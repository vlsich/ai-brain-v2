from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.brain_core import BrainCore
from app.config import get_settings
from app.dashboard import DASHBOARD_HTML
from app.database import SessionLocal, get_db, init_db
from app.decision_journal import DecisionJournal
from app.editorial_calendar import EditorialCalendar
from app.goal_engine import GoalEngine
from app.graph_intelligence import GraphIntelligence
from app.knowledge_graph import KnowledgeGraph
from app.memory import Memory
from app.models import DailyReview, WeeklyReview
from app.orchestrator import Orchestrator
from app.response_formatter import ResponseFormatter
from app.semantic_memory import SemanticMemory
from app.task_engine import TaskEngine


settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI(title=settings.app_name)


class TaskRequest(BaseModel):
    task: str = Field(..., min_length=3, examples=["Analizza il mercato AI e crea 3 post LinkedIn"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, examples=["Chi sono?", "Creami una strategia TikTok"])
    chat_id: Optional[str] = Field(default="api", examples=["api", "telegram-123"])


class RetrievedMemoryResponse(BaseModel):
    id: int
    memory_type: str
    title: str
    importance: int
    source_task_id: int
    score: float
    matched_keywords: list[str] = Field(default_factory=list)


class TaskResponse(BaseModel):
    task_id: int
    agents_used: list[str]
    final_answer: str
    results: dict[str, str]
    memories_used: list[RetrievedMemoryResponse] = Field(default_factory=list)
    agents_used_memory: list[str] = Field(default_factory=list)
    memories_saved: int = 0


class ChatResponse(BaseModel):
    reply: str
    agents_used: list[str]
    memories_used: list[RetrievedMemoryResponse] = Field(default_factory=list)
    task_id: int


class LongTermMemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    memory_type: str
    title: str
    content: str
    importance: int
    source_task_id: int
    created_at: datetime


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    memory_type: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=6, ge=1, le=20)


class BrainSeedMemory(BaseModel):
    memory_type: str
    title: str
    content: str
    importance: int = Field(default=4, ge=1, le=5)


class BrainSeedRequest(BaseModel):
    memories: list[BrainSeedMemory] = Field(default_factory=list)


class EditorialPlanRequest(BaseModel):
    prompt: str = Field(
        default="Crea il piano editoriale della settimana per il personal brand finance di Michele",
        min_length=3,
    )


class EditorialItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    platform: str
    content_type: str
    objective: str
    target_audience: str
    hook: str
    status: str
    priority: int
    due_date: Optional[datetime] = None
    created_at: datetime


class EditorialPlanResponse(BaseModel):
    summary: str
    plans: list[EditorialItemResponse]
    ideas: list[EditorialItemResponse]
    tasks: list[EditorialItemResponse]
    memories_used: list[RetrievedMemoryResponse] = Field(default_factory=list)


class ProductivityTaskCreate(BaseModel):
    title: str = Field(..., min_length=3)
    description: str = ""
    category: str = "business"
    priority: str = "medium"
    estimated_minutes: int = Field(default=30, ge=5, le=480)
    due_date: Optional[datetime] = None
    related_goal: Optional[str] = None
    related_project: Optional[str] = None
    related_topic: Optional[str] = None


class ProductivityTaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    estimated_minutes: Optional[int] = Field(default=None, ge=5, le=480)
    due_date: Optional[datetime] = None
    related_goal: Optional[str] = None
    related_project: Optional[str] = None
    related_topic: Optional[str] = None


class ProductivityTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    category: str
    priority: str
    status: str
    estimated_minutes: int
    due_date: Optional[datetime] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    related_goal: Optional[str] = None
    related_project: Optional[str] = None
    related_topic: Optional[str] = None


class DecisionCreate(BaseModel):
    title: str = Field(..., min_length=3)
    context: str = ""
    decision: str = Field(..., min_length=3)
    reasoning: str = ""
    expected_outcome: str = ""
    related_goal: Optional[str] = None
    related_project: Optional[str] = None
    related_topic: Optional[str] = None


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    context: str
    decision: str
    reasoning: str
    expected_outcome: str
    created_at: datetime
    related_goal: Optional[str] = None
    related_project: Optional[str] = None
    related_topic: Optional[str] = None


class DailyReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wins: str
    blockers: str
    priorities: str
    recommendations: str
    created_at: datetime
    related_goal: Optional[str] = None
    related_project: Optional[str] = None
    related_topic: Optional[str] = None


class WeeklyReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    progress: str
    completed_tasks: str
    decisions: str
    alignment: str
    recommendations: str
    created_at: datetime
    related_goal: Optional[str] = None
    related_project: Optional[str] = None
    related_topic: Optional[str] = None


