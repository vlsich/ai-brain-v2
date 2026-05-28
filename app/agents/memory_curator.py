from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import Settings
from app.agents.prompts import GLOBAL_AGENT_RULES


MEMORY_TYPES = {
    "user_profile",
    "business_goals",
    "brand_positioning",
    "preferences",
    "decisions",
    "content_strategy",
    "lessons_learned",
    "agents_behavior",
    "project_roadmap",
}


class MemoryCuratorAgent:
    name = "memory_curator"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
            if settings.openai_api_key
            else None
        )

    def curate(
        self,
        user_request: str,
        agents_used: list[str],
        agent_outputs: dict[str, str],
        final_answer: str,
    ) -> list[dict[str, Any]]:
        if not self.client:
            return self._local_curation(user_request, agents_used, agent_outputs, final_answer)

        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei un Memory Curator Agent. Decidi cosa merita di essere "
                            "salvato nella memoria a lungo termine di un sistema multi-agente. "
                            "Rispondi solo con JSON valido nel formato: "
                            "{\"memories\":[{\"memory_type\":\"...\",\"title\":\"...\","
                            "\"content\":\"...\",\"importance\":1}]}. "
                            "Usa solo questi memory_type: user_profile, business_goals, "
                            "brand_positioning, preferences, decisions, content_strategy, lessons_learned, "
                            "agents_behavior, project_roadmap. Salva solo informazioni utili, "
                            "riusabili e non ovvie. Non salvare rumore, passaggi generici, risposte "
                            "temporanee, ripetizioni, semplici output generati o dettagli privi di valore futuro. "
                            "Se una memoria simile sembra gia esistere, salva solo un aggiornamento realmente nuovo. "
                            f"{GLOBAL_AGENT_RULES}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "user_request": user_request,
                                "agents_used": agents_used,
                                "agent_outputs": agent_outputs,
                                "final_answer": final_answer,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            content = response.choices[0].message.content or "{}"
            payload = json.loads(content)
            return self._normalize_memories(payload.get("memories", []))
        except Exception:
            return self._local_curation(user_request, agents_used, agent_outputs, final_answer)

    def _normalize_memories(self, raw_memories: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_memories, list):
            return []

        memories: list[dict[str, Any]] = []
        for item in raw_memories[:8]:
            if not isinstance(item, dict):
                continue

            memory_type = str(item.get("memory_type", "")).strip()
            title = str(item.get("title", "")).strip()
            content = self._stringify_content(item.get("content", "")).strip()
            importance = self._parse_importance(item.get("importance", 3))

            if memory_type not in MEMORY_TYPES or not title or not content:
                continue

            memories.append(
                {
                    "memory_type": memory_type,
                    "title": title[:255],
                    "content": content,
                    "importance": importance,
                }
            )
        return memories

    def _parse_importance(self, value: Any) -> int:
        try:
            importance = int(value)
        except (TypeError, ValueError):
            importance = 3
        return max(1, min(5, importance))

    def _stringify_content(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    def _local_curation(
        self,
        user_request: str,
        agents_used: list[str],
        agent_outputs: dict[str, str],
        final_answer: str,
    ) -> list[dict[str, Any]]:
        memories: list[dict[str, Any]] = []

        normalized = user_request.lower()
        if any(keyword in normalized for keyword in ("tiktok", "contenuti", "post", "video", "reel", "shorts")):
            memories.append(
                {
                    "memory_type": "content_strategy",
                    "title": "Strategia contenuti finance e personal brand",
                    "content": (
                        "Michele sta costruendo contenuti e strategia social per il suo business finance/personal brand. "
                        f"Richiesta originale: {user_request}"
                    ),
                    "importance": 4,
                }
            )

        if any(keyword in normalized for keyword in ("brand", "posizionamento", "finance", "finanza", "multi-platform")):
            memories.append(
                {
                    "memory_type": "brand_positioning",
                    "title": "Posizionamento personal brand finance",
                    "content": (
                        "Michele sta definendo il posizionamento del personal brand collegato al business finance. "
                        f"Richiesta originale: {user_request}"
                    ),
                    "importance": 4,
                }
            )

        if "strategia" in normalized or "roadmap" in normalized:
            memories.append(
                {
                    "memory_type": "business_goals",
                    "title": "Obiettivo strategico business finance",
                    "content": f"Michele vuole definire una direzione operativa per crescita, contenuti o conversione: {user_request}",
                    "importance": 4,
                }
            )

        return memories[:8]
