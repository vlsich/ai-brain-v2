from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models import DailyReview, ProductivityTask, WeeklyReview


TASK_STATUSES = {"pending", "in_progress", "completed", "cancelled"}
TASK_PRIORITIES = {"low", "medium", "high", "critical"}


class TaskEngine:
    def __init__(self, db: Session):
        self.db = db

    def create_task(
        self,
        title: str,
        description: str = "",
        category: str = "business",
        priority: str = "medium",
        status: str = "pending",
        estimated_minutes: int = 30,
        due_date: Optional[datetime] = None,
        related_goal: Optional[str] = None,
        related_project: Optional[str] = None,
        related_topic: Optional[str] = None,
    ) -> ProductivityTask:
        task = ProductivityTask(
            title=title.strip()[:255],
            description=description.strip(),
            category=category.strip()[:64] or "business",
            priority=self._normalize_priority(priority),
            status=self._normalize_status(status),
            estimated_minutes=max(5, min(int(estimated_minutes or 30), 480)),
            due_date=due_date,
            related_goal=related_goal,
            related_project=related_project,
            related_topic=related_topic,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def update_task(self, task_id: int, **updates: Any) -> Optional[ProductivityTask]:
        task = self.db.query(ProductivityTask).filter(ProductivityTask.id == task_id).first()
        if task is None:
            return None

        allowed_fields = {
            "title",
            "description",
            "category",
            "priority",
            "status",
            "estimated_minutes",
            "due_date",
            "related_goal",
            "related_project",
            "related_topic",
        }
        for key, value in updates.items():
            if key not in allowed_fields or value is None:
                continue
            if key == "priority":
                value = self._normalize_priority(str(value))
            if key == "status":
                value = self._normalize_status(str(value))
            setattr(task, key, value)

        self.db.commit()
        self.db.refresh(task)
        return task

    def complete_task(self, task_id: int) -> Optional[ProductivityTask]:
        task = self.db.query(ProductivityTask).filter(ProductivityTask.id == task_id).first()
        if task is None:
            return None

        task.status = "completed"
        task.completed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(task)
        return task

    def complete_task_from_text(self, text: str) -> Optional[ProductivityTask]:
        task_id = self._extract_task_id(text)
        if task_id:
            return self.complete_task(task_id)

        title_hint = (
            text.lower()
            .replace("segna task completato", "")
            .replace("segna come completato", "")
            .replace("completa task", "")
            .strip(" :#")
        )
        if not title_hint:
            return None

        task = (
            self.db.query(ProductivityTask)
            .filter(ProductivityTask.status != "completed", ProductivityTask.title.ilike(f"%{title_hint}%"))
            .order_by(self._priority_rank(), ProductivityTask.created_at.desc())
            .first()
        )
        return self.complete_task(task.id) if task else None

    def list_pending_tasks(self, limit: int = 20) -> list[ProductivityTask]:
        return (
            self.db.query(ProductivityTask)
            .filter(ProductivityTask.status.in_(("pending", "in_progress")))
            .order_by(ProductivityTask.due_date.asc(), self._priority_rank(), ProductivityTask.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_today_tasks(self, limit: int = 10) -> list[ProductivityTask]:
        now = datetime.utcnow()
        tomorrow = now + timedelta(days=1)
        tasks = (
            self.db.query(ProductivityTask)
            .filter(
                ProductivityTask.status.in_(("pending", "in_progress")),
                ProductivityTask.due_date.isnot(None),
                ProductivityTask.due_date <= tomorrow,
            )
            .order_by(self._priority_rank(), ProductivityTask.due_date.asc())
            .limit(limit)
            .all()
        )
        return tasks or self.list_high_priority_tasks(limit=limit)

    def list_high_priority_tasks(self, limit: int = 10) -> list[ProductivityTask]:
        return (
            self.db.query(ProductivityTask)
            .filter(
                ProductivityTask.status.in_(("pending", "in_progress")),
                ProductivityTask.priority.in_(("high", "critical")),
            )
            .order_by(self._priority_rank(), ProductivityTask.due_date.asc(), ProductivityTask.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_completed_tasks(self, days: int = 7, limit: int = 30) -> list[ProductivityTask]:
        since = datetime.utcnow() - timedelta(days=days)
        return (
            self.db.query(ProductivityTask)
            .filter(ProductivityTask.status == "completed", ProductivityTask.completed_at >= since)
            .order_by(ProductivityTask.completed_at.desc())
            .limit(limit)
            .all()
        )

    def ensure_foundation_tasks(self, brain_context: str, memory_context: str) -> list[ProductivityTask]:
        if self.list_pending_tasks(limit=1):
            return []

        context = f"{brain_context}\n{memory_context}".lower()
        foundation = [
            {
                "title": "Definire priorita contenuti finance della settimana",
                "description": "Scegliere 1 obiettivo business, 1 canale principale e 3 contenuti ad alto impatto.",
                "category": "content",
                "priority": "high",
                "estimated_minutes": 30,
                "related_goal": "personal brand finance",
                "related_project": "content engine",
                "related_topic": "content creation",
            },
            {
                "title": "Preparare un contenuto educativo su investimenti",
                "description": "Creare hook, struttura e CTA per trasformare attenzione in lead qualificati.",
                "category": "finance_content",
                "priority": "high",
                "estimated_minutes": 45,
                "related_goal": "audience building",
                "related_project": "personal brand",
                "related_topic": "investing",
            },
            {
                "title": "Rivedere offerta e CTA di monetizzazione",
                "description": "Collegare i contenuti della settimana a newsletter, prodotto o consulenza.",
                "category": "monetization",
                "priority": "medium",
                "estimated_minutes": 40,
                "related_goal": "monetization",
                "related_project": "business growth",
                "related_topic": "conversion",
            },
        ]
        if "newsletter" in context:
            foundation.append(
                {
                    "title": "Scrivere bozza newsletter finance",
                    "description": "Trasformare un insight di educazione finanziaria in email utile e convertente.",
                    "category": "newsletter",
                    "priority": "medium",
                    "estimated_minutes": 45,
                    "related_goal": "audience nurturing",
                    "related_project": "newsletter",
                    "related_topic": "finance education",
                }
            )

        today = datetime.utcnow()
        return [
            self.create_task(**item, due_date=today + timedelta(days=index))
            for index, item in enumerate(foundation)
        ]

    def save_daily_review(
        self,
        payload: dict[str, str],
        related_goal: Optional[str] = "business growth",
        related_project: Optional[str] = "AI Brain productivity",
        related_topic: Optional[str] = "daily review",
    ) -> DailyReview:
        review = DailyReview(
            wins=payload.get("wins", ""),
            blockers=payload.get("blockers", ""),
            priorities=payload.get("priorities", ""),
            recommendations=payload.get("recommendations", ""),
            related_goal=related_goal,
            related_project=related_project,
            related_topic=related_topic,
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return review

    def save_weekly_review(
        self,
        payload: dict[str, str],
        related_goal: Optional[str] = "business growth",
        related_project: Optional[str] = "AI Brain productivity",
        related_topic: Optional[str] = "weekly review",
    ) -> WeeklyReview:
        review = WeeklyReview(
            progress=payload.get("progress", ""),
            completed_tasks=payload.get("completed_tasks", ""),
            decisions=payload.get("decisions", ""),
            alignment=payload.get("alignment", ""),
            recommendations=payload.get("recommendations", ""),
            related_goal=related_goal,
            related_project=related_project,
            related_topic=related_topic,
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return review

    def format_tasks(self, tasks: list[ProductivityTask], empty_message: str) -> str:
        if not tasks:
            return empty_message

        lines = []
        for task in tasks:
            due = task.due_date.strftime("%d/%m") if task.due_date else "senza scadenza"
            lines.append(
                f"{task.id}. {task.title} [{task.priority}] - {task.estimated_minutes} min - {due}"
            )
        return "\n".join(lines)

    def _extract_task_id(self, text: str) -> Optional[int]:
        match = re.search(r"#?(\d+)", text)
        return int(match.group(1)) if match else None

    def _normalize_status(self, status: str) -> str:
        return status if status in TASK_STATUSES else "pending"

    def _normalize_priority(self, priority: str) -> str:
        return priority if priority in TASK_PRIORITIES else "medium"

    def _priority_rank(self):
        return case(
            (ProductivityTask.priority == "critical", 0),
            (ProductivityTask.priority == "high", 1),
            (ProductivityTask.priority == "medium", 2),
            (ProductivityTask.priority == "low", 3),
            else_=4,
        )
