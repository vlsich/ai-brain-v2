from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.agents.autonomous_daily_worker import AutonomousDailyWorker
from app.brain.graph_exporter import GraphExporter
from app.brain_core import BrainCore
from app.decision_journal import DecisionJournal
from app.goal_engine import GoalEngine
from app.graph_intelligence import GraphIntelligence
from app.knowledge_graph import KnowledgeGraph
from app.proactive_loop import GoalToContentPipeline, ProactiveBrainLoop
from app.task_engine import TaskEngine


@dataclass
class ToolResult:
    handled: bool
    response: str = ""
    tool_name: str = ""
    format_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolRouter:
    def __init__(self, db: Session):
        self.db = db
        self.brain_core = BrainCore(db)
        self.goal_engine = GoalEngine(db)
        self.task_engine = TaskEngine(db)
        self.decision_journal = DecisionJournal(db)
        self.proactive_loop = ProactiveBrainLoop(db)
        self.autonomous_daily_worker = AutonomousDailyWorker(db)
        self.goal_content_pipeline = GoalToContentPipeline(db)
        self.knowledge_graph = KnowledgeGraph(db)
        self.graph_intelligence = GraphIntelligence(db)

    def route(self, message: str, chat_id: str | int | None = None) -> ToolResult:
        normalized = self._normalize(message)

        if self._is_chat_id_request(normalized):
            value = chat_id if chat_id not in (None, "", "default", "api") else "non disponibile"
            return ToolResult(
                handled=True,
                response=f"Il tuo chat id Telegram è:\n{value}",
                tool_name="telegram_chat_id",
                format_message="tool direct chat id",
            )

        if self._matches(normalized, ("mostra obiettivi", "mostrami obiettivi", "mostra gli obiettivi", "quali sono i miei obiettivi")):
            goals = self.goal_engine.list_active_goals(limit=10)
            return ToolResult(
                handled=True,
                response="Obiettivi attivi:\n" + self.goal_engine.format_goals(goals),
                tool_name="goal_engine",
                format_message="tool goal list",
            )

        if self._matches(normalized, ("briefing di oggi", "dammi il focus di oggi", "preparami la giornata", "cosa dovrei fare oggi")):
            briefing = self.proactive_loop.generate_daily_briefing()
            return ToolResult(
                handled=True,
                response=self.proactive_loop.format_for_telegram(briefing),
                tool_name="proactive_loop",
                format_message="proactive daily business briefing",
            )

        if self._matches(normalized, ("genera briefing automatico", "daily worker", "lavora per me oggi")):
            return ToolResult(
                handled=True,
                response=self.autonomous_daily_worker.run(),
                tool_name="autonomous_daily_worker",
                format_message="autonomous daily worker briefing",
            )

        if self._matches(normalized, ("sincronizza obsidian", "aggiorna obsidian", "esporta brain su obsidian")):
            try:
                result = GraphExporter.export_all(db=self.db)
                response = self._format_obsidian_export(result)
            except ValueError as exc:
                response = str(exc)
            except Exception as exc:
                response = f"Export Obsidian non completato.\n\nErrore: {exc}"
            return ToolResult(
                handled=True,
                response=response,
                tool_name="obsidian_exporter",
                format_message="obsidian export summary",
            )

        if self._matches(normalized, ("piano operativo settimanale", "trasforma i miei obiettivi in contenuti", "genera task dai miei obiettivi")):
            result = self.goal_content_pipeline.generate_weekly_plan()
            return ToolResult(
                handled=True,
                response=self.goal_content_pipeline.format_for_telegram(result),
                tool_name="goal_content_pipeline",
                format_message="goal to content weekly execution plan",
            )

        if self._matches(normalized, ("ricostruisci graph", "ricostruisci il graph", "ricostruisci grafo", "ricostruisci il knowledge graph", "rebuild knowledge graph")):
            result = self.knowledge_graph.rebuild(limit=250)
            return ToolResult(
                handled=True,
                response=self.knowledge_graph.format_rebuild_result(result),
                tool_name="knowledge_graph",
                format_message="knowledge graph rebuild",
            )

        if self._matches(normalized, ("analizza il mio brain", "cosa manca nel mio brain", "quali opportunita vedi", "quali opportunità vedi")):
            payload = self.graph_intelligence.insights(limit=10)
            intent = "opportunities" if "opportun" in normalized else "gaps" if "manca" in normalized else "analysis"
            return ToolResult(
                handled=True,
                response=self.graph_intelligence.format_insights(payload, intent=intent),
                tool_name="graph_intelligence",
                format_message="graph intelligence insights",
            )

        if self._matches(normalized, ("mostrami il mio brain state", "brain state", "cosa sai di me", "cosa sto costruendo")):
            state = self.brain_core.get_state_summary()
            return ToolResult(
                handled=True,
                response=self._format_brain_state(state["summary"]),
                tool_name="brain_core",
                format_message="brain state summary",
            )

        if self._matches(normalized, ("ultime decisioni", "mostrami le ultime decisioni", "decisioni recenti")):
            decisions = self.decision_journal.latest_decisions(limit=5)
            return ToolResult(
                handled=True,
                response="Ultime decisioni:\n" + self.decision_journal.format_decisions(decisions),
                tool_name="decision_journal",
                format_message="tool decision list",
            )

        return ToolResult(handled=False)

    def _format_brain_state(self, summary: str) -> str:
        lines = [line.strip() for line in summary.splitlines() if line.strip()]
        preferred = (
            "Identita:",
            "Business profile:",
            "Active strategic goals:",
            "Current priorities:",
            "Brand positioning:",
            "Content pillars:",
            "Strategic decisions:",
        )
        selected = []
        for prefix in preferred:
            match = next((line for line in lines if line.startswith(prefix)), "")
            if match:
                title, _, content = match.partition(":")
                selected.append(f"{title}:\n{content.strip()}")
        if not selected:
            selected = lines[:6]
        return "Questo e cio che so oggi del tuo Brain:\n\n" + "\n\n".join(selected[:8])

    def _format_obsidian_export(self, result: dict[str, Any]) -> str:
        errors = result.get("errors") or []
        lines = [
            "Sync Obsidian completato.",
            "",
            f"File creati: {result.get('files_created', 0)}",
            f"File aggiornati: {result.get('files_updated', 0)}",
            f"Entità esportate: {result.get('entities_exported', 0)}",
            f"Vault: {result.get('vault_path', '')}",
        ]
        if errors:
            lines.extend(["", "Errori:"])
            lines.extend(f"- {error}" for error in errors[:5])
        else:
            lines.extend(["", "Errori: nessuno."])
        return "\n".join(lines)

    def _is_chat_id_request(self, normalized: str) -> bool:
        return normalized in {
            "qual e il mio chat id",
            "qual è il mio chat id",
            "chat id",
            "mio chat id",
            "/chatid",
            "/id",
        }

    def _matches(self, normalized: str, patterns: tuple[str, ...]) -> bool:
        return any(pattern in normalized for pattern in patterns)

    def _normalize(self, text: str) -> str:
        return " ".join(text.lower().strip(" ?!.\n\t").split())
