from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.brain_core import BrainCore
from app.decision_journal import DecisionJournal
from app.editorial_calendar import EditorialCalendar
from app.goal_engine import GoalEngine
from app.memory import Memory
from app.models import ContentIdea, ContentTask, EditorialPlan, ProactiveRecommendation
from app.task_engine import TaskEngine


RECOMMENDATION_CATEGORIES = {
    "content",
    "business",
    "finance",
    "personal_brand",
    "operations",
    "social_growth",
}


@dataclass
class DailyBrainBriefing:
    daily_focus: str
    top_priorities: list[str]
    suggested_content_ideas: list[str]
    business_recommendations: list[str]
    risks_blockers: list[str]
    next_actions: list[str]


class ProactiveBrainLoop:
    def __init__(self, db: Session):
        self.db = db
        self.memory = Memory(db)
        self.brain_core = BrainCore(db)
        self.goal_engine = GoalEngine(db)
        self.task_engine = TaskEngine(db)
        self.decision_journal = DecisionJournal(db)
        self.editorial_calendar = EditorialCalendar(db)

    def generate_daily_briefing(self) -> DailyBrainBriefing:
        self.task_engine.ensure_foundation_tasks(
            brain_context=self.brain_core.context_for_agents(),
            memory_context=self.memory.build_context_from_memory(
                self.memory.retrieve_relevant_memories("daily proactive business operating system", limit=6)
            ),
        )

        active_goals = self.goal_engine.list_active_goals(limit=6)
        pending_tasks = self.goal_engine.prioritize_tasks_by_goals(self.task_engine.list_pending_tasks(limit=12))
        recent_decisions = self.decision_journal.latest_decisions(limit=5)
        recent_memories = self.memory.list_long_term_memories(limit=8)
        editorial_items = self._editorial_items(limit=6)
        brain_state = self.brain_core.get_state_summary().get("summary", "")

        focus = self._daily_focus(active_goals, pending_tasks, editorial_items, brain_state)
        priorities = self._top_priorities(pending_tasks, active_goals)
        ideas = self._content_ideas(editorial_items, recent_memories)
        recommendations = self._business_recommendations(active_goals, recent_decisions, pending_tasks)
        risks = self._risks(pending_tasks, editorial_items, recent_decisions)
        next_actions = self._next_actions(priorities, ideas, recommendations)

        briefing = DailyBrainBriefing(
            daily_focus=focus,
            top_priorities=priorities,
            suggested_content_ideas=ideas,
            business_recommendations=recommendations,
            risks_blockers=risks,
            next_actions=next_actions,
        )
        self.save_recommendations(briefing)
        return briefing

    def save_recommendations(self, briefing: DailyBrainBriefing) -> list[ProactiveRecommendation]:
        items = [
            {
                "title": "Focus contenuto del giorno",
                "description": briefing.daily_focus,
                "category": "content",
                "priority": "high",
                "reason": "Il personal brand finance cresce con contenuti educativi semplici e costanti.",
                "suggested_action": briefing.next_actions[0] if briefing.next_actions else "Preparare un contenuto finance entro oggi.",
            },
            {
                "title": "Allineare CTA e monetizzazione",
                "description": "Collegare il contenuto del giorno a una CTA chiara per generare lead o conversazioni.",
                "category": "business",
                "priority": "high",
                "reason": "Audience e fiducia devono collegarsi a un prossimo passo misurabile.",
                "suggested_action": "Aggiungere una CTA semplice al contenuto principale di oggi.",
            },
            {
                "title": "Proteggere esecuzione operativa",
                "description": "Ridurre dispersione e chiudere le prime priorita prima di aprire nuovi task.",
                "category": "operations",
                "priority": "medium",
                "reason": "Il rischio principale e accumulare idee senza output pubblicati.",
                "suggested_action": "Bloccare 45 minuti per completare la prima priorita.",
            },
        ]

        saved = []
        for item in items:
            saved.append(self.create_recommendation(**item))
        return saved

    def create_recommendation(
        self,
        title: str,
        description: str,
        category: str,
        priority: str,
        reason: str,
        suggested_action: str,
        status: str = "pending",
    ) -> ProactiveRecommendation:
        recommendation = ProactiveRecommendation(
            title=title.strip()[:255],
            description=description.strip(),
            category=self._normalize_category(category),
            priority=self._normalize_priority(priority),
            reason=reason.strip(),
            suggested_action=suggested_action.strip(),
            status=status.strip()[:32] or "pending",
        )
        self.db.add(recommendation)
        self.db.commit()
        self.db.refresh(recommendation)
        return recommendation

    def format_for_telegram(self, briefing: DailyBrainBriefing) -> str:
        priorities = self._numbered(briefing.top_priorities[:3])
        ideas = self._bullets(briefing.suggested_content_ideas[:3])
        recommendations = self._bullets(briefing.business_recommendations[:3])
        risks = self._bullets(briefing.risks_blockers[:3])
        next_actions = self._numbered(briefing.next_actions[:3])

        return (
            "Buongiorno Michele.\n\n"
            "Oggi il focus principale dovrebbe essere:\n"
            f"{briefing.daily_focus}\n\n"
            "Priorita:\n"
            f"{priorities}\n\n"
            "Contenuti suggeriti:\n"
            f"{ideas}\n\n"
            "Raccomandazioni business:\n"
            f"{recommendations}\n\n"
            "Rischi o blocchi:\n"
            f"{risks}\n\n"
            "Prossime azioni:\n"
            f"{next_actions}"
        )

    def _editorial_items(self, limit: int) -> list[Any]:
        plans = self.db.query(EditorialPlan).order_by(EditorialPlan.priority.desc(), EditorialPlan.created_at.desc()).limit(limit).all()
        ideas = self.db.query(ContentIdea).order_by(ContentIdea.priority.desc(), ContentIdea.created_at.desc()).limit(limit).all()
        tasks = self.db.query(ContentTask).order_by(ContentTask.priority.desc(), ContentTask.created_at.desc()).limit(limit).all()
        return [*plans, *ideas, *tasks][:limit]

    def _daily_focus(self, goals: list[Any], tasks: list[Any], editorial_items: list[Any], brain_state: str) -> str:
        if editorial_items:
            item = editorial_items[0]
            return f"rafforzare il personal brand finance con un contenuto educativo su: {item.title}."
        if tasks:
            return f"chiudere un output concreto collegato a: {tasks[0].title}."
        if goals:
            return f"avanzare sull'obiettivo: {goals[0].title}."
        if "ETF" in brain_state.upper():
            return "rafforzare il personal brand finance con un contenuto educativo semplice sugli ETF."
        return "rafforzare il personal brand finance con un contenuto educativo semplice sugli ETF."

    def _top_priorities(self, tasks: list[Any], goals: list[Any]) -> list[str]:
        priorities = [task.title for task in tasks[:3]]
        if len(priorities) < 3:
            fallbacks = [
                "Preparare un contenuto TikTok sugli ETF",
                "Sistemare una CTA per generare lead",
                "Aggiornare il piano editoriale della settimana",
            ]
            priorities.extend(item for item in fallbacks if item not in priorities)
        if goals and len(priorities) < 3:
            priorities.append(f"Collegare il lavoro di oggi all'obiettivo: {goals[0].title}")
        return priorities[:3]

    def _content_ideas(self, editorial_items: list[Any], memories: list[Any]) -> list[str]:
        ideas = []
        for item in editorial_items[:3]:
            hook = getattr(item, "hook", "")
            if hook:
                ideas.append(f"{item.title}: {hook}")
            else:
                ideas.append(item.title)
        if not ideas:
            ideas.append('"3 errori da evitare quando inizi a investire in ETF"')
        if len(ideas) < 2:
            ideas.append('"ETF: cosa guardare prima del rendimento passato"')
        if len(ideas) < 3 and memories:
            ideas.append(f"Trasforma in contenuto: {memories[0].title}")
        return ideas[:3]

    def _business_recommendations(self, goals: list[Any], decisions: list[Any], tasks: list[Any]) -> list[str]:
        recommendations = [
            "Collega il contenuto principale a una CTA semplice: commento, DM, newsletter o lead magnet.",
            "Misura un solo segnale oggi: salvataggi, risposte, click o lead generati.",
        ]
        if goals:
            recommendations.insert(0, f"Proteggi il focus sull'obiettivo: {goals[0].title}.")
        if decisions:
            recommendations.append(f"Mantieni coerenza con la decisione recente: {decisions[0].title}.")
        if tasks and len(tasks) > 6:
            recommendations.append("Riduci il carico: scegli 3 task e rimanda il resto.")
        return recommendations[:4]

    def _risks(self, tasks: list[Any], editorial_items: list[Any], decisions: list[Any]) -> list[str]:
        risks = []
        if not editorial_items:
            risks.append("Il calendario editoriale non ha abbastanza idee pronte.")
        if not tasks:
            risks.append("Mancano task operativi salvati per trasformare gli obiettivi in esecuzione.")
        if len(tasks) > 8:
            risks.append("Troppi task aperti possono ridurre focus e pubblicazione.")
        if not decisions:
            risks.append("Poche decisioni recenti salvate: rischio di cambiare direzione senza traccia.")
        return risks or ["Il rischio principale e disperdere energie su troppe iniziative non collegate."]

    def _next_actions(self, priorities: list[str], ideas: list[str], recommendations: list[str]) -> list[str]:
        actions = []
        if ideas:
            actions.append("Registrare o scrivere il contenuto principale entro oggi.")
        if priorities:
            actions.append(f"Chiudere la priorita numero 1: {priorities[0]}.")
        actions.append("Aggiungere una CTA misurabile prima di pubblicare.")
        if recommendations:
            actions.append("Rivedere a fine giornata cosa ha prodotto lead, risposte o avanzamento.")
        return actions[:4]

    def _normalize_category(self, category: str) -> str:
        category = category.strip().lower()
        return category if category in RECOMMENDATION_CATEGORIES else "business"

    def _normalize_priority(self, priority: str) -> str:
        priority = priority.strip().lower()
        return priority if priority in {"low", "medium", "high", "critical"} else "medium"

    def _numbered(self, items: list[str]) -> str:
        return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1)) or "1. Definire la prima azione concreta."

    def _bullets(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) or "- Nessun elemento disponibile."
