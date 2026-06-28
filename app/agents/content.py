from __future__ import annotations

from typing import Optional

from openai import OpenAI

from app.config import Settings
from app.agents.prompts import GLOBAL_AGENT_RULES


class ContentAgent:
    name = "content"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
            if settings.openai_api_key
            else None
        )

    def run(
        self,
        task: str,
        research_context: Optional[str] = None,
        memory_context: Optional[str] = None,
    ) -> str:
        if not self.client:
            return self._local_response(task, research_context, memory_context)

        context = f"\n\nContesto di ricerca:\n{research_context}" if research_context else ""
        memory_section = f"\n\n{memory_context}" if memory_context else ""
        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei il Content Director di AI Brain. Produci contenuti chiari, concreti e pronti "
                            "per l'uso: script, post social, outline o copy. Per Michele, mantieni "
                            "coerenza con finance, educazione finanziaria, investimenti e personal brand. "
                            "Adatta tono, struttura e profondita alla piattaforma richiesta. Evita genericita: "
                            "usa hook specifici, esempi concreti, angoli editoriali chiari e CTA sensate. "
                            "Non produrre teoria sul content marketing: produci output utilizzabile e pronto da pubblicare. "
                            "Se l'utente chiede contenuti, consegna sempre un asset completo. "
                            "LinkedIn post: Hook, Body, CTA e hashtag opzionali. "
                            "Carousel: Title, struttura slide-by-slide e CTA. "
                            "TikTok/video: Hook, Script, Visual direction e CTA. "
                            "Non consegnare mai solo un hook, salvo richiesta esplicita di soli hook. "
                            "Usa eventuali memorie come "
                            "contesto, ma non ignorare mai quantita, formato e canale richiesti. "
                            f"{GLOBAL_AGENT_RULES}"
                            f"{memory_section}"
                        ),
                    },
                    {"role": "user", "content": f"{task}{context}"},
                ],
                temperature=0.7,
            )
            return response.choices[0].message.content or ""
        except Exception:
            return self._local_response(task, research_context, memory_context)

    def _local_response(
        self,
        task: str,
        research_context: Optional[str] = None,
        memory_context: Optional[str] = None,
    ) -> str:
        context_note = "basato sulla ricerca locale" if research_context else "senza contesto di ricerca"
        memory_note = f"\nMemorie usate:\n{memory_context}\n\n" if memory_context else ""
        return (
            f"Content Agent - bozza locale ({context_note})\n"
            f"Task: {task}\n\n"
            f"{memory_note}"
            "Formato suggerito:\n"
            "Hook: presenta il problema in modo diretto.\n\n"
            "Body/Script: sviluppa il contenuto con introduzione, 3 punti concreti e chiusura.\n\n"
            "Visual direction: indica cosa mostrare a schermo o come strutturare il post.\n\n"
            "CTA: invita a commentare, salvare o richiedere approfondimenti.\n\n"
            "Hashtag opzionali: #finanzapersonale #investimenti #educazionefinanziaria"
        )
