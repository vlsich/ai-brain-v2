from __future__ import annotations

import json
from typing import Any, Optional

from openai import OpenAI

from app.agents.prompts import GLOBAL_AGENT_RULES
from app.config import Settings
from app.models import Decision, ProductivityTask


class DailyReviewAgent:
    name = "daily_review"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
            if settings.openai_api_key
            else None
        )

    def run(
        self,
        tasks: list[ProductivityTask],
        decisions: list[Decision],
        brain_context: str,
        memory_context: Optional[str] = None,
    ) -> dict[str, str]:
        if not self.client:
            return self._local_review(tasks, decisions)

        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei DailyReviewAgent di AI Brain. Produci un briefing giornaliero "
                            "per Michele: pratico, breve, business-oriented. Usa il contesto per "
                            "dare priorita a finance, investing, content creation, personal brand, "
                            "audience building e monetizzazione. Evita contenuti generici sull'AI. "
                            "Rispondi solo con JSON valido con chiavi: wins, blockers, priorities, recommendations. "
                            f"{GLOBAL_AGENT_RULES}\n\nBRAIN STATE\n{brain_context}\n\nMEMORIA\n{memory_context or ''}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "pending_tasks": [self._task_payload(task) for task in tasks],
                                "latest_decisions": [self._decision_payload(decision) for decision in decisions],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.25,
            )
            return self._normalize(json.loads(response.choices[0].message.content or "{}"))
        except Exception:
            return self._local_review(tasks, decisions)

    def _local_review(self, tasks: list[ProductivityTask], decisions: list[Decision]) -> dict[str, str]:
        top_tasks = tasks[:3]
        priorities = "\n".join(
            f"{index}. {task.title} ({task.priority}, {task.estimated_minutes} min)"
            for index, task in enumerate(top_tasks, start=1)
        )
        if not priorities:
            priorities = "Definire 1 task finance/content ad alto impatto e bloccarlo in agenda."

        blockers = "Nessun blocco esplicito salvato. Rischio principale: dispersione tra troppe attivita non collegate a crescita e monetizzazione."
        latest_decision = decisions[0].title if decisions else "nessuna decisione recente"
        return {
            "wins": f"Contesto operativo attivo. Ultima decisione rilevante: {latest_decision}.",
            "blockers": blockers,
            "priorities": priorities,
            "recommendations": (
                "Lavora prima sul contenuto o task con impatto diretto su audience e conversione. "
                "Chiudi un output pubblicabile prima di aprire nuove idee."
            ),
        }

    def _normalize(self, payload: dict[str, Any]) -> dict[str, str]:
        return {
            "wins": str(payload.get("wins", "")).strip(),
            "blockers": str(payload.get("blockers", "")).strip(),
            "priorities": str(payload.get("priorities", "")).strip(),
            "recommendations": str(payload.get("recommendations", "")).strip(),
        }

    def _task_payload(self, task: ProductivityTask) -> dict[str, Any]:
        return {
            "id": task.id,
            "title": task.title,
            "category": task.category,
            "priority": task.priority,
            "status": task.status,
            "estimated_minutes": task.estimated_minutes,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "related_goal": task.related_goal,
            "related_project": task.related_project,
            "related_topic": task.related_topic,
        }

    def _decision_payload(self, decision: Decision) -> dict[str, Any]:
        return {
            "id": decision.id,
            "title": decision.title,
            "decision": decision.decision,
            "related_goal": decision.related_goal,
            "related_project": decision.related_project,
            "related_topic": decision.related_topic,
        }
