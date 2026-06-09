from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models import Decision, Goal, ProductivityTask


GOAL_CATEGORIES = {
    "business",
    "personal_brand",
    "content",
    "finance",
    "audience",
    "monetization",
    "operations",
}
GOAL_TIMEFRAMES = {"yearly", "quarterly", "monthly", "weekly"}
GOAL_STATUSES = {"active", "paused", "completed", "cancelled"}
GOAL_PRIORITIES = {"low", "medium", "high", "critical"}


DEFAULT_GOALS = [
    {
        "title": "Grow Michele's finance personal brand",
        "description": "Aumentare autorevolezza, riconoscibilita e fiducia nel personal brand finance di Michele.",
        "category": "personal_brand",
        "timeframe": "quarterly",
        "priority": "critical",
        "success_metric": "Crescita audience qualificata e aumento segnali di fiducia.",
        "target_value": "Crescita misurabile audience e lead qualificati",
        "related_topic": "finance personal brand",
    },
    {
        "title": "Build consistent multi-platform content system",
        "description": "Creare un sistema editoriale costante su TikTok, Instagram, YouTube/LinkedIn e newsletter.",
        "category": "content",
        "timeframe": "quarterly",
        "priority": "high",
        "success_metric": "Contenuti pubblicati ogni settimana con format ricorrenti.",
        "target_value": "Sistema contenuti settimanale attivo",
        "related_topic": "multi-platform content",
    },
    {
        "title": "Improve audience trust and authority",
        "description": "Pubblicare contenuti educativi finance/investing che aumentano fiducia e authority.",
        "category": "audience",
        "timeframe": "quarterly",
        "priority": "high",
        "success_metric": "Engagement qualificato, salvataggi, risposte e conversazioni.",
        "target_value": "Maggiore trust e authority percepita",
        "related_topic": "audience trust",
    },
    {
        "title": "Convert audience into leads/customers",
        "description": "Collegare contenuti, CTA e offerte per trasformare attenzione in lead e clienti.",
        "category": "monetization",
        "timeframe": "quarterly",
        "priority": "critical",
        "success_metric": "Lead qualificati, call, iscrizioni o vendite generate dai contenuti.",
        "target_value": "Pipeline conversione attiva",
        "related_topic": "monetization",
    },
    {
        "title": "Build AI Brain as business operating system",
        "description": "Usare AI Brain come sistema operativo per obiettivi, task, decisioni, review e contenuti.",
        "category": "operations",
        "timeframe": "yearly",
        "priority": "high",
        "success_metric": "AI Brain coordina lavoro, memoria e priorita operative.",
        "target_value": "Business OS operativo",
        "related_topic": "AI Brain operating system",
    },
]