class GoalCreate(BaseModel):
    title: str = Field(..., min_length=3)
    description: str = ""
    category: str = "business"
    timeframe: str = "quarterly"
    status: str = "active"
    priority: str = "medium"
    success_metric: str = ""
    target_value: Optional[str] = None
    current_value: Optional[str] = None
    related_topic: Optional[str] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    timeframe: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    success_metric: Optional[str] = None
    target_value: Optional[str] = None
    current_value: Optional[str] = None
    related_topic: Optional[str] = None


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    category: str
    timeframe: str
    status: str
    priority: str
    success_metric: str
    target_value: Optional[str] = None
    current_value: Optional[str] = None
    related_topic: Optional[str] = None
    created_at: datetime
    updated_at: datetime


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    db = SessionLocal()
    try:
        GoalEngine(db).ensure_default_goals()
        Memory(db).ensure_core_memories()
        BrainCore(db).seed()
        SemanticMemory(db).sync_from_long_term_memory()
        KnowledgeGraph(db).refresh_from_current_state()
    finally:
        db.close()


@app.get("/")
def root() -> dict[str, str]:
    return {"app": settings.app_name, "status": "ok"}


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:
        logger.exception("Health check database failed")
        database_status = "error"

    return {
        "app": settings.app_name,
        "status": "ok" if database_status == "ok" else "degraded",
        "environment": settings.app_env,
        "database": database_status,
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(content=DASHBOARD_HTML)


@app.post("/task", response_model=TaskResponse)
def create_task(payload: TaskRequest, db: Session = Depends(get_db)) -> dict:
    orchestrator = Orchestrator(db)
    formatter = ResponseFormatter(telegram_max_chars=settings.telegram_max_response_chars)
    try:
        result = orchestrator.handle_task(payload.task)
        result["final_answer"] = formatter.format_chat(result.get("format_message", payload.task), result["final_answer"])
        logger.info(
            "Response quality: endpoint=/task agents=%s memories=%s length=%s score=%s",
            ",".join(result["agents_used"]),
            len(result["memories_used"]),
            len(result["final_answer"]),
            formatter.quality_score(result["final_answer"]),
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> dict:
    orchestrator = Orchestrator(db, chat_id=payload.chat_id or "api")
    formatter = ResponseFormatter(telegram_max_chars=settings.telegram_max_response_chars)
    try:
        result = orchestrator.handle_chat(payload.message)
        result["reply"] = formatter.format_chat(result.get("format_message", payload.message), result["reply"])
        logger.info(
            "Response quality: endpoint=/chat agents=%s memories=%s length=%s score=%s",
            ",".join(result["agents_used"]),
            len(result["memories_used"]),
            len(result["reply"]),
            formatter.quality_score(result["reply"]),
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/memory", response_model=list[LongTermMemoryResponse])
def list_memory(
    memory_type: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list:
    memory = Memory(db)
    return memory.list_long_term_memories(memory_type=memory_type, limit=limit)


@app.post("/memory/search", response_model=list[LongTermMemoryResponse])
def search_memory(payload: MemorySearchRequest, db: Session = Depends(get_db)) -> list:
    memory = Memory(db)
    return memory.search_long_term_memories(
        query_text=payload.query,
        memory_type=payload.memory_type,
        limit=payload.limit,
    )


@app.post("/memory/semantic/search")
def search_semantic_memory(payload: SemanticSearchRequest, db: Session = Depends(get_db)) -> list[dict]:
    return SemanticMemory(db).retrieve(payload.query, limit=payload.limit)


@app.get("/brain/state")
def get_brain_state(db: Session = Depends(get_db)) -> dict:
    return BrainCore(db).get_state_summary()


@app.get("/brain/concepts")
def get_related_concepts(query: str = "", limit: int = 12, db: Session = Depends(get_db)) -> dict:
    graph = KnowledgeGraph(db)
    graph.refresh_from_current_state(limit=80)
    return {"concepts": graph.related_concepts(query=query, limit=limit)}


@app.get("/graph/nodes")
def get_graph_nodes(
    type: Optional[str] = None,
    limit: int = 500,
    db: Session = Depends(get_db),
) -> list[dict]:
    return KnowledgeGraph(db).export_nodes(limit=limit, node_type=type)


@app.get("/graph/edges")
def get_graph_edges(limit: int = 1000, db: Session = Depends(get_db)) -> list[dict]:
    return KnowledgeGraph(db).export_edges(limit=limit)


@app.get("/graph")
def get_graph(limit: int = 500, db: Session = Depends(get_db)) -> dict:
    return KnowledgeGraph(db).export_graph(limit=limit)


@app.get("/graph/search")
def search_graph(q: str = "", limit: int = 25, db: Session = Depends(get_db)) -> dict:
    return KnowledgeGraph(db).search_graph(query=q, limit=limit)


@app.post("/graph/rebuild")
def rebuild_graph(limit: int = 250, db: Session = Depends(get_db)) -> dict:
    graph = KnowledgeGraph(db)
    return graph.rebuild(limit=limit)


@app.get("/graph/insights")
def get_graph_insights(limit: int = 10, db: Session = Depends(get_db)) -> dict:
    return GraphIntelligence(db).insights(limit=limit)


@app.get("/graph/clusters")
def get_graph_clusters(limit: int = 10, db: Session = Depends(get_db)) -> dict:
    return GraphIntelligence(db).clusters(limit=limit)


@app.get("/graph/gaps")
def get_graph_gaps(limit: int = 10, db: Session = Depends(get_db)) -> dict:
    return GraphIntelligence(db).gaps(limit=limit)


@app.post("/brain/seed")
def seed_brain(payload: BrainSeedRequest, db: Session = Depends(get_db)) -> dict:
    memories = [memory.model_dump() for memory in payload.memories] if payload.memories else None
    return BrainCore(db).seed(memories=memories)


@app.post("/editorial/plan", response_model=EditorialPlanResponse)
def create_editorial_plan(payload: EditorialPlanRequest, db: Session = Depends(get_db)) -> dict:
    calendar = EditorialCalendar(db)
    try:
        return calendar.create_weekly_plan(payload.prompt)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/editorial/ideas", response_model=list[EditorialItemResponse])
def list_editorial_ideas(
    status: Optional[str] = None,
    platform: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list:
    calendar = EditorialCalendar(db)
    return calendar.list_ideas(status=status, platform=platform, limit=limit)


@app.get("/editorial/tasks", response_model=list[EditorialItemResponse])
def list_editorial_tasks(
    status: Optional[str] = None,
    platform: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list:
    calendar = EditorialCalendar(db)
    return calendar.list_tasks(status=status, platform=platform, limit=limit)


@app.post("/productivity/tasks", response_model=ProductivityTaskResponse)
def create_productivity_task(payload: ProductivityTaskCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    if not data.get("related_goal"):
        goal = GoalEngine(db).best_goal_for_text(f"{data.get('title', '')} {data.get('description', '')} {data.get('category', '')}")
        if goal:
            data["related_goal"] = goal.title
            data["related_topic"] = data.get("related_topic") or goal.related_topic
    return TaskEngine(db).create_task(**data)


@app.patch("/productivity/tasks/{task_id}", response_model=ProductivityTaskResponse)
def update_productivity_task(task_id: int, payload: ProductivityTaskUpdate, db: Session = Depends(get_db)):
    task = TaskEngine(db).update_task(task_id, **payload.model_dump(exclude_unset=True))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/productivity/tasks/{task_id}/complete", response_model=ProductivityTaskResponse)
def complete_productivity_task(task_id: int, db: Session = Depends(get_db)):
    task = TaskEngine(db).complete_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/productivity/tasks/pending", response_model=list[ProductivityTaskResponse])
def list_pending_productivity_tasks(limit: int = 20, db: Session = Depends(get_db)):
    return TaskEngine(db).list_pending_tasks(limit=limit)


@app.get("/productivity/tasks/high-priority", response_model=list[ProductivityTaskResponse])
def list_high_priority_productivity_tasks(limit: int = 10, db: Session = Depends(get_db)):
    return TaskEngine(db).list_high_priority_tasks(limit=limit)


@app.post("/decisions", response_model=DecisionResponse)
def create_decision(payload: DecisionCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    if not data.get("related_goal"):
        goal = GoalEngine(db).best_goal_for_text(f"{data.get('title', '')} {data.get('decision', '')} {data.get('reasoning', '')}")
        if goal:
            data["related_goal"] = goal.title
            data["related_topic"] = data.get("related_topic") or goal.related_topic
    return DecisionJournal(db).save_decision(**data)


@app.get("/decisions", response_model=list[DecisionResponse])
def list_decisions(limit: int = 10, db: Session = Depends(get_db)):
    return DecisionJournal(db).latest_decisions(limit=limit)


@app.get("/reviews/daily", response_model=list[DailyReviewResponse])
def list_daily_reviews(limit: int = 10, db: Session = Depends(get_db)):
    return db.query(DailyReview).order_by(DailyReview.created_at.desc()).limit(limit).all()


@app.get("/reviews/weekly", response_model=list[WeeklyReviewResponse])
def list_weekly_reviews(limit: int = 10, db: Session = Depends(get_db)):
    return db.query(WeeklyReview).order_by(WeeklyReview.created_at.desc()).limit(limit).all()


@app.post("/goals", response_model=GoalResponse)
def create_goal(payload: GoalCreate, db: Session = Depends(get_db)):
    goal = GoalEngine(db).create_goal(**payload.model_dump())
    BrainCore(db).update_state_summary()
    return goal


@app.get("/goals", response_model=list[GoalResponse])
def list_goals(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return GoalEngine(db).list_goals(status=status, limit=limit)


@app.patch("/goals/{goal_id}", response_model=GoalResponse)
def update_goal(goal_id: int, payload: GoalUpdate, db: Session = Depends(get_db)):
    goal = GoalEngine(db).update_goal(goal_id, **payload.model_dump(exclude_unset=True))
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    BrainCore(db).update_state_summary()
    return goal


@app.get("/goals/active", response_model=list[GoalResponse])
def list_active_goals(limit: int = 20, db: Session = Depends(get_db)):
    return GoalEngine(db).list_active_goals(limit=limit)
