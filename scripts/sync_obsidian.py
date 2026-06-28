#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


AI_SECTION_START = "<!-- AI_BRAIN_START -->"
AI_SECTION_END = "<!-- AI_BRAIN_END -->"

FOLDERS = (
    "00 Home",
    "01 Goals",
    "02 Projects",
    "04 Knowledge",
    "07 Decisions",
    "08 Tasks",
)

CORE_WIKILINKS = ("Personal Brand", "ETF", "LinkedIn", "Monetization")


@dataclass
class SyncStats:
    files_created: int = 0
    files_updated: int = 0
    errors: list[str] = field(default_factory=list)
    skipped_endpoints: list[str] = field(default_factory=list)


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any | None:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.base_url}{path}{query}"
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise RuntimeError(f"{path}: HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"{path}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{path}: invalid JSON response") from exc


class LocalObsidianSync:
    def __init__(self, api_base_url: str, vault_path: str):
        self.client = ApiClient(api_base_url)
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.stats = SyncStats()

    def sync(self) -> SyncStats:
        self._ensure_folders()
        payload = self._fetch_payload()
        self._write_home(payload)
        self._write_goals(payload["goals"])
        self._write_projects(payload)
        self._write_knowledge(payload["graph"])
        self._write_decisions(payload["decisions"])
        self._write_tasks(payload["tasks"])
        return self.stats

    def _fetch_payload(self) -> dict[str, Any]:
        return {
            "graph": self._fetch_optional("/graph", default={"nodes": [], "edges": []}),
            "goals": self._fetch_optional("/goals", params={"limit": 100}, default=[]),
            "tasks": self._fetch_tasks(),
            "decisions": self._fetch_optional("/decisions", params={"limit": 100}, default=[]),
            "brain_state": self._fetch_optional("/brain/state", default={}),
        }

    def _fetch_tasks(self) -> list[dict[str, Any]]:
        tasks = self._fetch_optional("/tasks", params={"limit": 100}, default=None)
        if tasks is not None:
            return tasks
        return self._fetch_optional("/productivity/tasks/pending", params={"limit": 100}, default=[])

    def _fetch_optional(self, path: str, default: Any, params: dict[str, Any] | None = None) -> Any:
        try:
            payload = self.client.get(path, params=params)
        except Exception as exc:
            self.stats.errors.append(str(exc))
            return default
        if payload is None:
            self.stats.skipped_endpoints.append(path)
            return default
        return payload

    def _ensure_folders(self) -> None:
        self.vault_path.mkdir(parents=True, exist_ok=True)
        for folder in FOLDERS:
            (self.vault_path / folder).mkdir(parents=True, exist_ok=True)

    def _write_home(self, payload: dict[str, Any]) -> None:
        goals = [item.get("title", "") for item in payload["goals"] if item.get("status") == "active"]
        tasks = [item.get("title", "") for item in payload["tasks"]]
        projects = self._project_names(payload)
        body = "\n".join(
            [
                "# AI Brain Home",
                "",
                f"Last update: {self._now()}",
                "",
                "## Active Goals",
                self._wikilink_list(goals),
                "",
                "## Active Projects",
                self._wikilink_list(projects),
                "",
                "## Current Priorities",
                self._wikilink_list(tasks[:10]),
                "",
                "## Core Links",
                self._wikilink_list(CORE_WIKILINKS),
                "",
                "## Brain State",
                self._brain_state_text(payload["brain_state"]),
            ]
        )
        self._write_note(self.vault_path / "00 Home" / "Home.md", body)

    def _write_goals(self, goals: list[dict[str, Any]]) -> None:
        for goal in goals:
            title = goal.get("title") or f"Goal {goal.get('id', '')}".strip()
            connected = [goal.get("related_topic"), goal.get("category"), *CORE_WIKILINKS]
            body = "\n".join(
                [
                    f"# {title}",
                    "",
                    "Type: Goal",
                    "",
                    f"Status: {self._title(goal.get('status'))}",
                    "",
                    f"Priority: {self._title(goal.get('priority'))}",
                    "",
                    f"Timeframe: {goal.get('timeframe') or ''}",
                    "",
                    "## Connected",
                    self._wikilink_list(connected),
                    "",
                    "## Notes",
                    goal.get("description") or "Generated automatically by AI Brain.",
                    "",
                    f"Success metric: {goal.get('success_metric') or ''}",
                ]
            )
            self._write_note(self.vault_path / "01 Goals" / f"{self._safe_filename(title)}.md", body)

    def _write_projects(self, payload: dict[str, Any]) -> None:
        for project in self._project_names(payload):
            connected = self._project_connections(project, payload)
            body = "\n".join(
                [
                    f"# {project}",
                    "",
                    "Type: Project",
                    "",
                    "Status: Active",
                    "",
                    "## Connected",
                    self._wikilink_list(connected),
                    "",
                    "## Notes",
                    "Generated automatically from Railway AI Brain data.",
                ]
            )
            self._write_note(self.vault_path / "02 Projects" / f"{self._safe_filename(project)}.md", body)

    def _write_knowledge(self, graph: dict[str, Any]) -> None:
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
        edges = graph.get("edges", []) if isinstance(graph, dict) else []
        node_by_id = {node.get("id"): node for node in nodes}
        skip_types = {"goal", "project", "task", "decision", "person"}
        for node in nodes:
            node_type = str(node.get("type") or "knowledge")
            if node_type in skip_types:
                continue
            title = node.get("title") or f"Knowledge {node.get('id', '')}".strip()
            connected = self._connected_node_titles(node.get("id"), edges, node_by_id)
            body = "\n".join(
                [
                    f"# {title}",
                    "",
                    f"Type: {self._title(node_type)}",
                    "",
                    f"Importance: {node.get('importance') or ''}",
                    "",
                    "## Connected",
                    self._wikilink_list(connected),
                    "",
                    "## Notes",
                    node.get("description") or "Generated automatically from the AI Brain Knowledge Graph.",
                ]
            )
            self._write_note(self.vault_path / "04 Knowledge" / f"{self._safe_filename(title)}.md", body)

    def _write_decisions(self, decisions: list[dict[str, Any]]) -> None:
        for decision in decisions:
            title = decision.get("title") or f"Decision {decision.get('id', '')}".strip()
            connected = [decision.get("related_goal"), decision.get("related_project"), decision.get("related_topic")]
            body = "\n".join(
                [
                    f"# {title}",
                    "",
                    "Type: Decision",
                    "",
                    f"Created at: {decision.get('created_at') or ''}",
                    "",
                    "## Connected",
                    self._wikilink_list(connected),
                    "",
                    "## Notes",
                    f"Context: {decision.get('context') or ''}",
                    "",
                    f"Decision: {decision.get('decision') or ''}",
                    "",
                    f"Reasoning: {decision.get('reasoning') or ''}",
                    "",
                    f"Expected outcome: {decision.get('expected_outcome') or ''}",
                ]
            )
            self._write_note(self.vault_path / "07 Decisions" / f"{self._safe_filename(title)}.md", body)

    def _write_tasks(self, tasks: list[dict[str, Any]]) -> None:
        for task in tasks:
            title = task.get("title") or f"Task {task.get('id', '')}".strip()
            connected = [task.get("related_goal"), task.get("related_project"), task.get("related_topic")]
            body = "\n".join(
                [
                    f"# {title}",
                    "",
                    "Type: Task",
                    "",
                    f"Status: {self._title(task.get('status'))}",
                    "",
                    f"Priority: {self._title(task.get('priority'))}",
                    "",
                    f"Due date: {task.get('due_date') or ''}",
                    "",
                    "## Connected",
                    self._wikilink_list(connected),
                    "",
                    "## Notes",
                    task.get("description") or "Generated automatically by AI Brain.",
                ]
            )
            self._write_note(self.vault_path / "08 Tasks" / f"{self._safe_filename(title)}.md", body)

    def _write_note(self, path: Path, body: str) -> None:
        generated = f"{AI_SECTION_START}\n{body.strip()}\n{AI_SECTION_END}\n"
        if not path.exists():
            path.write_text(generated, encoding="utf-8")
            self.stats.files_created += 1
            return

        existing = path.read_text(encoding="utf-8")
        if AI_SECTION_START in existing and AI_SECTION_END in existing:
            pattern = re.compile(f"{re.escape(AI_SECTION_START)}.*?{re.escape(AI_SECTION_END)}", re.DOTALL)
            updated = pattern.sub(generated.strip(), existing, count=1)
        else:
            updated = f"{existing.rstrip()}\n\n{generated}" if existing.strip() else generated

        if updated != existing:
            path.write_text(updated, encoding="utf-8")
            self.stats.files_updated += 1

    def _project_names(self, payload: dict[str, Any]) -> list[str]:
        names = set()
        for task in payload["tasks"]:
            if task.get("related_project"):
                names.add(task["related_project"])
        for decision in payload["decisions"]:
            if decision.get("related_project"):
                names.add(decision["related_project"])
        graph = payload["graph"] if isinstance(payload["graph"], dict) else {}
        for node in graph.get("nodes", []):
            if node.get("type") == "project" and node.get("title"):
                names.add(node["title"])
        return sorted(names)

    def _project_connections(self, project: str, payload: dict[str, Any]) -> list[str]:
        links = []
        for task in payload["tasks"]:
            if task.get("related_project") == project:
                links.extend([task.get("title"), task.get("related_goal"), task.get("related_topic")])
        for decision in payload["decisions"]:
            if decision.get("related_project") == project:
                links.extend([decision.get("title"), decision.get("related_goal"), decision.get("related_topic")])
        return self._clean_links(links)

    def _connected_node_titles(self, node_id: Any, edges: list[dict[str, Any]], node_by_id: dict[Any, dict[str, Any]]) -> list[str]:
        links = []
        for edge in edges:
            source = edge.get("source") or edge.get("source_node_id")
            target = edge.get("target") or edge.get("target_node_id")
            if source == node_id:
                links.append(node_by_id.get(target, {}).get("title"))
            elif target == node_id:
                links.append(node_by_id.get(source, {}).get("title"))
        return self._clean_links(links)

    def _brain_state_text(self, brain_state: Any) -> str:
        if isinstance(brain_state, dict):
            return str(brain_state.get("summary") or brain_state.get("state") or "No brain state available.")
        return "No brain state available."

    def _wikilink_list(self, values: Any) -> str:
        links = [f"[[{value}]]" for value in self._clean_links(values)]
        return "\n".join(links) if links else "No connected notes yet."

    def _clean_links(self, values: Any) -> list[str]:
        if values is None:
            return []
        if isinstance(values, str):
            values = [values]
        clean = []
        seen = set()
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            clean.append(text)
        return clean

    def _safe_filename(self, title: str) -> str:
        clean = re.sub(r"[\\/:*?\"<>|#^[\\]]+", "-", title).strip(" .-")
        clean = re.sub(r"\s+", " ", clean)
        return clean[:120] or "Untitled"

    def _title(self, value: Any) -> str:
        return str(value or "").replace("_", " ").title()

    def _now(self) -> str:
        return datetime.now().replace(microsecond=0).isoformat()


def load_local_env() -> None:
    env_file = Path(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    load_local_env()
    api_base_url = os.getenv("AI_BRAIN_API_BASE_URL", "").strip()
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()

    errors = []
    if not api_base_url:
        errors.append("AI_BRAIN_API_BASE_URL non configurato.")
    if not vault_path:
        errors.append("OBSIDIAN_VAULT_PATH non configurato.")
    if errors:
        for error in errors:
            print(f"Errore: {error}")
        return 1

    try:
        stats = LocalObsidianSync(api_base_url, vault_path).sync()
    except Exception as exc:
        print(f"Errore: {exc}")
        return 1

    print("Obsidian sync completed.")
    print(f"Files created: {stats.files_created}")
    print(f"Files updated: {stats.files_updated}")
    if stats.skipped_endpoints:
        print("Skipped endpoints:")
        for endpoint in stats.skipped_endpoints:
            print(f"- {endpoint}")
    print(f"Errors: {len(stats.errors)}")
    for error in stats.errors:
        print(f"- {error}")
    return 0 if not stats.errors else 2


if __name__ == "__main__":
    sys.exit(main())
