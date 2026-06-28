from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.brain_core import BrainCore
from app.decision_journal import DecisionJournal
from app.goal_engine import GoalEngine
from app.graph_intelligence import GraphIntelligence
from app.memory import Memory
from app.models import ContentIdea, ContentTask, EditorialPlan
from app.task_engine import TaskEngine


logger = logging.getLogger(__name__)


@dataclass
class AutonomousDailyBriefing:
    focus_of_day: str
    top_priorities: list[str]
    suggested_content_idea: str
    task_recommendations: list[str]
    business_recommendation: str
    risk_blocker: str
    next_action: str


class AutonomousDailyWorker:
    """Creates Michele's proactive daily business/content briefing."""

    def __init__(self, db: Session):
        self.db = db
        self.memory = Memory(db)
        self.brain_core = BrainCore(db)
        self.goal_engine = GoalEngine(db)
        self.task_engine = TaskEngine(db)
        self.decision_journal = DecisionJournal(db)
        self.graph_intelligence = GraphIntelligence(db)

    def generate(self) -> AutonomousDailyBriefing:
        logger.info("AutonomousDailyWorker started")
        active_goals = self.goal_engine.list_active_goals(limit=8)
        pending_tasks = self.goal_engine.prioritize_tasks_by_goals(self.task_engine.list_pending_tasks(limit=15))
        editorial_items = self._editorial_items(limit=8)
        recent_decisions = self.decision_journal.latest_decisions(limit=5)
        recent_memories = self.memory.list_long_term_memories(limit=8)
        memory_context = self.memory.build_context_from_memory(
            self.memory.retrieve_relevant_memories(
                "daily worker finance personal brand content monetization goals priorities",
                limit=6,
            )
        )
        brain_state = self.brain_core.get_state_summary().get("summary", "")
        graph_insights = self._graph_insights()

        briefing = AutonomousDailyBriefing(
            focus_of_day=self._focus(active_goals, pending_tasks, editorial_items, brain_state, graph_insights),
            top_priorities=self._priorities(active_goals, pending_tasks, editorial_items),
            suggested_content_idea=self._content_idea(editorial_items, recent_memories, graph_insights),
            task_recommendations=self._task_recommendations(pending_tasks, active_goals),
            business_recommendation=self._business_recommendation(active_goals, recent_decisions, memory_context, graph_insights),
            risk_blocker=self._risk(pending_tasks, editorial_items, recent_decisions, graph_insights),
            next_action=self._next_action(pending_tasks, editorial_items),
        )
        logger.info("AutonomousDailyWorker completed priorities=%s", len(briefing.top_priorities))
        return briefing

    def format_for_telegram(self, briefing: AutonomousDailyBriefing) -> str:
        return (
            "Buongiorno Michele.\n\n"
            f"Oggi il focus è: {briefing.focus_of_day}\n\n"
            "Priorità:\n"
            f"{self._numbered(briefing.top_priorities[:3])}\n\n"
            "Contenuto suggerito:\n"
            f"- {briefing.suggested_content_idea}\n\n"
            "Task consigliati:\n"
            f"{self._bullets(briefing.task_recommendations[:3])}\n\n"
            "Raccomandazione business:\n"
            f"{briefing.business_recommendation}\n\n"
            "Rischio da controllare:\n"
            f"{briefing.risk_blocker}\n\n"
            "Prossima azione:\n"
            f"{briefing.next_action}"
        )

    def run(self) -> str:
        return self.format_for_telegram(self.generate())

    def _editorial_items(self, limit: int) -> list[Any]:
        plans = self.db.query(EditorialPlan).order_by(EditorialPlan.priority.desc(), EditorialPlan.created_at.desc()).limit(limit).all()
        ideas = self.db.query(ContentIdea).order_by(ContentIdea.priority.desc(), ContentIdea.created_at.desc()).limit(limit).all()
        tasks = self.db.query(ContentTask).order_by(ContentTask.priority.desc(), ContentTask.created_at.desc()).limit(limit).all()
        return [*plans, *ideas, *tasks][:limit]

    def _graph_insights(self) -> dict[str, Any]:
        try:
            return self.graph_intelligence.insights(limit=6)
        except Exception:
            logger.exception("AutonomousDailyWorker graph analysis failed")
            return {}

    def _focus(self, goals: list[Any], tasks: list[Any], editorial_items: list[Any], brain_state: str, graph: dict[str, Any]) -> str:
        weak_goals = graph.get("weakly_connected_goals", [])
        if weak_goals:
            return f"collegare l'obiettivo '{weak_goals[0]['title']}' a un contenuto e a un task concreto."
        if editorial_items:
            return f"pubblicare o preparare un contenuto finance su '{editorial_items[0].title}'."
        if tasks:
            return f"chiudere il task più importante: '{tasks[0].title}'."
        if goals:
            return f"fare avanzare l'obiettivo '{goals[0].title}' con un output visibile."
        if "monet" in brain_state.lower():
            return "trasformare attenzione in lead con un contenuto finance e una CTA semplice."
        return "rafforzare il personal brand finance con un contenuto educativo semplice e utile."

    def _priorities(self, goals: list[Any], tasks: list[Any], editorial_items: list[Any]) -> list[str]:
        priorities = [task.title for task in tasks[:3]]
        if editorial_items and len(priorities) < 3:
            priorities.append(f"Preparare il contenuto: {editorial_items[0].title}")
        if goals and len(priorities) < 3:
            priorities.append(f"Collegare l'esecuzione di oggi a: {goals[0].title}")
        fallbacks = [
            "Scrivere uno script breve su un tema finance ad alta utilità",
            "Aggiungere una CTA chiara per generare conversazioni o lead",
            "Aggiornare il backlog contenuti con una priorità concreta",
        ]
        priorities.extend(item for item in fallbacks if item not in priorities)
        return priorities[:3]

    def _content_idea(self, editorial_items: list[Any], memories: list[Any], graph: dict[str, Any]) -> str:
        if editorial_items:
            item = editorial_items[0]
            hook = getattr(item, "hook", "")
            return f"{item.title}" + (f" - Hook: {hook}" if hook else "")
        opportunities = graph.get("opportunities", [])
        if opportunities:
            return f"Post LinkedIn: cosa manca oggi nel sistema di crescita - {opportunities[0]}"
        if memories:
            return f"Trasforma in post LinkedIn: {memories[0].title}"
        return "Reel/TikTok: 3 errori da evitare quando inizi a investire in ETF"

    def _task_recommendations(self, tasks: list[Any], goals: list[Any]) -> list[str]:
        recommendations = []
        for task in tasks[:3]:
            label = getattr(task, "related_goal", None) or (goals[0].title if goals else "obiettivo da collegare")
            recommendations.append(f"{task.title} -> supporta: {label}")
        if recommendations:
            return recommendations
        return [
            "Creare un task per il contenuto principale di oggi",
            "Creare un task per CTA/lead magnet",
            "Collegare almeno un task a un obiettivo attivo",
        ]

    def _business_recommendation(self, goals: list[Any], decisions: list[Any], memory_context: str, graph: dict[str, Any]) -> str:
        if graph.get("opportunities"):
            return f"Trasforma la prima opportunità del grafo in un task operativo: {graph['opportunities'][0]}"
        if decisions:
            return f"Mantieni coerenza con la decisione recente: {decisions[0].title}."
        if goals:
            return f"Non aprire nuove direzioni oggi: proteggi l'obiettivo '{goals[0].title}' e produci un output misurabile."
        if "newsletter" in memory_context.lower():
            return "Usa la newsletter come ponte tra contenuto educativo e conversione."
        return "Collega il contenuto di oggi a una CTA semplice: DM, commento, newsletter o call."

    def _risk(self, tasks: list[Any], editorial_items: list[Any], decisions: list[Any], graph: dict[str, Any]) -> str:
        if len(tasks) > 8:
            return "troppi task aperti possono ridurre focus: scegli solo tre priorità operative."
        if not editorial_items:
            return "il calendario editoriale è debole: manca un contenuto già pronto da produrre."
        if graph.get("weakly_connected_goals"):
            return "alcuni obiettivi sono poco collegati ai task: rischio di lavorare senza avanzamento misurabile."
        if not decisions:
            return "poche decisioni salvate: rischio di cambiare direzione senza memoria strategica."
        return "il rischio principale è consumare tempo in analisi senza pubblicare un asset concreto."

    def _next_action(self, tasks: list[Any], editorial_items: list[Any]) -> str:
        if tasks:
            return f"Blocca 45 minuti e completa: {tasks[0].title}."
        if editorial_items:
            return f"Trasforma '{editorial_items[0].title}' in uno script da 45 secondi."
        return "Scrivi entro oggi uno script breve sugli ETF con hook, spiegazione e CTA."

    def _numbered(self, items: list[str]) -> str:
        return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))

    def _bullets(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items)
