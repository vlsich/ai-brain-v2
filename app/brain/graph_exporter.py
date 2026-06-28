from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import (
    BrainState,
    ContentIdea,
    ContentTask,
    Decision,
    EditorialPlan,
    Goal,
    KnowledgeEdge,
    KnowledgeNode,
    LongTermMemory,
    ProductivityTask,
)


logger = logging.getLogger(__name__)


AI_SECTION_START = "<!-- AI_BRAIN_START -->"
AI_SECTION_END = "<!-- AI_BRAIN_END -->"


VAULT_FOLDERS = (
    "01 Goals",
    "02 Projects",
    "03 Areas",
    "04 Knowledge",
    "05 People",
    "06 Content",
    "07 Decisions",
    "08 Tasks",
    "09 Daily",
)


@dataclass
class ExportItem:
    title: str
    folder: str
    entity_type: str
    fields: dict[str, Any] = field(default_factory=dict)
    connected: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ExportSummary:
    vault_path: str
    files_created: int
    files_updated: int
    folders_created: int
    entities_exported: int
    updated_at: str
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "vault_path": self.vault_path,
            "files_created": self.files_created,
            "files_updated": self.files_updated,
            "files_written": self.files_created + self.files_updated,
            "folders_created": self.folders_created,
            "entities_exported": self.entities_exported,
            "updated_at": self.updated_at,
            "errors": self.errors,
        }


