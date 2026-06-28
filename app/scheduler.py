from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Awaitable, Callable

from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application

from app.brain_core import BrainCore
from app.config import Settings, get_settings
from app.database import SessionLocal
from app.decision_journal import DecisionJournal
from app.goal_engine import GoalEngine
from app.graph_intelligence import GraphIntelligence
from app.knowledge_graph import KnowledgeGraph
from app.memory import Memory
from app.models import ScheduledJobRun
from app.proactive_loop import ProactiveBrainLoop
from app.response_formatter import ResponseFormatter
from app.task_engine import TaskEngine


logger = logging.getLogger(__name__)


SendMessage = Callable[[str], Awaitable[None]]


class AutonomousScheduler:
    def __init__(self, application: Application, settings: Settings | None = None):
        self.application = application
        self.settings = settings or get_settings()
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    def start(self) -> None:
        if not self.settings.scheduler_enabled:
            logger.info("Autonomous scheduler disabled by SCHEDULER_ENABLED=false")
            return
        if not self.settings.telegram_admin_chat_id:
            logger.info("Autonomous scheduler disabled: TELEGRAM_ADMIN_CHAT_ID is missing")
            return
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="ai-brain-autonomous-scheduler")
        logger.info("Autonomous scheduler started")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                await self.run_due_jobs()
            except Exception:
                logger.exception("Autonomous scheduler tick failed")
            await asyncio.sleep(max(30, int(self.settings.scheduler_tick_seconds or 60)))

    async def run_due_jobs(self) -> None:
        now = datetime.now()
        if now.hour >= self.settings.scheduler_daily_briefing_hour:
            await self._run_once_per_day("daily_briefing", now, self._daily_briefing)
            await self._run_once_per_day("brain_state_refresh", now, self._brain_state_refresh)
            await self._run_once_per_day("graph_analysis", now, self._graph_analysis)

        if now.weekday() == 6 and now.hour >= self.settings.scheduler_weekly_review_hour:
            await self._run_once_per_week("weekly_review", now, self._weekly_review)

    async def _run_once_per_day(self, job_name: str, now: datetime, job: Callable[[], str]) -> None:
        period_key = now.strftime("%Y-%m-%d")
        if self._already_ran(job_name, period_key):
            return
        text = await asyncio.to_thread(job)
        await self._send_to_admin(text)
        self._mark_run(job_name, period_key)

    async def _run_once_per_week(self, job_name: str, now: datetime, job: Callable[[], str]) -> None:
        year, week, _ = now.isocalendar()
        period_key = f"{year}-W{week:02d}"
        if self._already_ran(job_name, period_key):
            return
        text = await asyncio.to_thread(job)
        await self._send_to_admin(text)
        self._mark_run(job_name, period_key)

    def _daily_briefing(self) -> str:
        db = SessionLocal()
        try:
            briefing = ProactiveBrainLoop(db).generate_daily_briefing()
            text = ProactiveBrainLoop(db).format_for_telegram(briefing)
            return self._format("scheduled daily briefing", text)
        finally:
            db.close()

    def _weekly_review(self) -> str:
        db = SessionLocal()
        try:
            memory = Memory(db)
            brain_core = BrainCore(db)
            goal_engine = GoalEngine(db)
            task_engine = TaskEngine(db)
            decision_journal = DecisionJournal(db)

            brain_context = brain_core.context_for_agents()
            memory_context = memory.build_context_from_memory(
                memory.retrieve_relevant_memories("weekly review business goals content finance", limit=6)
            )
            pending_tasks = goal_engine.prioritize_tasks_by_goals(task_engine.list_pending_tasks(limit=20))
            completed_tasks = task_engine.list_completed_tasks(days=7, limit=20)
            decisions = decision_journal.latest_decisions(limit=10)

            payload = {
                "progress": self._join_titles(completed_tasks, "Nessun task completato registrato questa settimana."),
                "completed_tasks": self._join_titles(completed_tasks, "Nessun task completato registrato."),
                "decisions": self._join_titles(decisions, "Nessuna decisione nuova registrata."),
                "alignment": self._goal_alignment_summary(brain_context, pending_tasks),
                "recommendations": self._weekly_recommendations(pending_tasks, memory_context),
            }
            review = task_engine.save_weekly_review(payload)
            text = (
                f"Review settimanale #{review.id}\n\n"
                f"Progressi:\n{payload['progress']}\n\n"
                f"Task aperti:\n{self._join_titles(pending_tasks[:6], 'Nessun task aperto.')}\n\n"
                f"Decisioni:\n{payload['decisions']}\n\n"
                f"Allineamento obiettivi:\n{payload['alignment']}\n\n"
                f"Priorita consigliate:\n{payload['recommendations']}"
            )
            return self._format("scheduled weekly review", text)
        finally:
            db.close()

    def _brain_state_refresh(self) -> str:
        db = SessionLocal()
        try:
            state = BrainCore(db).update_state_summary()
            text = (
                "Brain State aggiornato.\n\n"
                f"Versione: {state['version']}\n\n"
                "Il contesto persistente e stato riallineato con memorie, obiettivi, decisioni e priorita."
            )
            return self._format("scheduled brain state refresh", text)
        finally:
            db.close()

    def _graph_analysis(self) -> str:
        db = SessionLocal()
        try:
            KnowledgeGraph(db).refresh_from_current_state(limit=250)
            payload = GraphIntelligence(db).insights(limit=8)
            text = GraphIntelligence(db).format_insights(payload)
            return self._format("scheduled graph intelligence insights", text)
        finally:
            db.close()

    def _already_ran(self, job_name: str, period_key: str) -> bool:
        db = SessionLocal()
        try:
            return (
                db.query(ScheduledJobRun)
                .filter(
                    ScheduledJobRun.job_name == job_name,
                    ScheduledJobRun.period_key == period_key,
                    ScheduledJobRun.status == "completed",
                )
                .first()
                is not None
            )
        finally:
            db.close()

    def _mark_run(self, job_name: str, period_key: str) -> None:
        db = SessionLocal()
        try:
            run = ScheduledJobRun(job_name=job_name, period_key=period_key, status="completed")
            db.add(run)
            db.commit()
        finally:
            db.close()

    async def _send_to_admin(self, text: str) -> None:
        chat_id = self.settings.telegram_admin_chat_id
        if not chat_id:
            return
        for chunk in self._split_message(text):
            try:
                await self.application.bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)
            except TelegramError:
                logger.exception("Scheduled Telegram HTML send failed, falling back to plain text")
                await self.application.bot.send_message(chat_id=chat_id, text=self._strip_html(chunk))

    def _format(self, message: str, text: str) -> str:
        formatter = ResponseFormatter(telegram_max_chars=self.settings.telegram_max_response_chars)
        return formatter.format_telegram(message, text)

    def _split_message(self, text: str) -> list[str]:
        max_length = self.settings.telegram_max_response_chars
        if len(text) <= max_length:
            return [text]
        chunks = []
        current = ""
        for block in text.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            candidate = f"{current}\n\n{block}".strip() if current else block
            if len(candidate) > max_length:
                if current:
                    chunks.append(current)
                current = block[:max_length] if len(block) > max_length else block
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    def _strip_html(self, text: str) -> str:
        return re.sub(r"</?[^>]+>", "", text)

    def _join_titles(self, items: list, empty: str) -> str:
        if not items:
            return empty
        return "\n".join(f"- {getattr(item, 'title', str(item))}" for item in items)

    def _goal_alignment_summary(self, brain_context: str, pending_tasks: list) -> str:
        if pending_tasks:
            return "Le priorita operative sono collegate a contenuti, personal brand, audience e monetizzazione."
        if "monetization" in brain_context.lower() or "monetizzazione" in brain_context.lower():
            return "Gli obiettivi sono chiari, ma servono task operativi collegati alla monetizzazione."
        return "Serve collegare meglio obiettivi, task e output misurabili."

    def _weekly_recommendations(self, pending_tasks: list, memory_context: str) -> str:
        recommendations = [
            "1. Scegliere 3 priorita massime per la settimana.",
            "2. Pubblicare almeno un contenuto finance collegato a una CTA.",
            "3. Collegare ogni nuovo task a un obiettivo attivo.",
        ]
        if len(pending_tasks) > 8:
            recommendations.append("4. Ridurre backlog: chiudere o cancellare task non allineati.")
        if "newsletter" in memory_context.lower():
            recommendations.append("5. Usare la newsletter come ponte tra contenuto e conversione.")
        return "\n".join(recommendations)
