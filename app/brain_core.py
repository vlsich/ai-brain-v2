from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.memory import Memory
from app.models import BrainState, LongTermMemory


BRAIN_MEMORY_TYPES = {
    "identity",
    "business_profile",
    "goals",
    "preferences",
    "brand_positioning",
    "content_strategy",
    "decisions",
    "lessons",
    "tasks",
    "agent_instructions",
}


LEGACY_MEMORY_TYPE_MAP = {
    "user_profile": "identity",
    "business_goals": "goals",
    "brand_positioning": "brand_positioning",
    "preferences": "preferences",
    "content_strategy": "content_strategy",
    "decisions": "decisions",
    "lessons_learned": "lessons",
    "project_roadmap": "tasks",
    "agents_behavior": "agent_instructions",
}


BRAIN_SEED_MEMORIES = [
    {
        "memory_type": "identity",
        "title": "Identita Michele",
        "content": "Michele Valsecchi sta costruendo AI Brain come cervello operativo persistente per lavoro, contenuti e business.",
        "importance": 5,
    },
    {
        "memory_type": "business_profile",
        "title": "Business finance",
        "content": "Il business di Michele e centrato su finanza personale, educazione finanziaria, investimenti e crescita del personal brand.",
        "importance": 5,
    },
    {
        "memory_type": "goals",
        "title": "Obiettivi AI Brain",
        "content": "AI Brain deve aiutare Michele a ragionare meglio, ricordare decisioni, creare contenuti, coordinare agenti e trasformare idee in azioni.",
        "importance": 5,
    },
    {
        "memory_type": "brand_positioning",
        "title": "Personal brand finance multi-platform",
        "content": "Il personal brand di Michele deve essere chiaro, autorevole, pratico e multi-platform, con focus finance e conversione audience.",
        "importance": 5,
    },
    {
        "memory_type": "agent_instructions",
        "title": "Stile operativo AI Brain",
        "content": "Risposte in italiano, sintetiche ma ragionate, professionali, operative, senza rumore e adattate a Telegram quando necessario.",
        "importance": 5,
    },
]


