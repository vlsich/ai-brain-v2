from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import Decision


class DecisionJournal:
    def __init__(self, db: Session):
        self.db = db

    def save_decision(
        self,
        title: str,
        context: str,
        decision: str,
        reasoning: str = "",
        expected_outcome: str = "",
        related_goal: Optional[str] = None,
        related_project: Optional[str] = None,
        related_topic: Optional[str] = None,
    ) -> Decision:
        model = Decision(
            title=title.strip()[:255],
            context=context.strip(),
            decision=decision.strip(),
            reasoning=reasoning.strip(),
            expected_outcome=expected_outcome.strip(),
            related_goal=related_goal,
            related_project=related_project,
            related_topic=related_topic,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def save_from_message(self, message: str) -> Decision:
        decision_text = self._strip_command(message)
        title = self._title_from_decision(decision_text)
        return self.save_decision(
            title=title,
            context="Decisione salvata da chat/Telegram.",
            decision=decision_text,
            reasoning="Da chiarire o aggiornare quando Michele aggiunge piu contesto.",
            expected_outcome="Mantenere coerenza operativa nelle prossime scelte del business.",
            related_goal="business growth",
            related_project="personal brand finance",
            related_topic=self._infer_topic(decision_text),
        )

    def latest_decisions(self, limit: int = 5) -> list[Decision]:
        return self.db.query(Decision).order_by(Decision.created_at.desc()).limit(limit).all()

    def format_decisions(self, decisions: list[Decision]) -> str:
        if not decisions:
            return "Non ho ancora decisioni strategiche salvate."

        return "\n".join(
            f"{decision.id}. {decision.title} - {decision.decision[:180]}"
            for decision in decisions
        )

    def _strip_command(self, message: str) -> str:
        normalized = message.strip()
        lowered = normalized.lower()
        for prefix in ("salva questa decisione", "salva decisione", "decisione:"):
            if lowered.startswith(prefix):
                return normalized[len(prefix) :].strip(" :-") or normalized
        return normalized

    def _title_from_decision(self, decision: str) -> str:
        clean = " ".join(decision.split())
        if not clean:
            return "Decisione strategica"
        return clean[:80]

    def _infer_topic(self, decision: str) -> str:
        lowered = decision.lower()
        if "tiktok" in lowered:
            return "TikTok"
        if "newsletter" in lowered:
            return "newsletter"
        if "prodotto" in lowered or "product" in lowered:
            return "product"
        if "invest" in lowered or "finanza" in lowered or "finance" in lowered:
            return "finance"
        return "business strategy"
