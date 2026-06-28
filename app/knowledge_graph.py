from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    AgentResult,
    BrainState,
    ContentIdea,
    ContentTask,
    Decision,
    EditorialPlan,
    Goal,
    KnowledgeEdge,
    KnowledgeNode,
    LongTermMemory,
    ProductivityTask,
)


NODE_TYPES = {
    "person",
    "business",
    "goal",
    "platform",
    "content_pillar",
    "project",
    "task",
    "decision",
    "topic",
    "agent",
    "strategy",
}


EDGE_TYPES = {
    "related_to",
    "supports",
    "depends_on",
    "created_by",
    "improves",
    "belongs_to",
    "conflicts_with",
    "inspired_by",
}


FOUNDATION_NODES = [
    ("Michele", "person", "Michele Valsecchi, owner e utente principale di AI Brain.", 5),
    ("AI Brain", "project", "Second Brain multi-agente con memoria persistente e interfaccia Telegram.", 5),
    ("Business finance", "business", "Business centrato su finanza, educazione finanziaria, investimenti e personal brand.", 5),
    ("Personal brand finance", "business", "Posizionamento pubblico di Michele su finance, investing e crescita multi-platform.", 5),
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
        self.connect(michele, ai_brain, "created_by", strength=5)
        self.connect(michele, business, "belongs_to", strength=5)
        self.connect(brand, business, "supports", strength=5)

        for platform in PLATFORM_KEYWORDS:
            platform_node, was_created = self.get_or_create_node(platform, "platform", f"Piattaforma rilevante per il personal brand di Michele.", 3)
            created += int(was_created)
            self.connect(platform_node, brand, "supports", strength=3)

        for pillar in CONTENT_PILLARS:
            pillar_node, was_created = self.get_or_create_node(pillar.title(), "content_pillar", f"Pilastro contenuti: {pillar}.", 4)
            created += int(was_created)
            self.connect(pillar_node, brand, "supports", strength=4)

        return created

    def refresh_from_current_state(self, limit: int = 80) -> dict[str, int]:
        self.seed_foundation()
        counts = {"goals": 0, "decisions": 0, "memories": 0, "projects": 0, "tasks": 0, "content": 0, "brain_state": 0, "agents": 0}
        for goal in self.db.query(Goal).order_by(Goal.updated_at.desc()).limit(limit).all():
            node, created = self.get_or_create_node(goal.title, "goal", goal.description, self._importance_from_priority(goal.priority))
            counts["goals"] += int(created)
            self.connect(node, self.get_or_create_node("Michele", "person")[0], "belongs_to", strength=node.importance)
            self.connect(node, self.get_or_create_node("Business finance", "business")[0], "supports", strength=node.importance)
            if goal.related_topic:
                topic = self.get_or_create_node(goal.related_topic, "topic", f"Topic collegato all'obiettivo {goal.title}.", 3)[0]
                self.connect(topic, node, "supports", strength=3)

        for decision in self.db.query(Decision).order_by(Decision.created_at.desc()).limit(limit).all():
            node, created = self.get_or_create_node(decision.title, "decision", decision.decision, 4)
            counts["decisions"] += int(created)
            self.connect(node, self.get_or_create_node("Michele", "person")[0], "created_by", strength=4)
            if decision.related_goal:
                goal = self.get_or_create_node(decision.related_goal, "goal", "", 3)[0]
                self.connect(node, goal, "supports", strength=4)
            if decision.related_topic:
                topic = self.get_or_create_node(decision.related_topic, "topic", "", 3)[0]
                self.connect(node, topic, "related_to", strength=3)

        for task in self.db.query(ProductivityTask).order_by(ProductivityTask.created_at.desc()).limit(limit).all():
            node, created = self.get_or_create_node(task.title, "task", task.description, self._importance_from_priority(task.priority))
            counts["tasks"] += int(created)
            if task.related_goal:
                goal = self.get_or_create_node(task.related_goal, "goal", "", 3)[0]
                self.connect(node, goal, "supports", strength=4)
            if task.related_project:
                project = self.get_or_create_node(task.related_project, "project", "Progetto operativo collegato ai task di Michele.", 3)[0]
                self.connect(node, project, "belongs_to", strength=3)
            if task.related_topic:
                topic = self.get_or_create_node(task.related_topic, "topic", "", 3)[0]
                self.connect(node, topic, "related_to", strength=3)

        project_names = (
            self.db.query(ProductivityTask.related_project)
            .filter(ProductivityTask.related_project.isnot(None))
            .distinct()
            .limit(limit)
            .all()
        )
        for project in project_names:
            if not project.related_project:
                continue
            node, created = self.get_or_create_node(project.related_project, "project", "Progetto operativo collegato ai task di Michele.", 3)
            counts["projects"] += int(created)
            self.connect(node, self.get_or_create_node("Michele", "person")[0], "belongs_to", strength=3)

        for item in self._content_items(limit):
            node, created = self.get_or_create_node(item.title, "strategy", item.objective, int(getattr(item, "priority", 3) or 3))
            counts["content"] += int(created)
            if item.platform:
                platform = self.get_or_create_node(item.platform, "platform", "Piattaforma del piano contenuti.", 3)[0]
                self.connect(node, platform, "belongs_to", strength=3)
            if item.content_type:
                topic = self.get_or_create_node(item.content_type, "topic", "Formato o categoria contenuto.", 2)[0]
                self.connect(node, topic, "related_to", strength=2)
            self.connect(node, self.get_or_create_node("Personal brand finance", "business")[0], "supports", strength=3)

        state = self.db.query(BrainState).filter(BrainState.key == "main").first()
        if state:
            node, created = self.get_or_create_node("Brain State Summary", "strategy", state.summary[:1200], 5)
            counts["brain_state"] += int(created)
            self.connect(node, self.get_or_create_node("AI Brain", "project")[0], "belongs_to", strength=5)

        for agent in self._agent_names(limit):
            node, created = self.get_or_create_node(agent, "agent", f"Agente AI Brain: {agent}.", 3)
            counts["agents"] += int(created)
            self.connect(node, self.get_or_create_node("AI Brain", "project")[0], "belongs_to", strength=3)

        for memory in self.db.query(LongTermMemory).order_by(LongTermMemory.importance.desc()).limit(limit).all():
            counts["memories"] += int(self.ingest_memory(memory))
        return counts

    def rebuild(self, limit: int = 250) -> dict[str, Any]:
        counts = self.refresh_from_current_state(limit=limit)
        graph = self.export_graph(limit=limit)
        return {
            "status": "rebuilt",
            "counts": counts,
            "nodes": len(graph["nodes"]),
            "edges": len(graph["edges"]),
        }

    def ingest_memory(self, memory: LongTermMemory) -> bool:
        title = memory.title.strip()
        if not title:
            return False
        node, created = self.get_or_create_node(title, self._node_type_from_memory(memory.memory_type), memory.content, memory.importance)
        self.connect(node, self.get_or_create_node("AI Brain", "project")[0], "belongs_to", strength=memory.importance)
        for concept in self.extract_concepts(f"{memory.title} {memory.content}")[:6]:
            concept_node = self.get_or_create_node(concept, self._concept_type(concept), f"Concetto estratto dalla memoria: {memory.title}.", 3)[0]
            self.connect(concept_node, node, "related_to", strength=3)
        return created

    def export_nodes(self, limit: int = 500, node_type: Optional[str] = None) -> list[dict[str, Any]]:
        query = self.db.query(KnowledgeNode)
        if node_type:
            query = query.filter(KnowledgeNode.type == self._normalize_node_type(node_type))
        nodes = query.order_by(KnowledgeNode.importance.desc(), KnowledgeNode.created_at.desc()).limit(limit).all()
        return [self._node_to_dict(node) for node in nodes]

    def export_edges(self, limit: int = 1000) -> list[dict[str, Any]]:
        edges = self.db.query(KnowledgeEdge).order_by(KnowledgeEdge.strength.desc(), KnowledgeEdge.created_at.desc()).limit(limit).all()
        return [self._edge_to_dict(edge) for edge in edges]

    def export_graph(self, limit: int = 500) -> dict[str, list[dict[str, Any]]]:
        return {
            "nodes": self.export_nodes(limit=limit),
            "edges": self.export_edges(limit=limit * 2),
        }

    def search_graph(self, query: str, limit: int = 25) -> dict[str, list[dict[str, Any]]]:
        normalized = query.strip()
        if not normalized:
            return self.export_graph(limit=limit)

        nodes = (
            self.db.query(KnowledgeNode)
            .filter(or_(KnowledgeNode.title.ilike(f"%{normalized}%"), KnowledgeNode.description.ilike(f"%{normalized}%")))
            .order_by(KnowledgeNode.importance.desc(), KnowledgeNode.created_at.desc())
            .limit(limit)
            .all()
        )
        node_ids = {node.id for node in nodes}
        edges = []
        if node_ids:
            edges = (
                self.db.query(KnowledgeEdge)
                .filter(or_(KnowledgeEdge.source_node_id.in_(node_ids), KnowledgeEdge.target_node_id.in_(node_ids)))
                .order_by(KnowledgeEdge.strength.desc(), KnowledgeEdge.created_at.desc())
                .limit(limit * 2)
                .all()
            )
        return {
            "nodes": [self._node_to_dict(node) for node in nodes],
            "edges": [self._edge_to_dict(edge) for edge in edges],
        }

    def format_graph_summary(self, query: str = "", limit: int = 10) -> str:
        graph = self.search_graph(query, limit=limit) if query else self.export_graph(limit=limit)
        nodes = graph["nodes"]
        edges = graph["edges"]
        if not nodes:
            return "Il Knowledge Graph e ancora vuoto. Il prossimo passo e ricostruirlo dalle memorie e dagli obiettivi."

        main_nodes = nodes[:6]
        key_edges = edges[:6]
        connected_ids = {edge["source_node_id"] for edge in edges}.union({edge["target_node_id"] for edge in edges})
        missing_nodes = [node for node in nodes if node["id"] not in connected_ids][:4]

        lines = ["Ecco cosa vedo nel Knowledge Graph."]
        lines.append("\nNodi principali:")
        for node in main_nodes:
            lines.append(f"- {node['title']} ({node['type']}, importanza {node['importance']})")

        lines.append("\nConnessioni chiave:")
        if key_edges:
            for edge in key_edges:
                source = self._node_title(edge["source_node_id"])
                target = self._node_title(edge["target_node_id"])
                lines.append(f"- {source} -> {target}: {edge['relationship_type']}")
        else:
            lines.append("- Non ci sono ancora connessioni forti.")

        lines.append("\nConnessioni mancanti:")
        if missing_nodes:
            for node in missing_nodes:
                lines.append(f"- {node['title']} dovrebbe essere collegato a un obiettivo, progetto o topic.")
        else:
            lines.append("- La base e collegata. Il prossimo miglioramento e aumentare relazioni tra contenuti e obiettivi.")

        lines.append("\nProssimi link suggeriti:")
        lines.append("- Collegare task attivi agli obiettivi principali.")
        lines.append("- Collegare contenuti e platform alla strategia di conversione.")
        lines.append("- Collegare decisioni recenti ai progetti che influenzano.")
        return "\n".join(lines)

    def format_rebuild_result(self, result: dict[str, Any]) -> str:
        counts = result.get("counts", {})
        return (
            "Knowledge Graph ricostruito.\n\n"
            "Nodi aggiornati:\n"
            f"- Obiettivi: {counts.get('goals', 0)}\n"
            f"- Task: {counts.get('tasks', 0)}\n"
            f"- Decisioni: {counts.get('decisions', 0)}\n"
            f"- Contenuti/strategie: {counts.get('content', 0)}\n"
            f"- Progetti: {counts.get('projects', 0)}\n"
            f"- Memorie: {counts.get('memories', 0)}\n"
            f"- Agenti: {counts.get('agents', 0)}\n\n"
            f"Totale export: {result.get('nodes', 0)} nodi e {result.get('edges', 0)} relazioni.\n\n"
            "Prossimo passo: usare /graph per alimentare una dashboard visuale."
        )

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
        clean_type = self._normalize_node_type(node_type)
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
                KnowledgeEdge.relationship_type == self._normalize_edge_type(relationship_type),
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
            relationship_type=self._normalize_edge_type(relationship_type),
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
            "brand_positioning": "business",
            "content_strategy": "content_pillar",
            "decisions": "decision",
            "tasks": "project",
        }
        return mapping.get(memory_type, "topic")

    def _normalize_node_type(self, node_type: str) -> str:
        clean = node_type.strip().lower()
        aliases = {"brand": "business", "content": "content_pillar", "memory": "topic"}
        clean = aliases.get(clean, clean)
        return clean if clean in NODE_TYPES else "topic"

    def _normalize_edge_type(self, edge_type: str) -> str:
        clean = edge_type.strip().lower()
        aliases = {
            "builds": "created_by",
            "owns": "belongs_to",
            "uses": "supports",
            "publishes_on": "supports",
            "has_pillar": "supports",
            "pursues": "supports",
            "made_decision": "created_by",
            "works_on": "belongs_to",
            "mentions": "related_to",
            "remembers": "belongs_to",
            "relates_to": "related_to",
        }
        clean = aliases.get(clean, clean)
        return clean if clean in EDGE_TYPES else "related_to"

    def _concept_type(self, concept: str) -> str:
        if concept in PLATFORM_KEYWORDS:
            return "platform"
        if concept.lower() in CONTENT_PILLARS:
            return "content_pillar"
        return "topic"

    def _importance_from_priority(self, priority: Optional[str]) -> int:
        return {"critical": 5, "high": 4, "medium": 3, "low": 2}.get((priority or "").lower(), 3)

    def _content_items(self, limit: int) -> list:
        items = []
        for model in (EditorialPlan, ContentIdea, ContentTask):
            items.extend(self.db.query(model).order_by(model.created_at.desc()).limit(limit // 3 or 1).all())
        return items[:limit]

    def _agent_names(self, limit: int) -> list[str]:
        rows = (
            self.db.query(AgentResult.agent_name)
            .distinct()
            .order_by(AgentResult.agent_name.asc())
            .limit(limit)
            .all()
        )
        default_agents = {"manager", "memory_curator", "research", "content", "finance_strategist", "content_planner"}
        return sorted(default_agents.union({row.agent_name for row in rows if row.agent_name}))

    def _node_to_dict(self, node: KnowledgeNode) -> dict[str, Any]:
        return {
            "id": node.id,
            "title": node.title,
            "type": node.type,
            "description": node.description,
            "importance": node.importance,
            "created_at": node.created_at.isoformat(),
        }

    def _edge_to_dict(self, edge: KnowledgeEdge) -> dict[str, Any]:
        return {
            "id": edge.id,
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "relationship_type": self._normalize_edge_type(edge.relationship_type),
            "strength": edge.strength,
            "created_at": edge.created_at.isoformat(),
        }

    def _node_title(self, node_id: int) -> str:
        node = self.db.query(KnowledgeNode).filter(KnowledgeNode.id == node_id).first()
        return node.title if node else f"node:{node_id}"
