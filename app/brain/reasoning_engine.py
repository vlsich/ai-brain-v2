from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.context_builder import CognitiveContext, CognitiveContextBuilder


logger = logging.getLogger(__name__)


@dataclass
class ReasoningPlan:
    original_prompt: str
    effective_prompt: str
    detected_intent: str
    real_objective: str
    selected_role: str
    response_mode: str
    context_sources_used: list[str] = field(default_factory=list)
    context: CognitiveContext | None = None
    internal_steps: list[str] = field(default_factory=list)


class ReasoningEngine:
    """Builds an internal, non-user-visible reasoning plan before BrainOS answers."""

    ROLE_BY_INTENT = {
        "content_creation": "Content Director",
        "strategy": "Strategy Advisor",
        "business_analysis": "Research Analyst",
        "task_management": "Operations Manager",
        "goal_review": "CEO Advisor",
        "decision_support": "Executive Advisor",
        "conversation": "Strategy Advisor",
    }

    RESPONSE_MODE_BY_INTENT = {
        "content_creation": "content_creation",
        "strategy": "strategy",
        "business_analysis": "strategy",
        "task_management": "planning",
        "goal_review": "briefing",
        "decision_support": "decision_support",
        "conversation": "answer",
    }

    def __init__(self, db: Session, chat_id: str | int = "default", context_builder: CognitiveContextBuilder | None = None):
        self.db = db
        self.chat_id = chat_id
        self.context_builder = context_builder or CognitiveContextBuilder(db, chat_id=chat_id)

    def reason(self, prompt: str) -> ReasoningPlan:
        context = self.context_builder.build(prompt)
        intent = context.role_spec.intent
        response_mode = self._response_mode(intent, context.effective_prompt)
        selected_role = self.ROLE_BY_INTENT.get(intent, context.role_spec.role)
        sources = self._context_sources(context)
        objective = self._real_objective(context.effective_prompt, intent, response_mode)
        plan = ReasoningPlan(
            original_prompt=prompt,
            effective_prompt=context.effective_prompt,
            detected_intent=intent,
            real_objective=objective,
            selected_role=selected_role,
            response_mode=response_mode,
            context_sources_used=sources,
            context=context,
            internal_steps=self._internal_steps(intent, response_mode, sources),
        )
        logger.info(
            "ReasoningEngine plan intent=%s role=%s mode=%s sources=%s",
            plan.detected_intent,
            plan.selected_role,
            plan.response_mode,
            ",".join(plan.context_sources_used) or "none",
        )
        return plan

    def format_message(self) -> str:
        return ""

    def _response_mode(self, intent: str, prompt: str) -> str:
        normalized = prompt.lower()
        if any(term in normalized for term in ("briefing", "focus di oggi", "review", "cosa dovrei fare oggi")):
            return "briefing"
        if any(term in normalized for term in ("piano", "roadmap", "task", "priorità", "priorita", "step")):
            return "planning"
        if intent == "business_analysis" and any(term in normalized for term in ("ricerca", "research", "confronta", "benchmark")):
            return "answer"
        return self.RESPONSE_MODE_BY_INTENT.get(intent, "answer")

    def _context_sources(self, context: CognitiveContext) -> list[str]:
        sources = []
        if context.brain_state:
            sources.append("brain_state")
        if context.goals_context:
            sources.append("active_goals")
        if context.tasks_context:
            sources.append("recent_tasks")
        if context.decisions_context:
            sources.append("recent_decisions")
        if context.semantic_context:
            sources.append("semantic_memories")
        if context.memory_context:
            sources.append("long_term_memory")
        if context.conversation and (context.conversation.context or context.conversation.is_follow_up):
            sources.append("conversation_state")
        if context.graph_context:
            sources.append("graph_insights")
        return sources

    def _real_objective(self, prompt: str, intent: str, response_mode: str) -> str:
        normalized = " ".join(prompt.strip().split())
        if intent == "content_creation":
            return "produrre un asset contenuto completo e pronto da usare"
        if response_mode == "briefing":
            return "chiarire priorità, rischi e prossima azione operativa"
        if intent == "decision_support":
            return "aiutare Michele a scegliere una direzione pratica e motivata"
        if intent == "task_management":
            return "trasformare la richiesta in un piano d'azione eseguibile"
        if intent == "strategy":
            return "definire una raccomandazione strategica e i prossimi passi"
        if intent == "business_analysis":
            return "analizzare il problema e ricavare implicazioni operative"
        compact = re.sub(r"\s+", " ", normalized)
        return compact[:180] or "rispondere in modo utile alla richiesta"

    def _internal_steps(self, intent: str, response_mode: str, sources: list[str]) -> list[str]:
        return [
            f"intent={intent}",
            f"response_mode={response_mode}",
            f"context_sources={','.join(sources) or 'none'}",
            "produce only final answer; never expose internal reasoning",
        ]
