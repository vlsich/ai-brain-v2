from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional

from openai import OpenAI

from app.agents.prompts import GLOBAL_AGENT_RULES
from app.config import Settings


class ContentPlannerAgent:
    name = "content_planner"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
            if settings.openai_api_key
            else None
        )

    def plan_week(
        self,
        prompt: str,
        brain_context: str,
        memory_context: Optional[str] = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if not self.client:
            return self._local_plan(prompt)

        context = "\n\n".join(part for part in (brain_context, memory_context) if part)
        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei ContentPlanner, agente editoriale di AI Brain. Generi piani settimanali, "
                            "idee contenuto e task di crescita per il business finance/personal brand di Michele. "
                            "Focus: finanza personale, educazione finanziaria, investimenti, personal brand, "
                            "conversione audience e crescita multi-platform. Evita contenuti generici sull'AI: "
                            "AI e solo leva operativa interna. Rispondi solo con JSON valido: "
                            "{\"plans\":[],\"ideas\":[],\"tasks\":[]}. Ogni item deve avere: title, platform, "
                            "content_type, objective, target_audience, hook, status, priority, due_date. "
                            "due_date in formato YYYY-MM-DD. "
                            f"{GLOBAL_AGENT_RULES}\n\n{context}"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.45,
            )
            payload = json.loads(response.choices[0].message.content or "{}")
            return self._normalize_plan(payload)
        except Exception:
            return self._local_plan(prompt)

    def _normalize_plan(self, payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        return {
            "plans": self._normalize_items(payload.get("plans", []), default_status="planned"),
            "ideas": self._normalize_items(payload.get("ideas", []), default_status="idea"),
            "tasks": self._normalize_items(payload.get("tasks", []), default_status="todo"),
        }

    def _normalize_items(self, raw_items: Any, default_status: str) -> list[dict[str, Any]]:
        if not isinstance(raw_items, list):
            return []

        items = []
        for item in raw_items[:12]:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "title": str(item.get("title", "")).strip()[:255] or "Contenuto finance",
                    "platform": str(item.get("platform", "multi-platform")).strip()[:64],
                    "content_type": str(item.get("content_type", "short video")).strip()[:64],
                    "objective": str(item.get("objective", "Crescita del personal brand finance")).strip(),
                    "target_audience": str(item.get("target_audience", "Audience interessata a finanza personale")).strip()[:255],
                    "hook": str(item.get("hook", "Un errore finanziario che molti fanno senza accorgersene")).strip(),
                    "status": str(item.get("status", default_status)).strip()[:32] or default_status,
                    "priority": self._parse_priority(item.get("priority", 3)),
                    "due_date": str(item.get("due_date", "")).strip() or None,
                }
            )
        return items

    def _parse_priority(self, value: Any) -> int:
        try:
            priority = int(value)
        except (TypeError, ValueError):
            priority = 3
        return max(1, min(5, priority))

    def _local_plan(self, prompt: str) -> dict[str, list[dict[str, Any]]]:
        today = datetime.utcnow().date()
        dates = [(today + timedelta(days=offset)).isoformat() for offset in range(7)]
        plans = [
            {
                "title": "Errore finance della settimana",
                "platform": "TikTok",
                "content_type": "short video",
                "objective": "Aumentare reach e autorevolezza spiegando un errore comune di finanza personale.",
                "target_audience": "Giovani adulti interessati a gestire meglio soldi e investimenti",
                "hook": "Se fai questo errore con i soldi, stai rallentando la tua crescita finanziaria.",
                "status": "planned",
                "priority": 5,
                "due_date": dates[0],
            },
            {
                "title": "Framework investimento semplice",
                "platform": "Instagram",
                "content_type": "carousel",
                "objective": "Educare e salvare il contenuto, aumentando fiducia e relazione.",
                "target_audience": "Audience finance beginner/intermediate",
                "hook": "Il framework in 4 passaggi che uso per valutare una scelta di investimento.",
                "status": "planned",
                "priority": 4,
                "due_date": dates[2],
            },
            {
                "title": "Video authority long-form",
                "platform": "YouTube",
                "content_type": "long video",
                "objective": "Costruire authority e portare traffico verso newsletter o consulenza.",
                "target_audience": "Persone che vogliono metodo su finanza personale e investimenti",
                "hook": "Come costruire un sistema finanziario personale senza complicarsi la vita.",
                "status": "planned",
                "priority": 4,
                "due_date": dates[5],
            },
        ]
        ideas = [
            {
                "title": "3 bias che rovinano gli investimenti",
                "platform": "TikTok",
                "content_type": "short video",
                "objective": "Generare awareness con contenuto educativo semplice.",
                "target_audience": "Investitori principianti",
                "hook": "Il problema non e il mercato: spesso e il tuo cervello.",
                "status": "idea",
                "priority": 4,
                "due_date": dates[1],
            },
            {
                "title": "Prima di investire, sistema questo",
                "platform": "LinkedIn",
                "content_type": "post",
                "objective": "Posizionare Michele come guida pratica e razionale.",
                "target_audience": "Professionisti interessati a finanza personale",
                "hook": "Investire prima di avere un sistema e come accelerare senza volante.",
                "status": "idea",
                "priority": 3,
                "due_date": dates[3],
            },
        ]
        tasks = [
            {
                "title": "Scrivere 5 hook finance",
                "platform": "multi-platform",
                "content_type": "growth task",
                "objective": "Preparare varianti testabili per short video e post.",
                "target_audience": "Audience finance/personal brand di Michele",
                "hook": "Hook bank per contenuti della settimana.",
                "status": "todo",
                "priority": 5,
                "due_date": dates[0],
            },
            {
                "title": "Preparare CTA verso lead magnet",
                "platform": "multi-platform",
                "content_type": "conversion task",
                "objective": "Collegare contenuti educational a conversione audience.",
                "target_audience": "Follower caldi interessati a metodo e strumenti",
                "hook": "CTA chiara per trasformare attenzione in lead.",
                "status": "todo",
                "priority": 4,
                "due_date": dates[4],
            },
        ]
        return {"plans": plans, "ideas": ideas, "tasks": tasks}
