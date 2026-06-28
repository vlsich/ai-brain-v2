from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    final_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    results: Mapped[list["AgentResult"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )


class AgentResult(Base):
    __tablename__ = "agent_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    output: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    task: Mapped[Task] = relationship(back_populates="results")


class LongTermMemory(Base):
    __tablename__ = "long_term_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    source_task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class BrainState(Base):
    __tablename__ = "brain_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class ConversationState(Base):
    __tablename__ = "conversation_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    chat_id: Mapped[str] = mapped_column(String(128), default="default", nullable=False, index=True)
    active_topic: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    active_task: Mapped[str] = mapped_column(Text, default="", nullable=False)
    active_agent: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    active_intent: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    active_goal: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_assistant_response: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_content_topic: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    last_content_format: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    last_generated_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_output_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    last_user_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_task_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="business", nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(32), default="quarterly", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(32), default="medium", nullable=False, index=True)
    success_metric: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    target_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    current_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    related_topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class EditorialPlan(Base):
    __tablename__ = "editorial_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    target_audience: Mapped[str] = mapped_column(String(255), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False, index=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ContentIdea(Base):
    __tablename__ = "content_ideas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    target_audience: Mapped[str] = mapped_column(String(255), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="idea", nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False, index=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ContentTask(Base):
    __tablename__ = "content_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    target_audience: Mapped[str] = mapped_column(String(255), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="todo", nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False, index=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ProductivityTask(Base):
    __tablename__ = "business_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="business", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(32), default="medium", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    related_goal: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    related_project: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    related_topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    context: Mapped[str] = mapped_column(Text, default="", nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, default="", nullable=False)
    expected_outcome: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    related_goal: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    related_project: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    related_topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)


class DailyReview(Base):
    __tablename__ = "daily_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    wins: Mapped[str] = mapped_column(Text, default="", nullable=False)
    blockers: Mapped[str] = mapped_column(Text, default="", nullable=False)
    priorities: Mapped[str] = mapped_column(Text, default="", nullable=False)
    recommendations: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    related_goal: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    related_project: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    related_topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)


class WeeklyReview(Base):
    __tablename__ = "weekly_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    progress: Mapped[str] = mapped_column(Text, default="", nullable=False)
    completed_tasks: Mapped[str] = mapped_column(Text, default="", nullable=False)
    decisions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    alignment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    recommendations: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    related_goal: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    related_project: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    related_topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
