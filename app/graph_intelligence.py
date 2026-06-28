from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from sqlalchemy.orm import Session

from app.knowledge_graph import KnowledgeGraph


class GraphIntelligence:
    def __init__(self, db: Session):
        self.db = db
        self.graph = KnowledgeGraph(db)

    def insights(self, limit: int = 10) -> dict[str, Any]:
        self.graph.refresh_from_current_state(limit=250)
        graph = self.graph.export_graph(limit=500)
        nodes = graph["nodes"]
        edges = graph["edges"]
        degree = self._degree_map(edges)
        weighted_degree = self._weighted_degree_map(edges)

        important_nodes = self._important_nodes(nodes, degree, weighted_degree, limit=limit)
        isolated_nodes = self._isolated_nodes(nodes, degree, limit=limit)
        weak_goals = self._weakly_connected_goals(nodes, edges, degree, limit=limit)
        missing_connections = self._missing_connections(nodes, edges, degree, limit=limit)
        strongest_clusters = self._strongest_clusters(nodes, edges, limit=limit)
        overloaded_topics = self._overloaded_topics(nodes, degree, limit=limit)
        underdeveloped_areas = self._underdeveloped_areas(nodes, edges, degree, limit=limit)
        opportunities = self._opportunities(weak_goals, missing_connections, overloaded_topics, underdeveloped_areas)

        return {
            "summary": self._summary(important_nodes, weak_goals, underdeveloped_areas),
            "most_important_nodes": important_nodes,
            "isolated_nodes": isolated_nodes,
            "weakly_connected_goals": weak_goals,
            "missing_connections": missing_connections,
            "strongest_clusters": strongest_clusters,
            "overloaded_topics": overloaded_topics,
            "underdeveloped_areas": underdeveloped_areas,
            "opportunities": opportunities,
        }

    def clusters(self, limit: int = 10) -> dict[str, Any]:
        self.graph.refresh_from_current_state(limit=250)
        graph = self.graph.export_graph(limit=500)
        return {"clusters": self._strongest_clusters(graph["nodes"], graph["edges"], limit=limit)}

    def gaps(self, limit: int = 10) -> dict[str, Any]:
        self.graph.refresh_from_current_state(limit=250)
        graph = self.graph.export_graph(limit=500)
        degree = self._degree_map(graph["edges"])
        weak_goals = self._weakly_connected_goals(graph["nodes"], graph["edges"], degree, limit=limit)
        missing_connections = self._missing_connections(graph["nodes"], graph["edges"], degree, limit=limit)
        underdeveloped_areas = self._underdeveloped_areas(graph["nodes"], graph["edges"], degree, limit=limit)
        return {
            "weakly_connected_goals": weak_goals,
            "missing_connections": missing_connections,
            "underdeveloped_areas": underdeveloped_areas,
        }

    def format_insights(self, payload: dict[str, Any], intent: str = "analysis") -> str:
        important = payload.get("most_important_nodes", [])[:5]
        weak_goals = payload.get("weakly_connected_goals", [])[:4]
        gaps = payload.get("missing_connections", [])[:4]
        opportunities = payload.get("opportunities", [])[:4]
        underdeveloped = payload.get("underdeveloped_areas", [])[:4]

        if intent == "important_nodes":
            lines = ["I nodi piu importanti del tuo brain oggi sono:"]
            for index, node in enumerate(important, start=1):
                lines.append(f"{index}. {node['title']} ({node['type']}) - score {node['score']}")
            lines.append("\nPerche conta:\nquesti nodi stanno facendo da centro di gravita tra obiettivi, contenuti, decisioni e progetti.")
            lines.append("\nProssimo passo:\nrafforzare i collegamenti tra questi nodi e task concreti della settimana.")
            return "\n".join(lines)

        if intent == "gaps":
            lines = ["Ho notato una cosa importante:"]
            if weak_goals:
                lines.append(f"alcuni obiettivi sono ancora poco collegati ai task. Il piu evidente e: {weak_goals[0]['title']}.")
            elif underdeveloped:
                lines.append(f"alcune aree del brain sono ancora poco sviluppate. La prima e: {underdeveloped[0]['title']}.")
            else:
                lines.append("la base del grafo e collegata, ma puo diventare piu utile se aggiungiamo relazioni operative.")
            lines.append("\nCosa manca:")
            for gap in gaps or underdeveloped:
                lines.append(f"- {gap['title']}: {gap['reason']}")
            lines.append("\nProssimo passo:")
            lines.append("creare o collegare task, funnel, platform e offerta principale agli obiettivi di crescita e monetizzazione.")
            return "\n".join(lines)

        if intent == "opportunities":
            lines = ["Le opportunita piu interessanti che emergono dal grafo sono:"]
            for opportunity in opportunities:
                lines.append(f"- {opportunity}")
            if not opportunities:
                lines.append("- Ricostruire il grafo e collegare meglio obiettivi, task e contenuti per far emergere pattern piu chiari.")
            lines.append("\nProssimo passo:\ntrasformare la prima opportunita in 1 task operativo e 1 contenuto pubblicabile.")
            return "\n".join(lines)

        lines = ["Ho analizzato il tuo Knowledge Graph."]
        lines.append(f"\nIdea principale:\n{payload.get('summary', 'Il grafo mostra dove il Second Brain e forte e dove manca connessione operativa.')}")
        lines.append("\nNodi chiave:")
        for node in important[:4]:
            lines.append(f"- {node['title']} ({node['type']})")
        lines.append("\nGap principali:")
        for gap in (gaps or weak_goals or underdeveloped)[:4]:
            lines.append(f"- {gap['title']}: {gap.get('reason', 'serve collegarlo meglio al sistema operativo.')}")
        lines.append("\nOpportunita:")
        for opportunity in opportunities[:3]:
            lines.append(f"- {opportunity}")
        lines.append("\nProssimo passo:\ncollegare monetizzazione, funnel, piattaforme e task agli obiettivi piu importanti.")
        return "\n".join(lines)

    def _important_nodes(
        self,
        nodes: list[dict[str, Any]],
        degree: dict[int, int],
        weighted_degree: dict[int, int],
        limit: int,
    ) -> list[dict[str, Any]]:
        ranked = []
        for node in nodes:
            node_id = node["id"]
            score = (node.get("importance", 3) * 2) + degree.get(node_id, 0) + weighted_degree.get(node_id, 0)
            ranked.append({**node, "degree": degree.get(node_id, 0), "score": round(score, 2)})
        return sorted(ranked, key=lambda item: (item["score"], item["importance"]), reverse=True)[:limit]

    def _isolated_nodes(self, nodes: list[dict[str, Any]], degree: dict[int, int], limit: int) -> list[dict[str, Any]]:
        return [
            {**node, "reason": "nessuna relazione visibile nel grafo"}
            for node in nodes
            if degree.get(node["id"], 0) == 0
        ][:limit]

    def _weakly_connected_goals(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        degree: dict[int, int],
        limit: int,
    ) -> list[dict[str, Any]]:
        task_edges_by_goal = defaultdict(int)
        node_by_id = {node["id"]: node for node in nodes}
        for edge in edges:
            source = node_by_id.get(edge["source_node_id"])
            target = node_by_id.get(edge["target_node_id"])
            if not source or not target:
                continue
            if source["type"] == "task" and target["type"] == "goal":
                task_edges_by_goal[target["id"]] += 1
            if target["type"] == "task" and source["type"] == "goal":
                task_edges_by_goal[source["id"]] += 1

        weak = []
        for node in nodes:
            if node["type"] != "goal":
                continue
            task_links = task_edges_by_goal.get(node["id"], 0)
            if task_links <= 1:
                weak.append(
                    {
                        **node,
                        "degree": degree.get(node["id"], 0),
                        "task_links": task_links,
                        "reason": "pochi task collegati a questo obiettivo",
                    }
                )
        return sorted(weak, key=lambda item: (item["task_links"], item["degree"], -item["importance"]))[:limit]

    def _missing_connections(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        degree: dict[int, int],
        limit: int,
    ) -> list[dict[str, Any]]:
        connected_pairs = {
            tuple(sorted((edge["source_node_id"], edge["target_node_id"])))
            for edge in edges
        }
        by_type = defaultdict(list)
        for node in nodes:
            by_type[node["type"]].append(node)

        suggestions = []
        for goal in by_type["goal"]:
            for task in by_type["task"]:
                if self._looks_related(goal, task) and tuple(sorted((goal["id"], task["id"]))) not in connected_pairs:
                    suggestions.append(
                        {
                            "title": f"{goal['title']} -> {task['title']}",
                            "source": goal["title"],
                            "target": task["title"],
                            "suggested_edge": "supports",
                            "reason": "obiettivo e task sembrano semanticamente vicini ma non sono collegati",
                        }
                    )
        for platform in by_type["platform"]:
            for strategy in by_type["strategy"] + by_type["content_pillar"]:
                if tuple(sorted((platform["id"], strategy["id"]))) not in connected_pairs:
                    suggestions.append(
                        {
                            "title": f"{platform['title']} -> {strategy['title']}",
                            "source": platform["title"],
                            "target": strategy["title"],
                            "suggested_edge": "supports",
                            "reason": "piattaforma non ancora collegata a una strategia o pillar contenuto",
                        }
                    )
        for node in nodes:
            if node["type"] in {"goal", "strategy", "project", "decision"} and degree.get(node["id"], 0) <= 1:
                suggestions.append(
                    {
                        "title": node["title"],
                        "source": node["title"],
                        "target": "task, topic o progetto rilevante",
                        "suggested_edge": "related_to",
                        "reason": "nodo strategico con poche connessioni operative",
                    }
                )
        return self._dedupe_by_title(suggestions)[:limit]

    def _strongest_clusters(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        node_by_id = {node["id"]: node for node in nodes}
        adjacency = defaultdict(set)
        strength_by_pair = {}
        for edge in edges:
            if edge.get("strength", 0) < 3:
                continue
            source = edge["source_node_id"]
            target = edge["target_node_id"]
            adjacency[source].add(target)
            adjacency[target].add(source)
            strength_by_pair[tuple(sorted((source, target)))] = edge.get("strength", 1)

        clusters = []
        visited = set()
        for node_id in adjacency:
            if node_id in visited:
                continue
            queue = deque([node_id])
            component = []
            visited.add(node_id)
            while queue:
                current = queue.popleft()
                component.append(current)
                for neighbor in adjacency[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            if len(component) < 2:
                continue
            strength = 0
            for source in component:
                for target in adjacency[source]:
                    if target in component:
                        strength += strength_by_pair.get(tuple(sorted((source, target))), 0)
            cluster_nodes = [node_by_id[item] for item in component if item in node_by_id]
            clusters.append(
                {
                    "title": self._cluster_title(cluster_nodes),
                    "size": len(cluster_nodes),
                    "strength": strength // 2,
                    "nodes": [{"id": node["id"], "title": node["title"], "type": node["type"]} for node in cluster_nodes[:8]],
                }
            )
        return sorted(clusters, key=lambda item: (item["strength"], item["size"]), reverse=True)[:limit]

    def _overloaded_topics(self, nodes: list[dict[str, Any]], degree: dict[int, int], limit: int) -> list[dict[str, Any]]:
        overloaded = []
        for node in nodes:
            if node["type"] not in {"topic", "content_pillar", "platform"}:
                continue
            node_degree = degree.get(node["id"], 0)
            if node_degree >= 6:
                overloaded.append(
                    {
                        **node,
                        "degree": node_degree,
                        "reason": "molte connessioni concentrate qui; potrebbe servire dividerlo in sotto-topic o pipeline operative",
                    }
                )
        return sorted(overloaded, key=lambda item: item["degree"], reverse=True)[:limit]

    def _underdeveloped_areas(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        degree: dict[int, int],
        limit: int,
    ) -> list[dict[str, Any]]:
        strategic_types = {"business", "goal", "platform", "content_pillar", "project", "strategy"}
        underdeveloped = []
        for node in nodes:
            if node["type"] not in strategic_types:
                continue
            node_degree = degree.get(node["id"], 0)
            if node_degree <= 2:
                underdeveloped.append(
                    {
                        **node,
                        "degree": node_degree,
                        "reason": "area strategica con poche relazioni rispetto al suo potenziale",
                    }
                )
        return sorted(underdeveloped, key=lambda item: (item["degree"], -item["importance"]))[:limit]

    def _opportunities(
        self,
        weak_goals: list[dict[str, Any]],
        missing_connections: list[dict[str, Any]],
        overloaded_topics: list[dict[str, Any]],
        underdeveloped_areas: list[dict[str, Any]],
    ) -> list[str]:
        opportunities = []
        if weak_goals:
            opportunities.append(f"Trasformare l'obiettivo '{weak_goals[0]['title']}' in 2-3 task operativi collegati.")
        if missing_connections:
            opportunities.append(f"Creare il collegamento '{missing_connections[0]['title']}' per rendere il grafo piu azionabile.")
        if overloaded_topics:
            opportunities.append(f"Spezzare '{overloaded_topics[0]['title']}' in sotto-topic, funnel o format piu specifici.")
        if underdeveloped_areas:
            opportunities.append(f"Sviluppare meglio '{underdeveloped_areas[0]['title']}' con contenuti, decisioni e task dedicati.")
        opportunities.append("Collegare personal brand, piattaforme e monetizzazione con un nodo Funnel o Lead generation.")
        return self._dedupe_text(opportunities)[:5]

    def _summary(
        self,
        important_nodes: list[dict[str, Any]],
        weak_goals: list[dict[str, Any]],
        underdeveloped: list[dict[str, Any]],
    ) -> str:
        if weak_goals:
            return (
                f"Il nodo forte e '{important_nodes[0]['title']}' se presente, ma l'obiettivo "
                f"'{weak_goals[0]['title']}' ha ancora pochi task collegati."
            )
        if underdeveloped:
            return f"Il grafo ha una base utile, ma '{underdeveloped[0]['title']}' e ancora poco sviluppato."
        if important_nodes:
            return f"Il centro del brain oggi e '{important_nodes[0]['title']}'."
        return "Il grafo e ancora in fase iniziale: servono piu nodi e relazioni operative."

    def _degree_map(self, edges: list[dict[str, Any]]) -> dict[int, int]:
        degree = defaultdict(int)
        for edge in edges:
            degree[edge["source_node_id"]] += 1
            degree[edge["target_node_id"]] += 1
        return dict(degree)

    def _weighted_degree_map(self, edges: list[dict[str, Any]]) -> dict[int, int]:
        degree = defaultdict(int)
        for edge in edges:
            strength = int(edge.get("strength", 1) or 1)
            degree[edge["source_node_id"]] += strength
            degree[edge["target_node_id"]] += strength
        return dict(degree)

    def _looks_related(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_tokens = self._tokens(f"{left.get('title', '')} {left.get('description', '')}")
        right_tokens = self._tokens(f"{right.get('title', '')} {right.get('description', '')}")
        if not left_tokens or not right_tokens:
            return False
        return len(left_tokens.intersection(right_tokens)) >= 1

    def _tokens(self, text: str) -> set[str]:
        stopwords = {"michele", "brain", "business", "goal", "task", "content", "finanza", "finance"}
        return {token for token in str(text).lower().replace("/", " ").split() if len(token) >= 4 and token not in stopwords}

    def _cluster_title(self, nodes: list[dict[str, Any]]) -> str:
        preferred = sorted(nodes, key=lambda node: (node.get("importance", 3), node["title"]), reverse=True)
        return preferred[0]["title"] if preferred else "Cluster"

    def _dedupe_by_title(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped = []
        seen = set()
        for item in items:
            key = item["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _dedupe_text(self, items: list[str]) -> list[str]:
        deduped = []
        seen = set()
        for item in items:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped
