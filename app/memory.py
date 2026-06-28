from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import AgentResult, LongTermMemory, Task


MEMORY_TYPE_PRIORITY = {
    "identity": 1.5,
    "user_profile": 1.45,
    "business_profile": 1.42,
    "goals": 1.4,
    "business_goals": 1.38,
    "brand_positioning": 1.32,
    "preferences": 1.25,
    "content_strategy": 1.02,
    "tasks": 0.92,
    "project_roadmap": 0.92,
    "decisions": 0.9,
    "lessons": 0.82,
    "lessons_learned": 0.82,
    "agent_instructions": 0.55,
    "agents_behavior": 0.45,
}


CORE_MEMORIES = [
    {
        "memory_type": "user_profile",
        "title": "Profilo Michele",
        "content": "Michele sta costruendo AI Brain come sistema multi-agente con memoria persistente e interfacce chat/Telegram.",
        "importance": 5,
    },
    {
        "memory_type": "business_goals",
        "title": "Business finance di Michele",
        "content": (
            "Il business principale di Michele e legato alla finance; AI Brain deve aiutare strategia, "
            "contenuti, automazioni e crescita del business."
        ),
        "importance": 5,
    },
    {
        "memory_type": "brand_positioning",
        "title": "Personal brand multi-platform",
        "content": (
            "Michele vuole sviluppare un personal brand multi-platform, con contenuti coerenti su canali "
            "come TikTok, LinkedIn e altri social."
        ),
        "importance": 5,
    },
    {
        "memory_type": "business_goals",
        "title": "Ruolo dell AI nel business",
        "content": (
            "L AI deve funzionare come leva operativa per il business di Michele: ricerca, content strategy, "
            "produzione contenuti, memoria decisionale e agenti autonomi."
        ),
        "importance": 5,
    },
]


class Memory:
    def __init__(self, db: Session):
        self.db = db

    def create_task(self, prompt: str) -> Task:
        task = Task(prompt=prompt, status="running")
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def save_agent_result(self, task_id: int, agent_name: str, output: str) -> AgentResult:
        result = AgentResult(task_id=task_id, agent_name=agent_name, output=output)
        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)
        return result

    def save_long_term_memory(
        self,
        memory_type: str,
        title: str,
        content: str,
        importance: int,
        source_task_id: int,
    ) -> LongTermMemory:
        existing = (
            self.db.query(LongTermMemory)
            .filter(
                LongTermMemory.memory_type == memory_type,
                LongTermMemory.title == title,
            )
            .first()
        )
        if existing:
            existing.importance = max(existing.importance, max(1, min(5, importance)))
            if content and content not in existing.content:
                existing.content = f"{existing.content}\nAggiornamento: {content}"
            self.db.commit()
            self.db.refresh(existing)
            return existing

        memory = LongTermMemory(
            memory_type=memory_type,
            title=title,
            content=content,
            importance=max(1, min(5, importance)),
            source_task_id=source_task_id,
        )
        self.db.add(memory)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def ensure_core_memories(self) -> int:
        existing = {
            (memory.memory_type, memory.title)
            for memory in self.list_long_term_memories(limit=1000)
        }
        missing_memories = [
            memory
            for memory in CORE_MEMORIES
            if (memory["memory_type"], memory["title"]) not in existing
        ]
        if not missing_memories:
            return 0

        source_task = self.create_task("Bootstrap memoria core AI Brain")
        self.complete_task(source_task.id, "Memorie core inizializzate.")

        for memory in missing_memories:
            self.save_long_term_memory(
                memory_type=memory["memory_type"],
                title=memory["title"],
                content=memory["content"],
                importance=memory["importance"],
                source_task_id=source_task.id,
            )

        return len(missing_memories)

    def list_long_term_memories(
        self,
        memory_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[LongTermMemory]:
        query = self.db.query(LongTermMemory).order_by(
            LongTermMemory.importance.desc(),
            LongTermMemory.created_at.desc(),
        )
        if memory_type:
            query = query.filter(LongTermMemory.memory_type == memory_type)
        return query.limit(limit).all()

    def search_long_term_memories(
        self,
        query_text: str,
        memory_type: Optional[str] = None,
        limit: int = 20,
    ) -> list[LongTermMemory]:
        pattern = f"%{query_text}%"
        query = self.db.query(LongTermMemory).filter(or_(LongTermMemory.title.ilike(pattern), LongTermMemory.content.ilike(pattern)))
        if memory_type:
            query = query.filter(LongTermMemory.memory_type == memory_type)
        return query.order_by(LongTermMemory.importance.desc(), LongTermMemory.created_at.desc()).limit(limit).all()

    def retrieve_relevant_memories(self, task: str, limit: int = 6, min_score: float = 0.18) -> list[dict[str, Any]]:
        task_tokens = self._tokens(task)
        if not task_tokens:
            return []

        memories = self.list_long_term_memories(limit=300)
        scored_memories: list[dict[str, Any]] = []
        selected_fingerprints: set[str] = set()
        selected_titles: set[str] = set()

        for memory in memories:
            text = f"{memory.memory_type} {memory.title} {memory.content}"
            memory_tokens = self._tokens(text)
            keyword_score = self._keyword_score(task_tokens, memory_tokens)
            similarity_score = SequenceMatcher(None, task.lower(), text.lower()).ratio()
            business_score = self._business_relevance_score(task_tokens, memory_tokens)
            importance_score = memory.importance / 5
            priority_multiplier = MEMORY_TYPE_PRIORITY.get(memory.memory_type, 0.9)
            raw_score = (
                (keyword_score * 0.52)
                + (business_score * 0.24)
                + (similarity_score * 0.09)
                + (importance_score * 0.15)
            )
            score = round(min(raw_score * priority_multiplier, 1.0), 4)
            matched_keywords = sorted(task_tokens.intersection(memory_tokens))

            if score < min_score or not self._has_enough_relevance(memory.memory_type, matched_keywords, business_score, score):
                continue

            scored_memories.append(
                {
                    "id": memory.id,
                    "memory_type": memory.memory_type,
                    "title": memory.title,
                    "content": memory.content,
                    "importance": memory.importance,
                    "source_task_id": memory.source_task_id,
                    "score": score,
                    "matched_keywords": matched_keywords,
                }
            )

        ranked_memories = sorted(
            scored_memories,
            key=lambda item: (
                item["score"],
                MEMORY_TYPE_PRIORITY.get(item["memory_type"], 0),
                item["importance"],
            ),
            reverse=True,
        )

        deduped_memories: list[dict[str, Any]] = []
        for memory in ranked_memories:
            fingerprint = self._memory_fingerprint(memory)
            title_key = f"{memory['memory_type']}:{memory['title'].strip().lower()}"
            if fingerprint in selected_fingerprints or title_key in selected_titles:
                continue
            selected_fingerprints.add(fingerprint)
            selected_titles.add(title_key)
            deduped_memories.append(memory)
            if len(deduped_memories) >= limit:
                break

        return deduped_memories

    def build_context_from_memory(self, memories: list[dict[str, Any]], max_chars: int = 3500) -> str:
        if not memories:
            return ""

        grouped: dict[str, list[dict[str, Any]]] = {}
        for memory in memories:
            grouped.setdefault(memory["memory_type"], []).append(memory)

        sections = [
            "MEMORY CONTEXT",
            "Usa queste memorie per personalizzare la risposta. Non contraddire il messaggio corrente: i vincoli dell'utente hanno priorita.",
        ]
        used_chars = sum(len(section) for section in sections)

        for memory_type in MEMORY_TYPE_PRIORITY:
            items = grouped.get(memory_type, [])
            if not items:
                continue

            heading = f"\n[{memory_type}]"
            if used_chars + len(heading) > max_chars:
                break
            sections.append(heading)
            used_chars += len(heading)

            for item in items:
                line = self._format_memory_context_line(item)
                if used_chars + len(line) > max_chars:
                    return "\n".join(sections)
                sections.append(line)
                used_chars += len(line)

        return "\n".join(sections)

    def _tokens(self, text: str) -> set[str]:
        stopwords = {
            "alla",
            "allo",
            "altri",
            "come",
            "con",
            "crea",
            "creami",
            "degli",
            "della",
            "delle",
            "di",
            "fare",
            "gli",
            "il",
            "la",
            "le",
            "lo",
            "mio",
            "mia",
            "miei",
            "mie",
            "nel",
            "per",
            "proponi",
            "quali",
            "sono",
            "una",
            "uno",
        }
        return {
            token
            for token in re.findall(r"[a-zA-Z0-9_]+", text.lower())
            if len(token) > 2 and token not in stopwords
        }

    def _keyword_score(self, task_tokens: set[str], memory_tokens: set[str]) -> float:
        if not task_tokens or not memory_tokens:
            return 0.0
        overlap = task_tokens.intersection(memory_tokens)
        return len(overlap) / len(task_tokens)

    def _has_enough_relevance(
        self,
        memory_type: str,
        matched_keywords: list[str],
        business_score: float,
        score: float,
    ) -> bool:
        strategic_types = {"user_profile", "business_goals", "brand_positioning", "preferences"}
        if len(matched_keywords) >= 2:
            return True
        if memory_type in strategic_types and matched_keywords and score >= 0.25:
            return True
        if business_score >= 0.5 and score >= 0.22:
            return True
        return False

    def _business_relevance_score(self, task_tokens: set[str], memory_tokens: set[str]) -> float:
        priority_terms = {
            "michele",
            "finance",
            "finanza",
            "business",
            "ai",
            "brain",
            "personal",
            "brand",
            "tiktok",
            "linkedin",
            "instagram",
            "youtube",
            "newsletter",
            "multi",
            "platform",
            "automazione",
            "automazioni",
            "agent",
            "agenti",
            "content",
            "contenuti",
        }
        relevant_terms = priority_terms.intersection(task_tokens.union(memory_tokens))
        if not relevant_terms:
            return 0.0

        matched_terms = priority_terms.intersection(task_tokens).intersection(memory_tokens)
        return len(matched_terms) / max(len(priority_terms.intersection(task_tokens)), 1)

    def _memory_fingerprint(self, memory: dict[str, Any]) -> str:
        text = f"{memory['memory_type']} {memory['title']} {memory['content'][:240]}"
        tokens = sorted(self._tokens(text))
        return "|".join(tokens[:14])

    def _format_memory_context_line(self, memory: dict[str, Any]) -> str:
        content = memory["content"].replace("\n", " ").strip()
        if len(content) > 520:
            content = f"{content[:520]}..."
        matched = ", ".join(memory.get("matched_keywords", [])[:8]) or "none"
        return (
            f"- {memory['title']} "
            f"(id={memory['id']}, score={memory['score']}, importance={memory['importance']}, "
            f"matched={matched}): {content}"
        )

    def complete_task(self, task_id: int, final_answer: str) -> Task:
        task = self.db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        task.status = "completed"
        task.final_answer = final_answer
        self.db.commit()
        self.db.refresh(task)
        return task

    def fail_task(self, task_id: int, error: str) -> Task:
        task = self.db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        task.status = "failed"
        task.final_answer = error
        self.db.commit()
        self.db.refresh(task)
        return task