class GraphExporter:
    """Exports AI Brain entities to an Obsidian vault without overwriting manual notes."""

    @classmethod
    def export_all(
        cls,
        vault_path: str | Path | None = None,
        db: Session | None = None,
    ) -> dict[str, Any]:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            exporter = cls(session, vault_path=vault_path)
            return exporter._export_all().as_dict()
        finally:
            if owns_session:
                session.close()

    def __init__(self, db: Session, vault_path: str | Path | None = None):
        self.db = db
        self.settings = get_settings()
        configured_path = vault_path or self.settings.obsidian_vault_path
        if not configured_path:
            raise ValueError("OBSIDIAN_VAULT_PATH non configurato.")
        self.vault_path = Path(configured_path).expanduser().resolve()

    def _export_all(self) -> ExportSummary:
        started_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        folders_created = self._ensure_folders()
        items = self._collect_items()
        files_created = 0
        files_updated = 0
        errors = []

        for item in items:
            try:
                status = self._write_item(item, updated_at=started_at)
                files_created += int(status == "created")
                files_updated += int(status == "updated")
            except Exception as exc:
                logger.exception("Obsidian note export failed title=%s", item.title)
                errors.append(f"{item.title}: {exc}")

        try:
            home_status = self._write_home(items, updated_at=started_at)
            files_created += int(home_status == "created")
            files_updated += int(home_status == "updated")
        except Exception as exc:
            logger.exception("Obsidian Home export failed")
            errors.append(f"Home.md: {exc}")
        summary = ExportSummary(
            vault_path=str(self.vault_path),
            files_created=files_created,
            files_updated=files_updated,
            folders_created=folders_created,
            entities_exported=len(items),
            updated_at=started_at,
            errors=errors,
        )
        logger.info("Obsidian export completed: %s", summary.as_dict())
        return summary

    def _ensure_folders(self) -> int:
        created = 0
        self.vault_path.mkdir(parents=True, exist_ok=True)
        for folder in VAULT_FOLDERS:
            path = self.vault_path / folder
            if not path.exists():
                created += 1
            path.mkdir(parents=True, exist_ok=True)
        return created

    def _collect_items(self) -> list[ExportItem]:
        items: list[ExportItem] = []
        items.extend(self._goal_items())
        items.extend(self._task_items())
        items.extend(self._project_items())
        items.extend(self._knowledge_items())
        items.extend(self._decision_items())
        items.extend(self._content_items())
        items.extend(self._brain_state_items())
        return items

    def _goal_items(self) -> list[ExportItem]:
        goals = self.db.query(Goal).order_by(Goal.updated_at.desc()).all()
        return [
            ExportItem(
                title=goal.title,
                folder="01 Goals",
                entity_type="Goal",
                fields={
                    "Status": self._title(goal.status),
                    "Priority": self._title(goal.priority),
                    "Category": goal.category,
                    "Timeframe": goal.timeframe,
                    "Success Metric": goal.success_metric,
                    "Current Value": goal.current_value,
                    "Target Value": goal.target_value,
                },
                connected=self._clean_links([goal.related_topic]),
                notes=[goal.description or "Generated automatically by AI Brain."],
            )
            for goal in goals
        ]

    def _task_items(self) -> list[ExportItem]:
        tasks = self.db.query(ProductivityTask).order_by(ProductivityTask.created_at.desc()).all()
        return [
            ExportItem(
                title=task.title,
                folder="08 Tasks",
                entity_type="Task",
                fields={
                    "Status": self._title(task.status),
                    "Priority": self._title(task.priority),
                    "Category": task.category,
                    "Estimated Minutes": task.estimated_minutes,
                    "Due Date": self._date(task.due_date),
                    "Completed At": self._date(task.completed_at),
                },
                connected=self._clean_links([task.related_goal, task.related_project, task.related_topic]),
                notes=[task.description or "Generated automatically by AI Brain."],
            )
            for task in tasks
        ]

    def _project_items(self) -> list[ExportItem]:
        names = set()
        for value, in self.db.query(ProductivityTask.related_project).filter(ProductivityTask.related_project.isnot(None)).all():
            if value:
                names.add(value)
        for value, in self.db.query(Decision.related_project).filter(Decision.related_project.isnot(None)).all():
            if value:
                names.add(value)
        for node in self.db.query(KnowledgeNode).filter(KnowledgeNode.type == "project").all():
            names.add(node.title)

        return [
            ExportItem(
                title=name,
                folder="02 Projects",
                entity_type="Project",
                fields={"Status": "Active"},
                connected=self._project_links(name),
                notes=["Generated automatically from tasks, decisions and Knowledge Graph project nodes."],
            )
            for name in sorted(names)
        ]

    def _knowledge_items(self) -> list[ExportItem]:
        items: list[ExportItem] = []
        nodes = self.db.query(KnowledgeNode).order_by(KnowledgeNode.importance.desc(), KnowledgeNode.created_at.desc()).all()
        for node in nodes:
            if node.type in {"goal", "project", "task", "decision"}:
                continue
            folder = "05 People" if node.type == "person" else "04 Knowledge"
            items.append(
                ExportItem(
                    title=node.title,
                    folder=folder,
                    entity_type=self._title(node.type),
                    fields={"Importance": node.importance},
                    connected=self._node_links(node.id),
                    notes=[node.description or "Generated automatically from the AI Brain Knowledge Graph."],
                )
            )

        memories = self.db.query(LongTermMemory).order_by(LongTermMemory.importance.desc(), LongTermMemory.created_at.desc()).all()
        for memory in memories:
            items.append(
                ExportItem(
                    title=memory.title,
                    folder="04 Knowledge",
                    entity_type=self._title(memory.memory_type),
                    fields={"Importance": memory.importance, "Source Task ID": memory.source_task_id},
                    connected=[],
                    notes=[memory.content],
                )
            )
        return self._dedupe_items(items)

    def _decision_items(self) -> list[ExportItem]:
        decisions = self.db.query(Decision).order_by(Decision.created_at.desc()).all()
        return [
            ExportItem(
                title=decision.title,
                folder="07 Decisions",
                entity_type="Decision",
                fields={"Created At": self._date(decision.created_at)},
                connected=self._clean_links([decision.related_goal, decision.related_project, decision.related_topic]),
                notes=[
                    f"Context: {decision.context}",
                    f"Decision: {decision.decision}",
                    f"Reasoning: {decision.reasoning}",
                    f"Expected outcome: {decision.expected_outcome}",
                ],
            )
            for decision in decisions
        ]

    def _content_items(self) -> list[ExportItem]:
        items: list[ExportItem] = []
        for model, entity_type in (
            (EditorialPlan, "Editorial Plan"),
            (ContentIdea, "Content Idea"),
            (ContentTask, "Content Task"),
        ):
            rows = self.db.query(model).order_by(model.priority.desc(), model.created_at.desc()).all()
            for row in rows:
                items.append(
                    ExportItem(
                        title=row.title,
                        folder="06 Content",
                        entity_type=entity_type,
                        fields={
                            "Platform": row.platform,
                            "Content Type": row.content_type,
                            "Status": self._title(row.status),
                            "Priority": row.priority,
                            "Due Date": self._date(row.due_date),
                        },
                        connected=self._clean_links([row.platform, row.content_type]),
                        notes=[
                            f"Objective: {row.objective}",
                            f"Target audience: {row.target_audience}",
                            f"Hook: {row.hook}",
                        ],
                    )
                )
        return items

    def _brain_state_items(self) -> list[ExportItem]:
        states = self.db.query(BrainState).order_by(BrainState.updated_at.desc()).all()
        return [
            ExportItem(
                title=f"Brain State - {state.key}",
                folder="04 Knowledge",
                entity_type="Brain State",
                fields={"Version": state.version, "Updated At": self._date(state.updated_at)},
                connected=["AI Brain"],
                notes=[state.summary],
            )
            for state in states
        ]

    def _write_item(self, item: ExportItem, updated_at: str) -> str:
        path = self.vault_path / item.folder / f"{self._safe_filename(item.title)}.md"
        generated = self._render_item(item, updated_at)
        return self._write_ai_section(path, item.title, generated)

    def _write_home(self, items: list[ExportItem], updated_at: str) -> str:
        active_goals = [item.title for item in items if item.entity_type == "Goal" and item.fields.get("Status") == "Active"]
        projects = [item.title for item in items if item.entity_type == "Project"]
        priorities = [
            item.title
            for item in items
            if item.entity_type == "Task" and str(item.fields.get("Priority", "")).lower() in {"critical", "high"}
        ]

        body = "\n".join(
            [
                AI_SECTION_START,
                "# AI Brain Home",
                "",
                f"Last update: {updated_at}",
                "",
                "## Active Goals",
                self._wikilink_list(active_goals[:10]),
                "",
                "## Active Projects",
                self._wikilink_list(projects[:10]),
                "",
                "## Current Priorities",
                self._wikilink_list(priorities[:10]),
                "",
                "## Vault Areas",
                self._wikilink_list(VAULT_FOLDERS),
                AI_SECTION_END,
                "",
            ]
        )
        return self._write_ai_section(self.vault_path / "Home.md", "AI Brain Home", body)

    def _render_item(self, item: ExportItem, updated_at: str) -> str:
        lines = [
            AI_SECTION_START,
            f"# {item.title}",
            "",
            f"Type: {item.entity_type}",
        ]
        for key, value in item.fields.items():
            if value not in (None, ""):
                lines.append("")
                lines.append(f"{key}: {value}")

        lines.extend(["", f"Last update: {updated_at}", "", "## Connected"])
        lines.append(self._wikilink_list(item.connected))
        lines.extend(["", "## Notes"])
        notes = [note.strip() for note in item.notes if str(note).strip()]
        lines.extend(notes or ["Generated automatically by AI Brain."])
        lines.extend(["", AI_SECTION_END, ""])
        return "\n".join(lines)

    def _write_ai_section(self, path: Path, title: str, generated_section: str) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(generated_section, encoding="utf-8")
            logger.info("Obsidian note created: %s title=%s", path, title)
            return "created"

        existing = path.read_text(encoding="utf-8")
        if AI_SECTION_START in existing and AI_SECTION_END in existing:
            pattern = re.compile(f"{re.escape(AI_SECTION_START)}.*?{re.escape(AI_SECTION_END)}", re.DOTALL)
            updated = pattern.sub(generated_section.strip(), existing, count=1)
        else:
            manual_header = existing.rstrip()
            updated = f"{manual_header}\n\n{generated_section}" if manual_header else generated_section

        if updated == existing:
            return "unchanged"
        path.write_text(updated, encoding="utf-8")
        logger.info("Obsidian note synced: %s title=%s", path, title)
        return "updated"

    def _project_links(self, project_name: str) -> list[str]:
        links = []
        tasks = self.db.query(ProductivityTask).filter(ProductivityTask.related_project == project_name).limit(20).all()
        decisions = self.db.query(Decision).filter(Decision.related_project == project_name).limit(20).all()
        links.extend(task.title for task in tasks)
        links.extend(decision.title for decision in decisions)
        return self._clean_links(links)

    def _node_links(self, node_id: int) -> list[str]:
        edges = (
            self.db.query(KnowledgeEdge)
            .filter((KnowledgeEdge.source_node_id == node_id) | (KnowledgeEdge.target_node_id == node_id))
            .limit(30)
            .all()
        )
        linked_ids = []
        for edge in edges:
            linked_ids.append(edge.target_node_id if edge.source_node_id == node_id else edge.source_node_id)
        nodes = self.db.query(KnowledgeNode).filter(KnowledgeNode.id.in_(linked_ids)).all() if linked_ids else []
        return self._clean_links(node.title for node in nodes)

    def _wikilink_list(self, values: Iterable[str]) -> str:
        links = [self._wikilink(value) for value in self._clean_links(values)]
        return "\n".join(links) if links else "No connected notes yet."

    def _wikilink(self, value: str) -> str:
        return f"[[{value}]]"

    def _clean_links(self, values: Iterable[Any]) -> list[str]:
        links = []
        seen = set()
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            links.append(text)
        return links

    def _dedupe_items(self, items: list[ExportItem]) -> list[ExportItem]:
        deduped = []
        seen = set()
        for item in items:
            key = (item.folder, item.title.lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _safe_filename(self, title: str) -> str:
        clean = re.sub(r"[\\/:*?\"<>|#^[\\]]+", "-", title).strip(" .-")
        clean = re.sub(r"\s+", " ", clean)
        return clean[:120] or "Untitled"

    def _date(self, value: Any) -> str:
        if not value:
            return ""
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def _title(self, value: Any) -> str:
        return str(value or "").replace("_", " ").title()
