from __future__ import annotations

from typing import Optional

from openai import OpenAI

from app.config import Settings
from app.agents.prompts import GLOBAL_AGENT_RULES


class ResearchAgent:
    name = "research"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
            if settings.openai_api_key
            else None
        )

    def run(self, task: str, memory_context: Optional[str] = None) -> str:
        if not self.client:
            return self._local_response(task, memory_context)

        memory_section = f"\n\n{memory_context}" if memory_context else ""
        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei un Research Agent. Analizza task, contesto, rischi, "
                            "opportunita e produci una sintesi operativa in italiano. "
                            "Usa eventuali memorie come contesto, ma rispetta sempre "
                            "il task corrente e i suoi vincoli specifici. Non inventare dati: "
                            "distingui fatti, ipotesi e raccomandazioni. "
                            f"{GLOBAL_AGENT_RULES}"
                            f"{memory_section}"
                        ),
                    },
                    {"role": "user", "content": task},
                ],
                temperature=0.4,
            )
            return response.choices[0].message.content or ""
        except Exception:
            return self._local_response(task, memory_context)

    def _local_response(self, task: str, memory_context: Optional[str] = None) -> str:
        memory_note = f"\nMemorie usate:\n{memory_context}\n\n" if memory_context else ""
        return (
            "Research Agent - sintesi locale\n"
            f"Task analizzato: {task}\n\n"
            f"{memory_note}"
            "Punti chiave:\n"
            "- Identificare obiettivo, pubblico e vincoli del task.\n"
            "- Separare dati, ipotesi e decisioni operative.\n"
            "- Trasformare la ricerca in raccomandazioni pratiche.\n\n"
            "Output consigliato: una breve analisi con priorita, insight e prossimi passi."
        )
