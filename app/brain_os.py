from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.context_builder import CognitiveContextBuilder
from app.goal_engine import GoalEngine
from app.memory import Memory
from app.orchestrator import Orchestrator
from app.response_synthesizer import ResponseSynthesizer
from app.tool_router import ToolRouter


logger = logging.getLogger(__name__)


class BrainOS:
    """AI Brain V3 central cognitive operating layer."""

    def __init__(self, db: Session, chat_id: str | int = "default", telegram_mode: bool = False):
        self.db = db
        self.chat_id = chat_id
        self.telegram_mode = telegram_mode
        self.memory = Memory(db)
        self.goal_engine = GoalEngine(db)
        self.context_builder = CognitiveContextBuilder(db, chat_id=chat_id)
        self.tool_router = ToolRouter(db)
        self.response_synthesizer = ResponseSynthesizer(telegram_mode=telegram_mode)
        self.orchestrator = Orchestrator(db, chat_id=chat_id)

    def handle(self, message: str, mode: str = "chat") -> dict[str, Any]:
        context = self.context_builder.build(message)
        tool_result = self.tool_router.route(context.effective_prompt, chat_id=self.chat_id)

        if tool_result.handled:
            task = self.memory.create_task(message)
            final = self.response_synthesizer.synthesize(
                tool_result.response,
                context=context,
                format_message=tool_result.format_message or context.effective_prompt,
            )
            self.memory.save_agent_result(task.id, tool_result.tool_name, final)
            self.memory.complete_task(task.id, final)
            self.context_builder.conversation_state.update_after_response(
                user_message=message,
                effective_prompt=context.effective_prompt,
                final_answer=final,
                agents_used=[tool_result.tool_name],
                active_intent=context.role_spec.intent,
                last_output_type=context.role_spec.output_type,
                active_goal=self._active_goal(context.effective_prompt, final),
                task_id=task.id,
            )
            logger.info("BrainOS handled via ToolRouter tool=%s", tool_result.tool_name)
            return self._shape_response(
                task_id=task.id,
                final=final,
                agents_used=[tool_result.tool_name],
                memories_used=context.memories_used,
                format_message=tool_result.format_message,
                mode=mode,
                results={tool_result.tool_name: final},
            )

        logger.info("BrainOS delegating to orchestrator intent=%s role=%s", context.role_spec.intent, context.role_spec.role)
        if mode == "task":
            result = self.orchestrator.handle_task(message)
            raw_final = result["final_answer"]
            final = self.response_synthesizer.synthesize(raw_final, context=context, format_message=result.get("format_message", message))
            result["final_answer"] = final
            return result

        result = self.orchestrator.handle_chat(message)
        raw_reply = result["reply"]
        final = self.response_synthesizer.synthesize(raw_reply, context=context, format_message=result.get("format_message", message))
        result["reply"] = final
        return result

    def handle_chat(self, message: str) -> dict[str, Any]:
        return self.handle(message, mode="chat")

    def handle_task(self, task: str) -> dict[str, Any]:
        return self.handle(task, mode="task")

    def _shape_response(
        self,
        task_id: int,
        final: str,
        agents_used: list[str],
        memories_used: list[dict[str, Any]],
        format_message: str,
        mode: str,
        results: dict[str, str],
    ) -> dict[str, Any]:
        base = {
            "task_id": task_id,
            "agents_used": agents_used,
            "memories_used": self._serialize_memories(memories_used),
            "format_message": format_message,
        }
        if mode == "task":
            return {
                **base,
                "final_answer": final,
                "results": results,
                "agents_used_memory": agents_used if memories_used else [],
                "memories_saved": 0,
            }
        return {**base, "reply": final}

    def _serialize_memories(self, memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        serialized = []
        for memory in memories:
            serialized.append(
                {
                    "id": int(memory.get("id", 0)),
                    "memory_type": str(memory.get("memory_type", "")),
                    "title": str(memory.get("title", "")),
                    "importance": int(memory.get("importance", 0)),
                    "source_task_id": int(memory.get("source_task_id", 0)),
                    "score": float(memory.get("score", 0)),
                    "matched_keywords": list(memory.get("matched_keywords", [])),
                }
            )
        return serialized

    def _active_goal(self, prompt: str, response: str) -> str | None:
        goal = self.goal_engine.best_goal_for_text(f"{prompt}\n{response}")
        return goal.title if goal else None
