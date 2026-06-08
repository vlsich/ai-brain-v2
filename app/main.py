from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.brain_core import BrainCore
from app.config import get_settings
from app.database import SessionLocal, get_db, init_db
from app.memory import Memory
from app.orchestrator import Orchestrator
from app.response_formatter import ResponseFormatter


settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI(title=settings.app_name)


class TaskRequest(BaseModel):
    task: str = Field(..., min_length=3, examples=["Analizza il mercato AI e crea 3 post LinkedIn"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, examples=["Chi sono?", "Creami una strategia TikTok"])


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


class BrainSeedMemory(BaseModel):
    memory_type: str
    title: str
    content: str
    importance: int = Field(default=4, ge=1, le=5)


class BrainSeedRequest(BaseModel):
    memories: list[BrainSeedMemory] = Field(default_factory=list)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    db = SessionLocal()
    try:
        Memory(db).ensure_core_memories()
        BrainCore(db).seed()
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


@app.post("/task", response_model=TaskResponse)
def create_task(payload: TaskRequest, db: Session = Depends(get_db)) -> dict:
    orchestrator = Orchestrator(db)
    formatter = ResponseFormatter(telegram_max_chars=settings.telegram_max_response_chars)
    try:
        result = orchestrator.handle_task(payload.task)
        result["final_answer"] = formatter.format_chat(payload.task, result["final_answer"])
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
    orchestrator = Orchestrator(db)
    formatter = ResponseFormatter(telegram_max_chars=settings.telegram_max_response_chars)
    try:
        result = orchestrator.handle_chat(payload.message)
        result["reply"] = formatter.format_chat(payload.message, result["reply"])
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


@app.get("/brain/state")
def get_brain_state(db: Session = Depends(get_db)) -> dict:
    return BrainCore(db).get_state_summary()


@app.post("/brain/seed")
def seed_brain(payload: BrainSeedRequest, db: Session = Depends(get_db)) -> dict:
    memories = [memory.model_dump() for memory in payload.memories] if payload.memories else None
    return BrainCore(db).seed(memories=memories)
