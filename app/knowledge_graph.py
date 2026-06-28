from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Decision, Goal, KnowledgeEdge, KnowledgeNode, LongTermMemory


FOUNDATION_NODES = [
    ("Michele", "person", "Michele Valsecchi, owner e utente principale di AI Brain.", 5),
    ("AI Brain", "project", "Second Brain multi-agente con memoria persistente e interfaccia Telegram.", 5),
    ("Business finance", "business", "Business centrato su finanza, educazione finanziaria, investimenti e personal brand.", 5),
    ("Personal brand finance", "brand", "Posizionamento pubblico di Michele su finance, investing e crescita multi-platform.", 5),
]


PLATFORM_KEYWORDS = ("TikTok", "Instagram", "LinkedIn", "YouTube", "Newsletter", "Telegram")
CONTENT_PILLARS = ("educazione finanziaria", "investimenti", "ETF", "personal brand", "conversione audience")


class KnowledgeGraph:
    def __init__(self, db: Session):
        self.db = db

    def seed_foundation(self) -> int:
        created = 0
        for title, node_type, description, importance in FOUNDATION_NODES:
            node, was_created = self.get_or_create_node(title, node_type, description, importance)
            created += int(was_created)

        michele = self.get_or_create_node("Michele", "person")[0]
        ai_brain = self.get_or_create_node("AI Brain", "project")[0]
        business = self.get_or_create_node("Business finance", "business")[0]
        brand = self.get_or_create_node("Personal brand finance", "brand")[0]
        self.connect(michele, ai_brain, "builds", strength=5)
        self.connect(michele, business, "owns", strength=5)
        self.connect(business, brand, "uses", strength=5)

        for platform in PLATFORM_KEYWORDS:
            platform_node, was_created = self.get_or_create_node(platform, "platform", f"Piattaforma rilevante per il personal brand di Michele.", 3)
            created += int(was_created)
            self.connect(brand, platform_node, "publishes_on", strength=3)

        for pillar in CONTENT_PILLARS:
            pillar_node, was_created = self.get_or_create_node(pillar.title(), "content_pillar", f"Pilastro contenuti: {pillar}.", 4)
            created += int(was_created)
            self.connect(brand, pillar_node, "has_pillar", strength=4)

        return created

    def refresh_from_current_state(self, limit: int = 80) -> dict[str, int]:
        self.seed_foundation()
        counts = {"goals": 0, "decisions": 0, "memories": 0}
        for goal in self.db.query(Goal).order_by(Goal.updated_at.desc()).limit(limit).all():
            node, created = self.get_or_create_node(goal.title, "goal", goal.description, self._importance_from_priority(goal.priority))
            counts["goals"] += int(created)
            self.connect(self.get_or_create_node("Michele", "person")[0], node, "pursues", strength=node.importance)
            if goal.related_topic:
                topic = self.get_or_create_node(goal.related_topic, "topic", f"Topic collegato all'obiettivo {goal.title}.", 3)[0]
                self.connect(node, topic, "relates_to", strength=3)

        for decision in self.db.query(Decision).order_by(Decision.created_at.desc()).limit(limit).all():
            node, created = self.get_or_create_node(decision.title, "decision", decision.decision, 4)
            counts["decisions"] += int(created)
            self.connect(self.get_or_create_node("Michele", "person")[0], node, "made_decision", strength=4)
            if decision.related_goal:
                goal = self.get_or_create_node(decision.related_goal, "goal", "", 3)[0]
                self.connect(node, goal, "supports", strength=4)
            if decision.related_topic:
                topic = self.get_or_create_node(decision.related_topic, "topic", "", 3)[0]
                self.connect(node, topic, "relates_to", strength=3)

        for memory in self.db.query(LongTermMemory).order_by(LongTermMemory.importance.desc()).limit(limit).all():
            counts["memories"] += int(self.ingest_memory(memory))
        return counts

    def ingest_memory(self, memory: LongTermMemory) -> bool:
        title = memory.title.strip()
        if not title:
            return False
        node, created = self.get_or_create_node(title, self._node_type_from_memory(memory.memory_type), memory.content, memory.importance)
        self.connect(self.get_or_create_node("AI Brain", "project")[0], node, "remembers", strength=memory.importance)
        for concept in self.extract_concepts(f"{memory.title} {memory.content}")[:6]:
            concept_node = self.get_or_create_node(concept, self._concept_type(concept), f"Concetto estratto dalla memoria: {memory.title}.", 3)[0]
            self.connect(node, concept_node, "mentions", strength=3)
        return created

    def related_concepts(self, query: str = "", limit: int = 12) -> list[dict[str, Any]]:
        normalized = query.strip().lower()
        if normalized:
            nodes = (
                self.db.query(KnowledgeNode)
                .filter(or_(KnowledgeNode.title.ilike(f"%{normalized}%"), KnowledgeNode.description.ilike(f"%{normalized}%")))
                .order_by(KnowledgeNode.importance.desc(), KnowledgeNode.created_at.desc())
                .limit(6)
                .all()
            )
        else:
            nodes = (
                self.db.query(KnowledgeNode)
                .order_by(KnowledgeNode.importance.desc(), KnowledgeNode.created_at.desc())
                .limit(6)
                .all()
            )

        related: list[dict[str, Any]] = []
        seen: set[int] = set()
        for node in nodes:
            seen.add(node.id)
            edges = (
                self.db.query(KnowledgeEdge)
                .filter(or_(KnowledgeEdge.source_node_id == node.id, KnowledgeEdge.target_node_id == node.id))
                .order_by(KnowledgeEdge.strength.desc(), KnowledgeEdge.created_at.desc())
                .limit(limit)
                .all()
            )
            for edge in edges:
                target_id = edge.target_node_id if edge.source_node_id == node.id else edge.source_node_id
                if target_id in seen:
                    continue
                target = self.db.query(KnowledgeNode).filter(KnowledgeNode.id == target_id).first()
                if not target:
                    continue
                seen.add(target.id)
                related.append(
                    {
                        "from": node.title,
                        "to": target.title,
                        "type": target.type,
                        "relationship": edge.relationship_type,
                        "strength": edge.strength,
                    }
                )
                if len(related) >= limit:
                    return related
        return related

    def format_related_concepts(self, concepts: list[dict[str, Any]]) -> str:
        if not concepts:
            return "Non ho ancora abbastanza concetti collegati. Posso aggiornare il Second Brain e ricostruire il grafo."
        lines = ["I concetti piu collegati nel Second Brain sono:"]
        for index, item in enumerate(concepts, start=1):
            lines.append(
                f"{index}. {item['from']} -> {item['to']} ({item['relationship']}, forza {item['strength']})"
            )
        lines.append("\nProssimo passo: usa questi collegamenti per decidere contenuti, priorita o progetti da sviluppare.")
        return "\n".join(lines)

    def get_or_create_node(
        self,
        title: str,
        node_type: str,
        description: str = "",
        importance: int = 3,
    ) -> tuple[KnowledgeNode, bool]:
        clean_title = " ".join(title.strip().split())[:255] or "Concetto"
        clean_type = node_type.strip()[:64] or "topic"
        node = (
            self.db.query(KnowledgeNode)
            .filter(KnowledgeNode.title == clean_title, KnowledgeNode.type == clean_type)
            .first()
        )
        if node:
            node.importance = max(node.importance, max(1, min(5, importance)))
            if description and len(description) > len(node.description):
                node.description = description.strip()
            self.db.commit()
            self.db.refresh(node)
            return node, False

        node = KnowledgeNode(
            title=clean_title,
            type=clean_type,
            description=description.strip(),
            importance=max(1, min(5, importance)),
        )
        self.db.add(node)
        self.db.commit()
        self.db.refresh(node)
        return node, True

    def connect(
        self,
        source: KnowledgeNode,
        target: KnowledgeNode,
        relationship_type: str,
        strength: int = 3,
    ) -> KnowledgeEdge:
        existing = (
            self.db.query(KnowledgeEdge)
            .filter(
                KnowledgeEdge.source_node_id == source.id,
                KnowledgeEdge.target_node_id == target.id,
                KnowledgeEdge.relationship_type == relationship_type,
            )
            .first()
        )
        if existing:
            existing.strength = max(existing.strength, max(1, min(5, strength)))
            self.db.commit()
            self.db.refresh(existing)
            return existing

        edge = KnowledgeEdge(
            source_node_id=source.id,
            target_node_id=target.id,
            relationship_type=relationship_type.strip()[:64] or "related_to",
            strength=max(1, min(5, strength)),
        )
        self.db.add(edge)
        self.db.commit()
        self.db.refresh(edge)
        return edge

    def extract_concepts(self, text: str) -> list[str]:
        concepts = []
        lowered = text.lower()
        for platform in PLATFORM_KEYWORDS:
            if platform.lower() in lowered:
                concepts.append(platform)
        for pillar in CONTENT_PILLARS:
            if pillar.lower() in lowered:
                concepts.append(pillar.title())
        for token in re.findall(r"[A-ZÀ-Ý][a-zA-ZÀ-ÿ0-9_]{3,}(?:\s+[A-ZÀ-Ý][a-zA-ZÀ-ÿ0-9_]{3,})?", text):
            if token not in concepts:
                concepts.append(token)
        return concepts

    def _node_type_from_memory(self, memory_type: str) -> str:
        mapping = {
            "identity": "person",
            "business_profile": "business",
            "goals": "goal",
            "brand_positioning": "brand",
            "content_strategy": "content_pillar",
            "decisions": "decision",
            "tasks": "project",
        }
        return mapping.get(memory_type, "topic")

    def _concept_type(self, concept: str) -> str:
        if concept in PLATFORM_KEYWORDS:
            return "platform"
        if concept.lower() in CONTENT_PILLARS:
            return "content_pillar"
        return "topic"

    def _importance_from_priority(self, priority: Optional[str]) -> int:
        return {"critical": 5, "high": 4, "medium": 3, "low": 2}.get((priority or "").lower(), 3)
