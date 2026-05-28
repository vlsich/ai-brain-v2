from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.agents.content import ContentAgent
from app.agents.finance_strategist import FinanceContentStrategist
from app.agents.manager import ManagerAgent
from app.agents.memory_curator import MemoryCuratorAgent
from app.agents.research import ResearchAgent
from app.config import get_settings
from app.memory import Memory


logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, db: Session):
        self.settings = get_settings()
        self.memory = Memory(db)
        self.manager = ManagerAgent(self.settings)
        self.research = ResearchAgent(self.settings)
        self.finance_strategist = FinanceContentStrategist(self.settings)
        self.content = ContentAgent(self.settings)
        self.memory_curator = MemoryCuratorAgent(self.settings)

    def handle_task(self, prompt: str) -> dict:
        return self._run(prompt, chat_mode=False)

    def handle_chat(self, message: str) -> dict:
        result = self._run(message, chat_mode=True)
        return {
            "reply": result["final_answer"],
            "agents_used": result["agents_used"],
            "memories_used": result["memories_used"],
            "task_id": result["task_id"],
        }

    def _run(self, prompt: str, chat_mode: bool) -> dict:
        task = self.memory.create_task(prompt)

        try:
            retrieved_memories = self.memory.retrieve_relevant_memories(prompt, limit=7)
            memory_context = self.memory.build_context_from_memory(retrieved_memories)
            agents_to_use = self.manager.choose_agents(prompt)
            results: dict[str, str] = {}
            agents_used_memory = agents_to_use + ["manager"] if retrieved_memories else []

            logger.info("Agent routing: agents_used=%s", ", ".join(agents_to_use) or "manager")
            self._log_retrieved_memories(retrieved_memories, agents_used_memory)

            if chat_mode and not agents_to_use:
                final_answer = self.manager.respond_directly(prompt, memory_context=memory_context)
                self.memory.save_agent_result(task.id, "manager", final_answer)
                self.memory.complete_task(task.id, final_answer)
                saved_memories = self._curate_and_save_memories(
                    task_id=task.id,
                    prompt=prompt,
                    agents_to_use=["manager"],
                    results={},
                    final_answer=final_answer,
                )

                return {
                    "task_id": task.id,
                    "agents_used": ["manager"],
                    "final_answer": final_answer,
                    "results": {},
                    "memories_used": self._serialize_retrieved_memories(retrieved_memories),
                    "agents_used_memory": ["manager"] if retrieved_memories else [],
                    "memories_saved": len(saved_memories),
                }

            if "research" in agents_to_use:
                research_output = self.research.run(prompt, memory_context=memory_context)
                results["research"] = research_output
                self.memory.save_agent_result(task.id, "research", research_output)

            if "finance_strategist" in agents_to_use:
                finance_output = self.finance_strategist.run(
                    prompt,
                    research_context=results.get("research"),
                    memory_context=memory_context,
                )
                results["finance_strategist"] = finance_output
                self.memory.save_agent_result(task.id, "finance_strategist", finance_output)

            if "content" in agents_to_use:
                research_context = results.get("research")
                finance_context = results.get("finance_strategist")
                combined_context = "\n\n".join(
                    context for context in (research_context, finance_context) if context
                )
                content_output = self.content.run(
                    prompt,
                    research_context=combined_context or None,
                    memory_context=memory_context,
                )
                results["content"] = content_output
                self.memory.save_agent_result(task.id, "content", content_output)

            final_answer = self.manager.synthesize(prompt, results, memory_context=memory_context)
            self.memory.save_agent_result(task.id, "manager", final_answer)
            self.memory.complete_task(task.id, final_answer)
            saved_memories = self._curate_and_save_memories(
                task_id=task.id,
                prompt=prompt,
                agents_to_use=agents_to_use,
                results=results,
                final_answer=final_answer,
            )

            return {
                "task_id": task.id,
                "agents_used": agents_to_use,
                "final_answer": final_answer,
                "results": results,
                "memories_used": self._serialize_retrieved_memories(retrieved_memories),
                "agents_used_memory": agents_used_memory,
                "memories_saved": len(saved_memories),
            }
        except Exception as exc:
            error = f"Errore durante l'esecuzione del task: {exc}"
            self.memory.fail_task(task.id, error)
            raise

    def _curate_and_save_memories(
        self,
        task_id: int,
        prompt: str,
        agents_to_use: list[str],
        results: dict[str, str],
        final_answer: str,
    ) -> list:
        curated_memories = self.memory_curator.curate(
            user_request=prompt,
            agents_used=agents_to_use,
            agent_outputs=results,
            final_answer=final_answer,
        )
        return [
            self.memory.save_long_term_memory(
                memory_type=memory_item["memory_type"],
                title=memory_item["title"],
                content=memory_item["content"],
                importance=memory_item["importance"],
                source_task_id=task_id,
            )
            for memory_item in curated_memories
        ]

    def _format_memory_context(self, memories: list[dict[str, Any]]) -> str:
        return self.memory.build_context_from_memory(memories)

    def _serialize_retrieved_memories(self, memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "id": memory["id"],
                "memory_type": memory["memory_type"],
                "title": memory["title"],
                "importance": memory["importance"],
                "source_task_id": memory["source_task_id"],
                "score": memory["score"],
                "matched_keywords": memory.get("matched_keywords", []),
            }
            for memory in memories
        ]

    def _log_retrieved_memories(
        self,
        memories: list[dict[str, Any]],
        agents_used_memory: list[str],
    ) -> None:
        if not memories:
            logger.info("Memory retrieval: nessuna memoria rilevante recuperata.")
            return

        for memory in memories:
            logger.info(
                "Memory retrieval: id=%s type=%s title=%r score=%s",
                memory["id"],
                memory["memory_type"],
                memory["title"],
                memory["score"],
            )
            logger.info("Memory retrieval: matched_keywords=%s", ", ".join(memory.get("matched_keywords", [])))
        logger.info("Memory retrieval: agenti che usano memoria=%s", ", ".join(agents_used_memory))
