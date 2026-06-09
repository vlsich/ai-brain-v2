from __future__ import annotations

from typing import Optional

from openai import OpenAI

from app.config import Settings
from app.agents.prompts import GLOBAL_AGENT_RULES


class ManagerAgent:
    name = "manager"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
            if settings.openai_api_key
            else None
        )

    def choose_agents(self, task: str) -> list[str]:
        if self.should_answer_directly(task):
            return []

        normalized = task.lower()
        if self._is_editorial_planning_task(normalized):
            return ["content_planner"]

        if self._is_simple_content_task(normalized):
            return ["content"]

        content_keywords = (
            "post",
            "script",
            "contenuto",
            "contenuti",
            "social",
            "copy",
            "linkedin",
            "instagram",
            "newsletter",
            "tiktok",
            "video",
            "reel",
            "shorts",
        )
        research_keywords = ("analizza", "ricerca", "sintesi", "mercato", "competitor", "trend", "dati", "benchmark")
        finance_strategy_keywords = (
            "finanza",
            "finance",
            "investimenti",
            "investire",
            "educazione finanziaria",
            "personal branding",
            "personal brand",
            "crescita social",
            "conversione audience",
            "audience",
            "content strategy",
            "content funnel",
            "content pillars",
            "hook",
            "retention",
            "youtube finance",
            "instagram finance",
            "tiktok finance",
            "multi-platform",
        )
        editorial_keywords = (
            "piano editoriale",
            "calendario editoriale",
            "editorial plan",
            "piano contenuti",
            "piano dei contenuti",
            "piano della settimana",
            "piano settimanale",
            "weekly plan",
            "weekly content",
            "idee contenuto",
            "idee contenuti",
            "idee per contenuti",
            "content ideas",
            "task di oggi",
            "task devo fare",
            "quali task",
            "cosa devo pubblicare",
            "programmazione contenuti",
        )

        agents: list[str] = []
        if any(keyword in normalized for keyword in editorial_keywords):
            agents.append("content_planner")
        if any(keyword in normalized for keyword in finance_strategy_keywords):
            agents.append("finance_strategist")
        if any(keyword in normalized for keyword in research_keywords):
            agents.append("research")
        if any(keyword in normalized for keyword in content_keywords):
            agents.append("content")

        return agents or ["research", "content"]

    def _is_editorial_planning_task(self, normalized: str) -> bool:
        editorial_terms = (
            "piano editoriale",
            "calendario editoriale",
            "piano contenuti",
            "piano dei contenuti",
            "piano della settimana",
            "piano settimanale",
            "idee contenuto",
            "idee contenuti",
            "idee per contenuti",
            "task di oggi",
            "task devo fare",
            "quali task",
            "cosa devo pubblicare",
        )
        return any(term in normalized for term in editorial_terms)

    def _is_simple_content_task(self, normalized: str) -> bool:
        simple_action = any(word in normalized for word in ("scrivi", "crea", "fammi", "prepara"))
        content_target = any(word in normalized for word in ("post", "script", "caption", "email", "newsletter"))
        strategic_terms = ("strategia", "piano", "funnel", "pillar", "conversione", "analizza", "ricerca")
        return simple_action and content_target and not any(term in normalized for term in strategic_terms)

    def should_answer_directly(self, message: str) -> bool:
        normalized = message.lower().strip()
        direct_patterns = (
            "chi sono",
            "chi è michele",
            "chi e michele",
            "cosa sai di me",
            "che cosa sai di me",
            "cosa ricordi",
            "che cosa ricordi",
            "riassumi la memoria",
            "quali sono le mie preferenze",
            "quali sono i miei obiettivi",
            "qual è il mio business",
            "qual e il mio business",
            "qual è il suo business",
            "qual e il suo business",
            "che business",
        )
        return any(pattern in normalized for pattern in direct_patterns)

    def respond_directly(self, message: str, memory_context: Optional[str] = None) -> str:
        if not self.client:
            return self._local_direct_response(message, memory_context)

        memory_section = memory_context or "Nessuna memoria rilevante recuperata."
        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei il Manager Agent di AI Brain in modalita chat. "
                            "Capisci il vero obiettivo dell'utente e rispondi direttamente "
                            "quando non servono altri agenti. Se mancano dati essenziali, "
                            "fai una sola domanda di chiarimento. Usa solo memorie rilevanti; "
                            "se non sai qualcosa, dillo chiaramente. Mantieni focus sul business "
                            "finance, sul personal brand e sugli obiettivi di Michele quando pertinenti. "
                            "Considera sempre gli obiettivi attivi presenti nel contesto prima di dare "
                            "raccomandazioni. Quando proponi task o priorita, indica quale obiettivo "
                            "supportano e privilegia cio che avvicina a finance personal brand, audience, "
                            "content system e monetizzazione. "
                            f"{GLOBAL_AGENT_RULES}"
                            f"\n\n{memory_section}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Messaggio utente:\n{message}",
                    },
                ],
                temperature=0.3,
            )
            return response.choices[0].message.content or ""
        except Exception:
            return self._local_direct_response(message, memory_context)

    def synthesize(self, task: str, results: dict[str, str], memory_context: Optional[str] = None) -> str:
        if not self.client:
            return self._local_synthesis(task, results, memory_context)

        joined_results = "\n\n".join(f"{agent}:\n{output}" for agent, output in results.items())
        memory_section = f"\n\n{memory_context}" if memory_context else ""
        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei il Manager Agent. Capisci il vero obiettivo, usa solo gli "
                            "output necessari e sintetizza una risposta finale chiara, breve, "
                            "utile e orientata all'azione. Non sommare tutto: seleziona cio "
                            "che serve, elimina ridondanza e genericita. Mantieni focus sul business "
                            "finance/personal brand di Michele quando pertinente. Quando il task ha "
                            "implicazioni operative, prioritizza le azioni, proponi task concreti, "
                            "raccomandazioni e priorita settimanali. Ogni task proposto deve dire quale "
                            "obiettivo attivo supporta, quando il contesto lo permette. Rispetta sempre "
                            "i vincoli espliciti del task corrente. "
                            f"{GLOBAL_AGENT_RULES}"
                            f"{memory_section}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Task originale:\n{task}\n\nOutput agenti:\n{joined_results}",
                    },
                ],
                temperature=0.3,
            )
            return response.choices[0].message.content or ""
        except Exception:
            return self._local_synthesis(task, results, memory_context)

    def _local_synthesis(self, task: str, results: dict[str, str], memory_context: Optional[str] = None) -> str:
        sections = "\n\n".join(f"[{agent}]\n{output}" for agent, output in results.items())
        memory_note = f"\nMemorie usate:\n{memory_context}\n\n" if memory_context else ""
        return (
            "Manager Agent - risposta finale locale\n"
            f"Task: {task}\n\n"
            f"{memory_note}"
            "Sintesi:\n"
            "Il task e stato processato dagli agenti selezionati. Usa la ricerca come base "
            "strategica e il contenuto come bozza operativa pronta da rifinire. "
            "Prioritizza azioni legate a finance, contenuti, audience e monetizzazione.\n\n"
            f"Dettagli agenti:\n{sections}"
        )

    def _local_direct_response(self, message: str, memory_context: Optional[str] = None) -> str:
        if not memory_context:
            return (
                "Non ho ancora abbastanza memoria per rispondere con precisione. "
                "Posso iniziare a costruire il tuo profilo dai prossimi task e conversazioni."
            )

        clean_points = self._clean_memory_context_for_user(memory_context)
        return (
            "Da quello che ricordo:\n\n"
            f"{clean_points}\n\n"
            "Uso queste informazioni come contesto, non come verita definitiva: puoi correggerle quando vuoi."
        )

    def _clean_memory_context_for_user(self, memory_context: str) -> str:
        noisy_prefixes = (
            "BRAIN STATE SUMMARY",
            "Brain State Summary",
            "Questa sintesi rappresenta",
            "MEMORY CONTEXT",
            "Usa queste memorie",
        )
        lines = []
        for raw_line in memory_context.splitlines():
            line = raw_line.strip(" -")
            if not line:
                continue
            if any(line.startswith(prefix) for prefix in noisy_prefixes):
                continue
            if "id=" in line or "score=" in line or "matched=" in line:
                continue
            lines.append(line)
            if len(lines) >= 5:
                break

        if not lines:
            return memory_context[:900].strip()
        return "\n".join(f"- {line}" for line in lines)
