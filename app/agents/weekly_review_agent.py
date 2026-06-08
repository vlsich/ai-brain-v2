from __future__ import annotations

import json
from typing import Any, Optional

from openai import OpenAI

from app.agents.prompts import GLOBAL_AGENT_RULES
from app.config import Settings
from app.models import Decision, ProductivityTask


class WeeklyReviewAgent:
    name = "weekly_review"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
            if settings.openai_api_key
            else None
        )

    def run(
        self,
        pending_tasks: list[ProductivityTask],
        completed_tasks: list[ProductivityTask],
        decisions: list[Decision],
        brain_context: str,
        memory_context: Optional[str] = None,
    ) -> dict[str, str]:
        if not self.client:
            return self._local_review(pending_tasks, completed_tasks, decisions)

        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei WeeklyReviewAgent di AI Brain. Valuti progressi, task completati, "
                            "decisioni e allineamento con gli obiettivi business di Michele. Focus: "
                            "finance, investing, content creation, personal brand growth, audience building "
                            "e monetizzazione. Output concreto, senza genericita. Rispondi solo con JSON "
                            "valido con chiavi: progress, completed_tasks, decisions, alignment, recommendations. "
                            f"{GLOBAL_AGENT_RULES}\n\nBRAIN STATE\n{brain_context}\n\nMEMORIA\n{memory_context or ''}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "pending_tasks": [self._task_payload(task) for task in pending_tasks],
                                "completed_tasks": [self._task_payload(task) for task in completed_tasks],
                                "decisions": [self._decision_payload(decision) for decision in decisions],
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
            return self._local_review(pending_tasks, completed_tasks, decisions)

    def _local_review(
        self,
        pending_tasks: list[ProductivityTask],
        completed_tasks: list[ProductivityTask],
        decisions: list[Decision],
    ) -> dict[str, str]:
        completed = "\n".join(f"- {task.title}" for task in completed_tasks[:5]) or "Nessun task completato registrato negli ultimi 7 giorni."
        pending = "\n".join(f"- {task.title} ({task.priority})" for task in pending_tasks[:5]) or "Nessun task pendente registrato."
        decisions_text = "\n".join(f"- {decision.title}" for decision in decisions[:5]) or "Nessuna decisione recente registrata."
        return {
            "progress": "La settimana va valutata sulla produzione di asset concreti: contenuti pubblicabili, audience growth e leve di monetizzazione.",
            "completed_tasks": completed,
            "decisions": decisions_text,
            "alignment": f"Priorita aperte:\n{pending}",
            "recommendations": (
                "Scegli 1 canale principale, 1 contenuto finance ad alto valore e 1 azione di conversione. "
                "La prossima settimana deve ridurre dispersione e aumentare output pubblicabile."
            ),
        }

    def _normalize(self, payload: dict[str, Any]) -> dict[str, str]:
        return {
            "progress": str(payload.get("progress", "")).strip(),
            "completed_tasks": str(payload.get("completed_tasks", "")).strip(),
            "decisions": str(payload.get("decisions", "")).strip(),
            "alignment": str(payload.get("alignment", "")).strip(),
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