class BrainCore:
    state_key = "main"

    def __init__(self, db: Session):
        self.db = db
        self.memory = Memory(db)

    def seed(self, memories: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        seed_memories = memories or BRAIN_SEED_MEMORIES
        existing = {
            (memory.memory_type, memory.title)
            for memory in self.memory.list_long_term_memories(limit=1000)
        }
        memories_to_process = [
            item
            for item in seed_memories
            if (self.normalize_memory_type(str(item.get("memory_type", ""))), str(item.get("title", "")).strip())
            not in existing
        ]

        created_or_updated = 0
        source_task_id = 1
        if memories_to_process:
            source_task = self.memory.create_task("Brain seed")
            self.memory.complete_task(source_task.id, "Brain seed completato.")
            source_task_id = source_task.id

        for item in memories_to_process:
            memory_type = self.normalize_memory_type(str(item.get("memory_type", "")))
            if memory_type not in BRAIN_MEMORY_TYPES:
                continue
            title = str(item.get("title", "")).strip()
            content = str(item.get("content", "")).strip()
            if not title or not content:
                continue
            self.memory.save_long_term_memory(
                memory_type=memory_type,
                title=title[:255],
                content=content,
                importance=int(item.get("importance", 4)),
                source_task_id=source_task_id,
            )
            created_or_updated += 1

        state = self.update_state_summary()
        return {"memories_processed": created_or_updated, "state": state}

    def get_state_summary(self) -> dict[str, Any]:
        state = self.db.query(BrainState).filter(BrainState.key == self.state_key).first()
        if state is None:
            state = self.update_state_summary()
            return state
        return {
            "key": state.key,
            "summary": state.summary,
            "version": state.version,
            "updated_at": state.updated_at,
            "memory_types": sorted(BRAIN_MEMORY_TYPES),
        }

    def update_state_summary(self) -> dict[str, Any]:
        memories = self._brain_memories(limit=250)
        summary = self._build_summary(memories)
        state = self.db.query(BrainState).filter(BrainState.key == self.state_key).first()

        if state is None:
            state = BrainState(key=self.state_key, summary=summary, version=1)
            self.db.add(state)
        else:
            state.summary = summary
            state.version += 1

        self.db.commit()
        self.db.refresh(state)
        return {
            "key": state.key,
            "summary": state.summary,
            "version": state.version,
            "updated_at": state.updated_at,
            "memory_types": sorted(BRAIN_MEMORY_TYPES),
        }

    def should_update_after_task(
        self,
        prompt: str,
        agents_used: list[str],
        saved_memories_count: int,
    ) -> bool:
        normalized = prompt.lower()
        important_keywords = (
            "obiettivo",
            "strategia",
            "decisione",
            "preferenza",
            "business",
            "brand",
            "finance",
            "finanza",
            "roadmap",
            "posizionamento",
            "telegram",
            "agent",
            "agente",
        )
        return saved_memories_count > 0 or bool(agents_used) or any(keyword in normalized for keyword in important_keywords)

    def normalize_memory_type(self, memory_type: str) -> str:
        memory_type = memory_type.strip()
        return LEGACY_MEMORY_TYPE_MAP.get(memory_type, memory_type)

    def context_for_agents(self, max_chars: int = 1800) -> str:
        state = self.get_state_summary()
        summary = state["summary"]
        if len(summary) <= max_chars:
            return summary
        return f"{summary[:max_chars].rstrip()}..."

    def _brain_memories(self, limit: int) -> list[LongTermMemory]:
        memories = self.memory.list_long_term_memories(limit=limit)
        for memory in memories:
            normalized_type = self.normalize_memory_type(memory.memory_type)
            if normalized_type != memory.memory_type and normalized_type in BRAIN_MEMORY_TYPES:
                memory.memory_type = normalized_type
        self.db.commit()
        return [
            memory
            for memory in memories
            if memory.memory_type in BRAIN_MEMORY_TYPES or self.normalize_memory_type(memory.memory_type) in BRAIN_MEMORY_TYPES
        ]

    def _build_summary(self, memories: list[LongTermMemory]) -> str:
        grouped: dict[str, list[LongTermMemory]] = defaultdict(list)
        for memory in memories:
            grouped[self.normalize_memory_type(memory.memory_type)].append(memory)

        sections = [
            "Brain State Summary",
            "Questa sintesi rappresenta il contesto persistente attuale di AI Brain.",
            "",
            self._section("Identita", grouped["identity"], fallback="Michele sta costruendo AI Brain come cervello persistente personale/business."),
            self._section("Business profile", grouped["business_profile"], fallback="Business centrato su finance, educazione finanziaria, investimenti e personal brand."),
            self._section("Obiettivi e priorita", grouped["goals"], fallback="Crescita del business, contenuti migliori, memoria decisionale e automazioni operative."),
            self._section("Brand positioning", grouped["brand_positioning"], fallback="Personal brand finance pratico, autorevole, multi-platform e orientato alla conversione."),
            self._section("Preferenze", grouped["preferences"], fallback="Risposte in italiano, concrete, sintetiche, professionali e adatte a Telegram."),
            self._section("Content strategy", grouped["content_strategy"], fallback="Contenuti finance educativi, format social, funnel e conversione audience."),
            self._section("Decisioni", grouped["decisions"], fallback="Nessuna decisione critica consolidata oltre alla costruzione modulare di AI Brain."),
            self._section("Lessons", grouped["lessons"], fallback="Salvare solo memoria utile, ridurre rumore e migliorare qualita delle risposte."),
            self._section("Tasks", grouped["tasks"], fallback="Sviluppare backend, Telegram bot, memoria persistente, retrieval e agenti specialistici."),
            self._section("Agent instructions", grouped["agent_instructions"], fallback="Manager sintetizza, Finance Strategist cura strategia finance, Content produce output utilizzabili."),
        ]
        return "\n".join(sections).strip()

    def _section(self, title: str, memories: list[LongTermMemory], fallback: str) -> str:
        if not memories:
            return f"{title}: {fallback}"

        top_memories = sorted(memories, key=lambda item: (item.importance, item.created_at), reverse=True)[:4]
        points = []
        seen_points = set()
        for memory in top_memories:
            content = memory.content.replace("\n", " ").strip()
            if len(content) > 260:
                content = f"{content[:260].rstrip()}..."
            fingerprint = " ".join(content.lower().split())[:180]
            if fingerprint in seen_points:
                continue
            seen_points.add(fingerprint)
            points.append(content)
        return f"{title}: " + " ".join(points)