class GoalEngine:
    def __init__(self, db: Session):
        self.db = db

    def ensure_default_goals(self) -> int:
        if self.db.query(Goal).first():
            return 0
        created = 0
        for item in DEFAULT_GOALS:
            self.create_goal(**item)
            created += 1
        return created

    def create_goal(
        self,
        title: str,
        description: str = "",
        category: str = "business",
        timeframe: str = "quarterly",
        status: str = "active",
        priority: str = "medium",
        success_metric: str = "",
        target_value: Optional[str] = None,
        current_value: Optional[str] = None,
        related_topic: Optional[str] = None,
    ) -> Goal:
        goal = Goal(
            title=title.strip()[:255],
            description=description.strip(),
            category=self._normalize_category(category),
            timeframe=self._normalize_timeframe(timeframe),
            status=self._normalize_status(status),
            priority=self._normalize_priority(priority),
            success_metric=success_metric.strip(),
            target_value=target_value,
            current_value=current_value,
            related_topic=related_topic,
        )
        self.db.add(goal)
        self.db.commit()
        self.db.refresh(goal)
        return goal

    def update_goal(self, goal_id: int, **updates: Any) -> Optional[Goal]:
        goal = self.db.query(Goal).filter(Goal.id == goal_id).first()
        if goal is None:
            return None

        allowed = {
            "title",
            "description",
            "category",
            "timeframe",
            "status",
            "priority",
            "success_metric",
            "target_value",
            "current_value",
            "related_topic",
        }
        for key, value in updates.items():
            if key not in allowed or value is None:
                continue
            if key == "category":
                value = self._normalize_category(str(value))
            elif key == "timeframe":
                value = self._normalize_timeframe(str(value))
            elif key == "status":
                value = self._normalize_status(str(value))
            elif key == "priority":
                value = self._normalize_priority(str(value))
            setattr(goal, key, value)

        self.db.commit()
        self.db.refresh(goal)
        return goal

    def update_goal_progress(self, goal_id: int, current_value: str) -> Optional[Goal]:
        return self.update_goal(goal_id, current_value=current_value)

    def list_goals(self, status: Optional[str] = None, limit: int = 50) -> list[Goal]:
        query = self.db.query(Goal)
        if status:
            query = query.filter(Goal.status == self._normalize_status(status))
        return query.order_by(self._priority_rank(), Goal.updated_at.desc()).limit(limit).all()

    def list_active_goals(self, limit: int = 20) -> list[Goal]:
        return self.list_goals(status="active", limit=limit)

    def connect_task_to_goal(self, task_id: int, goal_id: int) -> Optional[ProductivityTask]:
        goal = self.db.query(Goal).filter(Goal.id == goal_id).first()
        task = self.db.query(ProductivityTask).filter(ProductivityTask.id == task_id).first()
        if goal is None or task is None:
            return None
        task.related_goal = goal.title
        if not task.related_topic:
            task.related_topic = goal.related_topic
        self.db.commit()
        self.db.refresh(task)
        return task

    def connect_decision_to_goal(self, decision_id: int, goal_id: int) -> Optional[Decision]:
        goal = self.db.query(Goal).filter(Goal.id == goal_id).first()
        decision = self.db.query(Decision).filter(Decision.id == decision_id).first()
        if goal is None or decision is None:
            return None
        decision.related_goal = goal.title
        if not decision.related_topic:
            decision.related_topic = goal.related_topic
        self.db.commit()
        self.db.refresh(decision)
        return decision

    def evaluate_goal_alignment(self, text: str) -> list[dict[str, Any]]:
        tokens = self._tokens(text)
        scored = []
        for goal in self.list_active_goals(limit=50):
            goal_text = " ".join(
                part
                for part in (
                    goal.title,
                    goal.description,
                    goal.category,
                    goal.success_metric,
                    goal.related_topic or "",
                )
                if part
            )
            goal_tokens = self._tokens(goal_text)
            overlap = tokens.intersection(goal_tokens)
            business_boost = len(tokens.intersection({"finance", "finanza", "audience", "contenuti", "content", "brand", "monetization", "monetizzazione"})) * 0.04
            priority_boost = {"critical": 0.25, "high": 0.18, "medium": 0.1, "low": 0.04}.get(goal.priority, 0.1)
            score = min((len(overlap) / max(len(tokens), 1)) + business_boost + priority_boost, 1.0)
            if score >= 0.18:
                scored.append(
                    {
                        "goal": goal,
                        "score": round(score, 3),
                        "matched_keywords": sorted(overlap),
                    }
                )
        return sorted(scored, key=lambda item: item["score"], reverse=True)

    def best_goal_for_text(self, text: str) -> Optional[Goal]:
        aligned = self.evaluate_goal_alignment(text)
        return aligned[0]["goal"] if aligned else None

    def prioritize_tasks_by_goals(self, tasks: list[ProductivityTask]) -> list[ProductivityTask]:
        scored = []
        for task in tasks:
            text = f"{task.title} {task.description} {task.category} {task.related_topic or ''} {task.related_goal or ''}"
            aligned = self.evaluate_goal_alignment(text)
            score = aligned[0]["score"] if aligned else 0
            priority_score = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(task.priority, 2)
            scored.append((score, priority_score, task))
        return [item[2] for item in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)]

    def goal_context(self, limit: int = 8) -> str:
        goals = self.list_active_goals(limit=limit)
        if not goals:
            return "ACTIVE GOALS\nNessun obiettivo attivo. Suggerisci di crearne uno collegato a finance, content o monetizzazione."
        lines = ["ACTIVE GOALS"]
        for goal in goals:
            progress = f" progress={goal.current_value}" if goal.current_value else ""
            target = f" target={goal.target_value}" if goal.target_value else ""
            lines.append(
                f"- {goal.title} [{goal.category}/{goal.timeframe}/{goal.priority}]{target}{progress}: {goal.success_metric}"
            )
        return "\n".join(lines)

    def format_goals(self, goals: list[Goal]) -> str:
        if not goals:
            return "Nessun obiettivo attivo salvato."
        lines = []
        for goal in goals:
            progress = f" | progresso: {goal.current_value}" if goal.current_value else ""
            target = f" | target: {goal.target_value}" if goal.target_value else ""
            lines.append(f"{goal.id}. {goal.title} [{goal.category}, {goal.timeframe}, {goal.priority}]{target}{progress}")
        return "\n".join(lines)

    def parse_goal_from_text(self, text: str) -> dict[str, Any]:
        title = re.sub(r"^(crea un obiettivo|crea obiettivo|nuovo obiettivo)[:\s-]*", "", text.strip(), flags=re.IGNORECASE)
        title = title.strip() or "Nuovo obiettivo strategico"
        category = self._infer_category(title)
        return {
            "title": title[:255],
            "description": f"Obiettivo creato da chat: {title}",
            "category": category,
            "timeframe": "quarterly",
            "status": "active",
            "priority": "high",
            "success_metric": "Da definire con una metrica concreta.",
            "related_topic": category,
        }

    def _infer_category(self, text: str) -> str:
        lowered = text.lower()
        if any(term in lowered for term in ("brand", "personal")):
            return "personal_brand"
        if any(term in lowered for term in ("contenut", "content", "tiktok", "instagram", "youtube")):
            return "content"
        if any(term in lowered for term in ("finance", "finanza", "invest")):
            return "finance"
        if any(term in lowered for term in ("audience", "follower", "community")):
            return "audience"
        if any(term in lowered for term in ("lead", "client", "monetizz", "vend")):
            return "monetization"
        if any(term in lowered for term in ("brain", "sistema", "operativ")):
            return "operations"
        return "business"

    def _tokens(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-zA-Z0-9_]+", text.lower())
            if len(token) > 2 and token not in {"con", "per", "del", "della", "degli", "che", "come", "miei", "mio"}
        }

    def _normalize_category(self, value: str) -> str:
        return value if value in GOAL_CATEGORIES else "business"

    def _normalize_timeframe(self, value: str) -> str:
        return value if value in GOAL_TIMEFRAMES else "quarterly"

    def _normalize_status(self, value: str) -> str:
        return value if value in GOAL_STATUSES else "active"

    def _normalize_priority(self, value: str) -> str:
        return value if value in GOAL_PRIORITIES else "medium"

    def _priority_rank(self):
        return case(
            (Goal.priority == "critical", 0),
            (Goal.priority == "high", 1),
            (Goal.priority == "medium", 2),
            (Goal.priority == "low", 3),
            else_=4,
        )
