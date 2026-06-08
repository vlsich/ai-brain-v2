from __future__ import annotations

import logging
import json
from typing import Any

from sqlalchemy.orm import Session

from app.agents.content import ContentAgent
from app.agents.content_planner import ContentPlannerAgent
from app.agents.daily_review_agent import DailyReviewAgent
from app.agents.finance_strategist import FinanceContentStrategist
from app.agents.manager import ManagerAgent
from app.agents.memory_curator import MemoryCuratorAgent
from app.agents.research import ResearchAgent
from app.agents.weekly_review_agent import WeeklyReviewAgent
from app.brain_core import BrainCore
from app.config import get_settings
from app.decision_journal import DecisionJournal
from app.editorial_calendar import EditorialCalendar
from app.memory import Memory
from app.task_engine import TaskEngine


logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, db: Session):
        self.settings = get_settings()
        self.memory = Memory(db)
        self.brain_core = BrainCore(db)
        self.manager = ManagerAgent(self.settings)
        self.research = ResearchAgent(self.settings)
        self.finance_strategist = FinanceContentStrategist(self.settings)
        self.content_planner = ContentPlannerAgent(self.settings)
        self.content = ContentAgent(self.settings)
        self.memory_curator = MemoryCuratorAgent(self.settings)
        self.editorial_calendar = EditorialCalendar(db)
        self.task_engine = TaskEngine(db)
        self.decision_journal = DecisionJournal(db)
        self.daily_review_agent = DailyReviewAgent(self.settings)
        self.weekly_review_agent = WeeklyReviewAgent(self.settings)

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
            brain_context = self.brain_core.context_for_agents()
            memory_context = self._build_agent_context(brain_context, retrieved_memories)
            productivity_result = self._handle_productivity_command(prompt, brain_context, memory_context)
            if productivity_result:
                final_answer = productivity_result["final_answer"]
                agent_name = productivity_result["agent_name"]
                self.memory.save_agent_result(task.id, agent_name, final_answer)
                self.memory.complete_task(task.id, final_answer)
                saved_memories = self._curate_and_save_memories(
                    task_id=task.id,
                    prompt=prompt,
                    agents_to_use=[agent_name, "manager"],
                    results={agent_name: final_answer},
                    final_answer=final_answer,
                )
                self._maybe_update_brain_state(prompt, [agent_name, "manager"], len(saved_memories))
                return {
                    "task_id": task.id,
                    "agents_used": [agent_name, "manager"],
                    "final_answer": final_answer,
                    "results": {agent_name: final_answer},
                    "memories_used": self._serialize_retrieved_memories(retrieved_memories),
                    "agents_used_memory": [agent_name, "manager"] if retrieved_memories else [],
                    "memories_saved": len(saved_memories),
                }

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
                self._maybe_update_brain_state(prompt, ["manager"], len(saved_memories))

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

            if "content_planner" in agents_to_use:
                planner_payload = self.content_planner.plan_week(
                    prompt,
                    brain_context=brain_context,
                    memory_context=memory_context,
                )
                saved_editorial = self.editorial_calendar.save_planner_payload(planner_payload)
                planner_output = self._format_editorial_output(planner_payload, saved_editorial)
                results["content_planner"] = planner_output
                self.memory.save_agent_result(task.id, "content_planner", planner_output)

            if "content" in agents_to_use:
                research_context = results.get("research")
                finance_context = results.get("finance_strategist")
                planner_context = results.get("content_planner")
                combined_context = "\n\n".join(
                    context for context in (research_context, finance_context, planner_context) if context
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
            self._maybe_update_brain_state(prompt, agents_to_use, len(saved_memories))

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

    def _build_agent_context(self, brain_context: str, retrieved_memories: list[dict[str, Any]]) -> str:
        memory_context = self.memory.build_context_from_memory(retrieved_memories)
        parts = []
        if brain_context:
            parts.append(f"BRAIN STATE SUMMARY\n{brain_context}")
        if memory_context:
            parts.append(memory_context)
        return "\n\n".join(parts)

    def _maybe_update_brain_state(self, prompt: str, agents_to_use: list[str], saved_memories_count: int) -> None:
        if self.brain_core.should_update_after_task(prompt, agents_to_use, saved_memories_count):
            state = self.brain_core.update_state_summary()
            logger.info("Brain state updated version=%s", state["version"])

    def _format_editorial_output(self, payload: dict[str, Any], saved_editorial: dict[str, Any]) -> str:
        summary = saved_editorial.get("summary", "Piano editoriale aggiornato.")
        compact_payload = {
            "summary": summary,
            "plans": payload.get("plans", [])[:6],
            "ideas": payload.get("ideas", [])[:8],
            "tasks": payload.get("tasks", [])[:8],
        }
        return json.dumps(compact_payload, ensure_ascii=False, indent=2)

    def _handle_productivity_command(
        self,
        prompt: str,
        brain_context: str,
        memory_context: str,
    ) -> dict[str, str] | None:
        normalized = prompt.lower().strip()

        if self._is_complete_task_command(normalized):
            completed = self.task_engine.complete_task_from_text(prompt)
            if not completed:
                return {
                    "agent_name": "task_engine",
                    "final_answer": (
                        "Mi serve l'ID o una parte chiara del titolo del task da completare. "
                        "Esempio: segna task completato 12."
                    ),
                }
            return {
                "agent_name": "task_engine",
                "final_answer": f"Task completato: {completed.id}. {completed.title}",
            }

        if self._is_save_decision_command(normalized):
            decision = self.decision_journal.save_from_message(prompt)
            return {
                "agent_name": "decision_journal",
                "final_answer": (
                    "Decisione salvata.\n\n"
                    f"{decision.id}. {decision.title}\n"
                    f"Focus: {decision.related_topic or 'business strategy'}"
                ),
            }

        if self._is_latest_decisions_command(normalized):
            decisions = self.decision_journal.latest_decisions(limit=5)
            return {
                "agent_name": "decision_journal",
                "final_answer": "Ultime decisioni:\n" + self.decision_journal.format_decisions(decisions),
            }

        if self._is_daily_review_command(normalized):
            self.task_engine.ensure_foundation_tasks(brain_context, memory_context)
            tasks = self.task_engine.list_today_tasks(limit=8)
            decisions = self.decision_journal.latest_decisions(limit=5)
            payload = self.daily_review_agent.run(
                tasks=tasks,
                decisions=decisions,
                brain_context=brain_context,
                memory_context=memory_context,
            )
            review = self.task_engine.save_daily_review(payload)
            return {
                "agent_name": "daily_review",
                "final_answer": self._format_daily_review(review.id, payload, tasks),
            }

        if self._is_weekly_review_command(normalized):
            pending_tasks = self.task_engine.list_pending_tasks(limit=20)
            completed_tasks = self.task_engine.list_completed_tasks(days=7, limit=20)
            decisions = self.decision_journal.latest_decisions(limit=10)
            payload = self.weekly_review_agent.run(
                pending_tasks=pending_tasks,
                completed_tasks=completed_tasks,
                decisions=decisions,
                brain_context=brain_context,
                memory_context=memory_context,
            )
            review = self.task_engine.save_weekly_review(payload)
            return {
                "agent_name": "weekly_review",
                "final_answer": self._format_weekly_review(review.id, payload),
            }

        if self._is_priorities_command(normalized):
            self.task_engine.ensure_foundation_tasks(brain_context, memory_context)
            tasks = self.task_engine.list_high_priority_tasks(limit=8)
            if not tasks:
                tasks = self.task_engine.list_pending_tasks(limit=8)
            return {
                "agent_name": "task_engine",
                "final_answer": (
                    "Priorita operative:\n"
                    f"{self.task_engine.format_tasks(tasks, 'Nessuna priorita pendente salvata.')}\n\n"
                    "Raccomandazione: scegli il task con impatto piu diretto su audience, contenuti finance o monetizzazione."
                ),
            }

        if self._is_today_tasks_command(normalized):
            self.task_engine.ensure_foundation_tasks(brain_context, memory_context)
            tasks = self.task_engine.list_today_tasks(limit=8)
            return {
                "agent_name": "task_engine",
                "final_answer": (
                    "Task consigliati per oggi:\n"
                    f"{self.task_engine.format_tasks(tasks, 'Nessun task pendente salvato per oggi.')}\n\n"
                    "Prossimo passo: chiudi il primo task prima di aprire nuove idee."
                ),
            }

        return None

    def _format_daily_review(self, review_id: int, payload: dict[str, str], tasks: list) -> str:
        task_lines = self.task_engine.format_tasks(tasks[:5], "Nessun task operativo disponibile.")
        return (
            f"Briefing giornaliero #{review_id}\n\n"
            f"Vittorie:\n{payload.get('wins', '')}\n\n"
            f"Blocchi:\n{payload.get('blockers', '')}\n\n"
            f"Priorita:\n{payload.get('priorities', '')}\n\n"
            f"Task:\n{task_lines}\n\n"
            f"Raccomandazione:\n{payload.get('recommendations', '')}"
        )

    def _format_weekly_review(self, review_id: int, payload: dict[str, str]) -> str:
        return (
            f"Review settimanale #{review_id}\n\n"
            f"Progressi:\n{payload.get('progress', '')}\n\n"
            f"Task completati:\n{payload.get('completed_tasks', '')}\n\n"
            f"Decisioni:\n{payload.get('decisions', '')}\n\n"
            f"Allineamento:\n{payload.get('alignment', '')}\n\n"
            f"Raccomandazione:\n{payload.get('recommendations', '')}"
        )

    def _is_today_tasks_command(self, normalized: str) -> bool:
        patterns = (
            "quali task devo fare oggi",
            "cosa dovrei fare oggi",
            "cosa devo fare oggi",
            "task di oggi",
        )
        return any(pattern in normalized for pattern in patterns)

    def _is_priorities_command(self, normalized: str) -> bool:
        patterns = ("mostrami le priorità", "mostrami le priorita", "quali sono le priorità", "quali sono le priorita")
        return any(pattern in normalized for pattern in patterns)

    def _is_complete_task_command(self, normalized: str) -> bool:
        patterns = ("segna task completato", "segna come completato", "completa task")
        return any(pattern in normalized for pattern in patterns)

    def _is_save_decision_command(self, normalized: str) -> bool:
        patterns = ("salva questa decisione", "salva decisione", "decisione:")
        return any(normalized.startswith(pattern) for pattern in patterns)

    def _is_latest_decisions_command(self, normalized: str) -> bool:
        patterns = ("mostrami le ultime decisioni", "ultime decisioni", "decisioni recenti")
        return any(pattern in normalized for pattern in patterns)

    def _is_daily_review_command(self, normalized: str) -> bool:
        patterns = ("briefing giornaliero", "daily briefing", "review giornaliera")
        return any(pattern in normalized for pattern in patterns)

    def _is_weekly_review_command(self, normalized: str) -> bool:
        patterns = ("review settimanale", "weekly review", "riepilogo settimanale")
        return any(pattern in normalized for pattern in patterns)

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
