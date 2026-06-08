from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.agents.content_planner import ContentPlannerAgent
from app.brain_core import BrainCore
from app.config import get_settings
from app.memory import Memory
from app.models import ContentIdea, ContentTask, EditorialPlan


class EditorialCalendar:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.memory = Memory(db)
        self.brain_core = BrainCore(db)
        self.planner = ContentPlannerAgent(self.settings)

    def create_weekly_plan(self, prompt: str) -> dict[str, Any]:
        memories = self.memory.retrieve_relevant_memories(prompt, limit=6)
        memory_context = self.memory.build_context_from_memory(memories)
        brain_context = self.brain_core.context_for_agents()
        payload = self.planner.plan_week(prompt, brain_context=brain_context, memory_context=memory_context)
        saved = self.save_planner_payload(payload)

        return {
            **saved,
            "memories_used": memories,
        }

    def save_planner_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        plans = [self._save_plan(item) for item in payload.get("plans", [])]
        ideas = [self._save_idea(item) for item in payload.get("ideas", [])]
        tasks = [self._save_task(item) for item in payload.get("tasks", [])]

        return {
            "plans": plans,
            "ideas": ideas,
            "tasks": tasks,
            "summary": self._summary(plans, ideas, tasks),
        }

    def list_ideas(
        self,
        status: Optional[str] = None,
        platform: Optional[str] = None,
        limit: int = 50,
    ) -> list[ContentIdea]:
        query = self.db.query(ContentIdea).order_by(ContentIdea.priority.desc(), ContentIdea.created_at.desc())
        if status:
            query = query.filter(ContentIdea.status == status)
        if platform:
            query = query.filter(ContentIdea.platform.ilike(f"%{platform}%"))
        return query.limit(limit).all()

    def list_tasks(
        self,
        status: Optional[str] = None,
        platform: Optional[str] = None,
        limit: int = 50,
    ) -> list[ContentTask]:
        query = self.db.query(ContentTask).order_by(ContentTask.priority.desc(), ContentTask.due_date.asc())
        if status:
            query = query.filter(ContentTask.status == status)
        if platform:
            query = query.filter(ContentTask.platform.ilike(f"%{platform}%"))
        return query.limit(limit).all()

    def _save_plan(self, item: dict[str, Any]) -> EditorialPlan:
        existing = self._find_existing(EditorialPlan, item)
        if existing:
            return existing
        model = EditorialPlan(**self._model_payload(item, default_status="planned"))
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def _save_idea(self, item: dict[str, Any]) -> ContentIdea:
        existing = self._find_existing(ContentIdea, item)
        if existing:
            return existing
        model = ContentIdea(**self._model_payload(item, default_status="idea"))
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def _save_task(self, item: dict[str, Any]) -> ContentTask:
        existing = self._find_existing(ContentTask, item)
        if existing:
            return existing
        model = ContentTask(**self._model_payload(item, default_status="todo"))
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def _find_existing(self, model: type, item: dict[str, Any]):
        return (
            self.db.query(model)
            .filter(
                model.title == item["title"],
                model.platform == item["platform"],
                model.content_type == item["content_type"],
            )
            .first()
        )

    def _model_payload(self, item: dict[str, Any], default_status: str) -> dict[str, Any]:
        return {
            "title": item["title"],
            "platform": item["platform"],
            "content_type": item["content_type"],
            "objective": item["objective"],
            "target_audience": item["target_audience"],
            "hook": item["hook"],
            "status": item.get("status") or default_status,
            "priority": item["priority"],
            "due_date": self._parse_due_date(item.get("due_date")),
        }

    def _parse_due_date(self, value: Optional[str]):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None

    def _summary(self, plans: list[EditorialPlan], ideas: list[ContentIdea], tasks: list[ContentTask]) -> str:
        return (
            f"Piano editoriale creato: {len(plans)} contenuti pianificati, "
            f"{len(ideas)} idee contenuto e {len(tasks)} task operativi."
        )
