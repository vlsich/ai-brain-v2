from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.brain_core import BrainCore
from app.conversation_state import ConversationStateManager, ConversationResolution
from app.decision_journal import DecisionJournal
from app.goal_engine import GoalEngine
from app.graph_intelligence import GraphIntelligence
from app.memory import Memory
from app.role_router import RoleRouter, RoleSpec
from app.semantic_memory import SemanticMemory
from app.task_engine import TaskEngine


logger = logging.getLogger(__name__)


@dataclass
class CognitiveContext:
    original_prompt: str
    effective_prompt: str
    role_spec: RoleSpec
    conversation: ConversationResolution
    brain_state: str = ""
    memory_context: str = ""
    semantic_context: str = ""
    goals_context: str = ""
    tasks_context: str = ""
    decisions_context: str = ""
    graph_context: str = ""
    full_context: str = ""
    memories_used: list[dict[str, Any]] = field(default_factory=list)


class CognitiveContextBuilder:
    def __init__(self, db: Session, chat_id: str | int = "default"):
        self.db = db
        self.memory = Memory(db)
        self.brain_core = BrainCore(db)
        self.semantic_memory = SemanticMemory(db)
        self.goal_engine = GoalEngine(db)
        self.task_engine = TaskEngine(db)
        self.decision_journal = DecisionJournal(db)
        self.graph_intelligence = GraphIntelligence(db)
        self.conversation_state = ConversationStateManager(db, chat_id=chat_id)
        self.role_router = RoleRouter()

    def build(self, prompt: str) -> CognitiveContext:
        conversation = self.conversation_state.resolve(prompt)
        effective_prompt = conversation.effective_prompt
        role_spec = (
            self.role_router.spec_for_intent(conversation.state.active_intent)
            if conversation.is_follow_up and conversation.state and conversation.state.active_intent
            else self.role_router.spec_for_text(effective_prompt)
        )

        keyword_memories = self.memory.retrieve_relevant_memories(effective_prompt, limit=7)
        semantic_memories = self.semantic_memory.retrieve(effective_prompt, limit=5)
        memories_used = self._dedupe_memories(keyword_memories + semantic_memories)

        brain_state = self.brain_core.context_for_agents()
        memory_context = self.memory.build_context_from_memory(keyword_memories)
        semantic_context = self.semantic_memory.build_context(semantic_memories)
        goals_context = self.goal_engine.goal_context()
        tasks_context = self._tasks_context(effective_prompt)
        decisions_context = self._decisions_context()
        graph_context = self._graph_context()

        parts = [
            conversation.context,
            self.role_router.context_for_prompt(role_spec),
            f"BRAIN STATE\n{brain_state}" if brain_state else "",
            goals_context,
            tasks_context,
            decisions_context,
            graph_context,
            semantic_context,
            memory_context,
        ]
        full_context = "\n\n".join(part for part in parts if part)

        logger.info(
            "Cognitive context built intent=%s role=%s memories=%s",
            role_spec.intent,
            role_spec.role,
            len(memories_used),
        )

        return CognitiveContext(
            original_prompt=prompt,
            effective_prompt=effective_prompt,
            role_spec=role_spec,
            conversation=conversation,
            brain_state=brain_state,
            memory_context=memory_context,
            semantic_context=semantic_context,
            goals_context=goals_context,
            tasks_context=tasks_context,
            decisions_context=decisions_context,
            graph_context=graph_context,
            full_context=full_context,
            memories_used=memories_used,
        )

    def _tasks_context(self, prompt: str) -> str:
        tokens = set(re.findall(r"[a-zA-ZÀ-ÿ0-9_]{3,}", prompt.lower()))
        tasks = self.task_engine.list_pending_tasks(limit=20)
        scored = []
        for task in tasks:
            text = f"{task.title} {task.description} {task.category} {task.related_goal or ''} {task.related_topic or ''}".lower()
            task_tokens = set(re.findall(r"[a-zA-ZÀ-ÿ0-9_]{3,}", text))
            overlap = len(tokens.intersection(task_tokens))
            priority = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(task.priority, 2)
            if overlap or task.priority in {"critical", "high"}:
                scored.append((overlap, priority, task))

        selected = [item[2] for item in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)[:6]]
        if not selected:
            selected = tasks[:4]
        if not selected:
            return ""
        lines = ["RELEVANT TASKS"]
        for task in selected:
            lines.append(f"- {task.title} [{task.priority}] goal={task.related_goal or 'da collegare'} topic={task.related_topic or 'n/a'}")
        return "\n".join(lines)

    def _decisions_context(self) -> str:
        decisions = self.decision_journal.latest_decisions(limit=5)
        if not decisions:
            return ""
        lines = ["RECENT DECISIONS"]
        for decision in decisions:
            lines.append(f"- {decision.title}: {decision.decision[:220]}")
        return "\n".join(lines)

    def _graph_context(self) -> str:
        try:
            insights = self.graph_intelligence.insights(limit=5)
        except Exception:
            logger.exception("Graph insights context failed")
            return ""
        opportunities = insights.get("opportunities", [])[:3]
        weak_goals = insights.get("weakly_connected_goals", [])[:3]
        if not opportunities and not weak_goals:
            return ""
        lines = ["KNOWLEDGE GRAPH INSIGHTS"]
        for opportunity in opportunities:
            lines.append(f"- opportunity: {opportunity}")
        for goal in weak_goals:
            lines.append(f"- weak goal: {goal['title']} ({goal.get('reason', 'poche connessioni')})")
        return "\n".join(lines)

    def _dedupe_memories(self, memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped = []
        seen = set()
        for memory in sorted(memories, key=lambda item: item.get("score", 0), reverse=True):
            key = (memory.get("retrieval", "keyword"), memory.get("id"), memory.get("memory_type"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(memory)
        return deduped[:10]
