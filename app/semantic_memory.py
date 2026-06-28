from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from typing import Any, Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LongTermMemory, SemanticMemory as SemanticMemoryModel


logger = logging.getLogger(__name__)


class SemanticMemory:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.client = (
            OpenAI(api_key=self.settings.openai_api_key, timeout=self.settings.openai_timeout_seconds, max_retries=0)
            if self.settings.openai_api_key
            else None
        )

    def remember(
        self,
        content: str,
        memory_type: str,
        importance: int = 3,
        source: str = "",
        related_goal: Optional[str] = None,
        related_topic: Optional[str] = None,
    ) -> SemanticMemoryModel | None:
        content = " ".join(content.strip().split())
        if len(content) < 12:
            return None

        existing = self._find_duplicate(content, memory_type)
        if existing:
            existing.importance = max(existing.importance, max(1, min(5, importance)))
            if related_goal and not existing.related_goal:
                existing.related_goal = related_goal
            if related_topic and not existing.related_topic:
                existing.related_topic = related_topic
            self.db.commit()
            self.db.refresh(existing)
            return existing

        memory = SemanticMemoryModel(
            content=content,
            memory_type=memory_type.strip()[:64] or "general",
            importance=max(1, min(5, int(importance or 3))),
            embedding=json.dumps(self._embed(content)),
            source=source.strip()[:255],
            related_goal=related_goal,
            related_topic=related_topic,
        )
        self.db.add(memory)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def remember_curated_memory(
        self,
        memory: LongTermMemory,
        related_goal: Optional[str] = None,
        related_topic: Optional[str] = None,
    ) -> SemanticMemoryModel | None:
        return self.remember(
            content=f"{memory.title}. {memory.content}",
            memory_type=memory.memory_type,
            importance=memory.importance,
            source=f"long_term_memory:{memory.id}",
            related_goal=related_goal,
            related_topic=related_topic,
        )

    def sync_from_long_term_memory(self, limit: int = 250) -> int:
        created_or_updated = 0
        memories = (
            self.db.query(LongTermMemory)
            .order_by(LongTermMemory.importance.desc(), LongTermMemory.created_at.desc())
            .limit(limit)
            .all()
        )
        existing_sources = {
            item.source
            for item in self.db.query(SemanticMemoryModel.source).filter(SemanticMemoryModel.source.like("long_term_memory:%")).all()
        }
        for memory in memories:
            source = f"long_term_memory:{memory.id}"
            if source in existing_sources:
                continue
            if self.remember_curated_memory(memory):
                created_or_updated += 1
        return created_or_updated

    def retrieve(self, query: str, limit: int = 6, min_score: float = 0.22) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []

        query_embedding = self._embed(query)
        rows = (
            self.db.query(SemanticMemoryModel)
            .order_by(SemanticMemoryModel.importance.desc(), SemanticMemoryModel.created_at.desc())
            .limit(400)
            .all()
        )
        scored: list[dict[str, Any]] = []
        for row in rows:
            score = self._cosine(query_embedding, self._loads_embedding(row.embedding))
            weighted_score = round(min(score + (row.importance * 0.025), 1.0), 4)
            if weighted_score < min_score:
                continue
            scored.append(
                {
                    "id": row.id,
                    "memory_type": row.memory_type,
                    "title": row.content[:80],
                    "content": row.content,
                    "importance": row.importance,
                    "source_task_id": 0,
                    "source": row.source,
                    "related_goal": row.related_goal,
                    "related_topic": row.related_topic,
                    "score": weighted_score,
                    "matched_keywords": ["semantic"],
                    "retrieval": "semantic",
                }
            )

        return sorted(scored, key=lambda item: (item["score"], item["importance"]), reverse=True)[:limit]

    def build_context(self, memories: list[dict[str, Any]], max_chars: int = 1800) -> str:
        if not memories:
            return ""
        lines = ["SEMANTIC MEMORY"]
        for memory in memories:
            goal = f" | goal: {memory['related_goal']}" if memory.get("related_goal") else ""
            topic = f" | topic: {memory['related_topic']}" if memory.get("related_topic") else ""
            lines.append(
                f"- [{memory['memory_type']} score={memory['score']}{goal}{topic}] {memory['content'][:420]}"
            )
        context = "\n".join(lines)
        return context[:max_chars].rstrip()

    def _find_duplicate(self, content: str, memory_type: str) -> SemanticMemoryModel | None:
        fingerprint = self._fingerprint(content)
        rows = (
            self.db.query(SemanticMemoryModel)
            .filter(SemanticMemoryModel.memory_type == memory_type.strip()[:64])
            .order_by(SemanticMemoryModel.created_at.desc())
            .limit(80)
            .all()
        )
        for row in rows:
            if self._fingerprint(row.content) == fingerprint:
                return row
        return None

    def _embed(self, text: str) -> list[float]:
        if self.client:
            try:
                response = self.client.embeddings.create(
                    model=getattr(self.settings, "openai_embedding_model", "text-embedding-3-small"),
                    input=text[:8000],
                )
                return [float(value) for value in response.data[0].embedding]
            except Exception:
                logger.warning("OpenAI embedding failed, using local semantic fallback")
        return self._local_embedding(text)

    def _local_embedding(self, text: str, dimensions: int = 256) -> list[float]:
        vector = [0.0] * dimensions
        tokens = self._tokens(text)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % dimensions
            weight = 1.0 + min(len(token), 12) / 12
            vector[index] += weight
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [round(value / norm, 6) for value in vector]

    def _loads_embedding(self, raw: str) -> list[float]:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return [float(item) for item in value] if isinstance(value, list) else []

    def _cosine(self, left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
        right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
        return max(0.0, min(dot / (left_norm * right_norm), 1.0))

    def _tokens(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-zA-ZÀ-ÿ0-9_]{3,}", text.lower())
            if token not in {"che", "con", "per", "una", "uno", "del", "della", "sono", "come", "this", "that"}
        }

    def _fingerprint(self, text: str) -> str:
        normalized = " ".join(sorted(self._tokens(text)))
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()
