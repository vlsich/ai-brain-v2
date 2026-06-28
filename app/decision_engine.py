from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.brain_core import BrainCore
from app.decision_journal import DecisionJournal
from app.goal_engine import GoalEngine
from app.memory import Memory
from app.task_engine import TaskEngine


@dataclass
class DecisionBrief:
    context: str
    options: list[str]
    pros: list[str]
    cons: list[str]
    risks: list[str]
    recommendation: str
    next_action: str
    should_save: bool


class DecisionEngine:
    def __init__(self, db: Session):
        self.db = db
        self.memory = Memory(db)
        self.brain_core = BrainCore(db)
        self.goal_engine = GoalEngine(db)
        self.task_engine = TaskEngine(db)
        self.decision_journal = DecisionJournal(db)

    def evaluate(self, prompt: str, save: bool = False) -> DecisionBrief:
        active_goals = self.goal_engine.list_active_goals(limit=5)
        recent_tasks = self.task_engine.list_pending_tasks(limit=6)
        recent_decisions = self.decision_journal.latest_decisions(limit=5)
        memories = self.memory.retrieve_relevant_memories(prompt, limit=6)
        brain_state = self.brain_core.context_for_agents(max_chars=1200)

        decision = self._clarify_decision(prompt)
        options = self._options(prompt)
        pros = self._pros(options, active_goals, memories)
        cons = self._cons(options, recent_tasks)
        risks = self._risks(prompt, recent_tasks, recent_decisions)
        recommendation = self._recommendation(decision, options, active_goals, brain_state)
        next_action = self._next_action(recommendation, prompt)

        brief = DecisionBrief(
            context=self._context(decision, active_goals, recent_decisions),
            options=options,
            pros=pros,
            cons=cons,
            risks=risks,
            recommendation=recommendation,
            next_action=next_action,
            should_save=save or self._should_save(prompt),
        )

        if brief.should_save:
            self.save_decision(prompt, brief)
        return brief

    def save_decision(self, prompt: str, brief: DecisionBrief):
        best_goal = self.goal_engine.best_goal_for_text(f"{prompt}\n{brief.recommendation}")
        return self.decision_journal.save_decision(
            title=self._decision_title(prompt),
            context=brief.context,
            decision=brief.recommendation,
            reasoning=" | ".join(brief.pros[:2] + brief.cons[:1]),
            expected_outcome=brief.next_action,
            related_goal=best_goal.title if best_goal else "business growth",
            related_project="AI Brain decision engine",
            related_topic=self._topic(prompt),
        )

    def format_for_telegram(self, brief: DecisionBrief) -> str:
        saved_line = "Ho salvato questa decisione nel Decision Journal.\n\n" if brief.should_save else ""
        return (
            f"{saved_line}{brief.context}\n\n"
            "Opzioni:\n"
            f"{self._numbered(brief.options)}\n\n"
            "Pro:\n"
            f"{self._bullets(brief.pros)}\n\n"
            "Contro:\n"
            f"{self._bullets(brief.cons)}\n\n"
            "Rischi:\n"
            f"{self._bullets(brief.risks)}\n\n"
            "Consiglio:\n"
            f"{brief.recommendation}\n\n"
            "Prossima azione:\n"
            f"{brief.next_action}"
        )

    def _clarify_decision(self, prompt: str) -> str:
        clean = re.sub(
            r"(?i)\b(aiutami a decidere|cosa mi consigli|valuta questa decisione|pro e contro|salva questa decisione|decisione:)\b",
            "",
            prompt,
        ).strip(" :-?.")
        return clean or "scegliere la prossima mossa piu utile per il business finance e il personal brand"

    def _options(self, prompt: str) -> list[str]:
        decision = self._clarify_decision(prompt)
        if " o " in decision.lower():
            parts = [part.strip(" .") for part in re.split(r"\s+o\s+", decision, flags=re.IGNORECASE) if part.strip()]
            if len(parts) >= 2:
                return parts[:3]
        if "newsletter" in prompt.lower():
            return ["Lanciare una newsletter pilota", "Aspettare e rafforzare prima contenuti e offerta"]
        if "tiktok" in prompt.lower():
            return ["Concentrarsi su TikTok per reach", "Distribuire gli stessi contenuti anche su LinkedIn/Instagram"]
        return [f"Procedere con: {decision}", "Rimandare e raccogliere piu segnali", "Fare un test piccolo e reversibile"]

    def _pros(self, options: list[str], goals: list[Any], memories: list[dict[str, Any]]) -> list[str]:
        pros = ["Crea apprendimento reale invece di restare nel ragionamento astratto."]
        if goals:
            pros.append(f"Si collega all'obiettivo attivo: {goals[0].title}.")
        if memories:
            pros.append(f"Usa contesto gia noto: {memories[0]['title']}.")
        if options:
            pros.append(f"L'opzione piu operativa e: {options[0]}.")
        return pros[:4]

    def _cons(self, options: list[str], tasks: list[Any]) -> list[str]:
        cons = ["Richiede focus: se aggiunge lavoro senza priorita, aumenta dispersione."]
        if len(tasks) >= 5:
            cons.append("Ci sono gia diversi task aperti: serve evitare nuovo carico non collegato.")
        if len(options) > 1:
            cons.append(f"L'alternativa '{options[1]}' puo essere piu prudente ma rallenta il feedback.")
        return cons[:4]

    def _risks(self, prompt: str, tasks: list[Any], decisions: list[Any]) -> list[str]:
        risks = []
        if "invest" in prompt.lower() or "finance" in prompt.lower() or "finanza" in prompt.lower():
            risks.append("Non trasformare una decisione finanziaria in contenuto senza distinguere educazione e consulenza personalizzata.")
        if tasks:
            risks.append("Rischio operativo: iniziare una nuova iniziativa senza chiudere i task gia prioritari.")
        if not decisions and not self._should_save(prompt):
            risks.append("Rischio strategico: decidere senza salvare criterio e risultato atteso.")
        return risks or ["Il rischio principale e scegliere senza una metrica di successo chiara."]

    def _recommendation(self, decision: str, options: list[str], goals: list[Any], brain_state: str) -> str:
        preferred = options[0] if options else decision
        if goals:
            return f"Io sceglierei: {preferred}. E la scelta piu utile se resta collegata a '{goals[0].title}' e produce un segnale misurabile entro pochi giorni."
        if "personal brand" in brain_state.lower() or "finance" in brain_state.lower():
            return f"Io sceglierei: {preferred}. E coerente con il focus finance/personal brand e permette di imparare velocemente."
        return f"Io sceglierei: {preferred}, ma solo come test piccolo e reversibile."

    def _next_action(self, recommendation: str, prompt: str) -> str:
        if "newsletter" in prompt.lower():
            return "Definisci promessa, frequenza e CTA; poi prepara il primo invio pilota."
        if "tiktok" in prompt.lower() or "contenut" in prompt.lower():
            return "Trasforma la decisione in un contenuto pubblicabile oggi con hook, corpo e CTA."
        return "Scrivi criterio di successo, rischio massimo accettabile e primo test da eseguire entro 48 ore."

    def _context(self, decision: str, goals: list[Any], decisions: list[Any]) -> str:
        context = f"La decisione da chiarire e: {decision}."
        if goals:
            context += f" Va letta rispetto all'obiettivo attivo: {goals[0].title}."
        if decisions:
            context += f" Decisione recente da non contraddire: {decisions[0].title}."
        return context

    def _should_save(self, prompt: str) -> bool:
        normalized = prompt.lower()
        return normalized.startswith(("salva questa decisione", "salva decisione", "decisione:")) or any(
            term in normalized for term in ("ho deciso", "decido di")
        )

    def _decision_title(self, prompt: str) -> str:
        return self._clarify_decision(prompt)[:80] or "Decisione strategica"

    def _topic(self, prompt: str) -> str:
        lowered = prompt.lower()
        if "contenut" in lowered or "tiktok" in lowered or "linkedin" in lowered:
            return "content strategy"
        if "finance" in lowered or "finanza" in lowered or "invest" in lowered:
            return "finance"
        if "business" in lowered or "monet" in lowered:
            return "business strategy"
        return "decision support"

    def _numbered(self, items: list[str]) -> str:
        return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))

    def _bullets(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items)
