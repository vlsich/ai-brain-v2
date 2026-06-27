from __future__ import annotations

from typing import Optional

from openai import OpenAI

from app.config import Settings
from app.agents.prompts import GLOBAL_AGENT_RULES


class FinanceContentStrategist:
    name = "finance_strategist"

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

        memory_section = f"\n\n{memory_context}" if memory_context else ""
        research_section = f"\n\nContesto ricerca:\n{research_context}" if research_context else ""
        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei FinanceContentStrategist. Agisci come Growth Strategist quando il task riguarda "
                            "crescita social/audience e come Strategy Consultant quando riguarda business, funnel "
                            "o monetizzazione. Sei specializzato per il business finance "
                            "e il personal brand di Michele. Crei strategie contenuto, format, funnel "
                            "e piani crescita per TikTok, Instagram, YouTube e piattaforme social. "
                            "Lavora su: finanza personale, educazione finanziaria, investimenti, "
                            "personal branding, conversione audience, content pillars, hook virali, "
                            "retention, educational content e strategia multi-platform. "
                            "Mantieni il focus su finanza, educazione finanziaria, investimenti e personal brand. "
                            "Non trasformare l'AI nel tema principale dei contenuti finance: usa AI Brain solo "
                            "come leva operativa interna per ricerca, produzione, distribuzione e memoria. "
                            "Produci output pratici, prioritizzati e orientati a crescita, fiducia e conversione. "
                            "Prima rileva intento, poi scegli ruolo, poi formato. Se la richiesta e operativa, "
                            "dai raccomandazioni eseguibili e non una sintesi generica. "
                            "Evita strategie generiche: definisci target, angolo, pillar, format, CTA e prossimo passo. "
                            "Usa le memorie su Michele, business goals e brand positioning, ma rispetta "
                            "sempre il task corrente. "
                            f"{GLOBAL_AGENT_RULES}"
                            f"{memory_section}"
                        ),
                    },
                    {"role": "user", "content": f"Task:\n{task}{research_section}"},
                ],
                temperature=0.55,
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
        memory_note = f"\nMemorie usate:\n{memory_context}\n" if memory_context else ""
        research_note = f"\nBase ricerca:\n{research_context}\n" if research_context else ""
        return (
            "FinanceContentStrategist - strategia locale\n"
            f"Task: {task}\n"
            f"{memory_note}"
            f"{research_note}\n"
            "Direzione strategica:\n"
            "- Posizionare Michele come creator finance pratico, chiaro e orientato ai risultati.\n"
            "- Collegare contenuti educational a fiducia, lead generation e conversione audience.\n"
            "- Usare AI Brain come leva per ricerca, produzione, distribuzione e memoria decisionale.\n\n"
            "Content pillars:\n"
            "1. Educazione finanziaria semplice e applicabile.\n"
            "2. Errori comuni, bias e miti sulla finanza personale.\n"
            "3. Strategie, framework e checklist per investire con metodo.\n"
            "4. Dietro le quinte del business, metodo decisionale e costruzione del personal brand.\n\n"
            "Format consigliati:\n"
            "- Hook virale + errore finance + correzione pratica.\n"
            "- Mini-lezione da 45-60 secondi con esempio numerico.\n"
            "- Serie multi-platform: TikTok per reach, Instagram per relazione, YouTube per authority.\n\n"
            "Funnel contenuti:\n"
            "- Awareness: short video con hook forti.\n"
            "- Trust: caroselli, newsletter e video lunghi educational.\n"
            "- Conversione: CTA verso lead magnet, consulenza, community o prodotto."
        )
