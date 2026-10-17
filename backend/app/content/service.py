"""Read-side service for concept graph traversal and curriculum lookups.

Provides:
- GraphService: in-memory DAG traversal, transitive prerequisite resolution,
  dependents lookup, React Flow graph formatting, and topological learning paths.
"""

from collections import deque
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Concept, ConceptEdge


class GraphCycleError(Exception):
    """Raised when an unexpected cycle is encountered during graph traversal."""


class GraphService:
    """Graph query service operating on active concept nodes and prerequisite edges."""

    def __init__(
        self,
        concepts: dict[str, dict[str, Any]] | None = None,
        edges: list[tuple[str, str]] | None = None,
    ) -> None:
        # concepts: id -> {id, title, difficulty, topic, ...}
        self.concepts = concepts or {}
        # edges: list of (source_id, target_id) where source_id is PREREQUISITE of target_id
        # target_id depends on source_id
        self.edges = edges or []

        # Build adjacency maps:
        # prereqs_map[node] = list of nodes that 'node' directly requires
        # dependents_map[node] = list of nodes that directly require 'node'
        self.prereqs_map: dict[str, list[str]] = {cid: [] for cid in self.concepts}
        self.dependents_map: dict[str, list[str]] = {cid: [] for cid in self.concepts}

        for src, tgt in self.edges:
            if tgt in self.prereqs_map and src in self.concepts:
                self.prereqs_map[tgt].append(src)
            if src in self.dependents_map and tgt in self.concepts:
                self.dependents_map[src].append(tgt)

    @classmethod
    async def from_db(
        cls,
        session: AsyncSession,
        topic: str | None = None,
    ) -> "GraphService":
        """Construct GraphService populated from active database records."""
        concept_query = select(Concept).where(Concept.is_active.is_(True))
        if topic:
            concept_query = concept_query.where(Concept.topic == topic)

        concepts_res = await session.execute(concept_query)
        concepts_list = concepts_res.scalars().all()
        concept_ids = {c.id for c in concepts_list}

        concepts_dict: dict[str, dict[str, Any]] = {
            c.id: {
                "id": c.id,
                "title": c.title,
                "difficulty": c.difficulty,
                "domain": c.domain,
                "topic": c.topic,
            }
            for c in concepts_list
        }

        # Fetch active edges connecting active concepts
        edge_query = select(ConceptEdge).where(
            ConceptEdge.source_id.in_(concept_ids),
            ConceptEdge.target_id.in_(concept_ids),
        )
        edge_res = await session.execute(edge_query)
        edges = [(e.source_id, e.target_id) for e in edge_res.scalars().all()]

        return cls(concepts=concepts_dict, edges=edges)

    def get_prerequisites(self, concept_id: str, depth: int | None = None) -> list[str]:
        """Retrieve direct or transitive prerequisites for a concept."""
        if concept_id not in self.concepts:
            return []

        if depth == 1:
            return list(self.prereqs_map.get(concept_id, []))

        # BFS / DFS traversal for transitive prerequisites with loop guard
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(concept_id, 0)])

        while queue:
            curr, curr_depth = queue.popleft()
            if depth is not None and curr_depth >= depth:
                continue

            for prereq in self.prereqs_map.get(curr, []):
                if prereq not in visited:
                    visited.add(prereq)
                    queue.append((prereq, curr_depth + 1))

        return list(visited)

    def get_dependents(self, concept_id: str) -> list[str]:
        """Retrieve concepts that directly depend on concept_id."""
        return list(self.dependents_map.get(concept_id, []))

    def get_topic_graph(self, topic: str) -> dict[str, Any]:
        """Format topic concepts and edges for React Flow visualization."""
        nodes: list[dict[str, Any]] = []
        topic_concept_ids: set[str] = set()

        for cid, data in self.concepts.items():
            if data.get("topic") == topic:
                topic_concept_ids.add(cid)
                nodes.append(
                    {
                        "id": cid,
                        "label": data.get("title", cid),
                        "difficulty": data.get("difficulty", 1),
                    }
                )

        edges: list[dict[str, str]] = [
            {"source": src, "target": tgt}
            for src, tgt in self.edges
            if src in topic_concept_ids and tgt in topic_concept_ids
        ]

        return {"nodes": nodes, "edges": edges}

    def learning_path(self, target_concept_id: str) -> list[str]:
        """Return a topologically sorted list of prerequisites leading to target_concept_id.

        Guards against cycles and raises GraphCycleError if an invalid loop is encountered.
        """
        if target_concept_id not in self.concepts:
            raise KeyError(f"Target concept '{target_concept_id}' not found in graph.")

        # Subgraph needed: target_concept_id + all its transitive prerequisites
        needed_nodes = set(self.get_prerequisites(target_concept_id))
        needed_nodes.add(target_concept_id)

        # Topological sort using Kahn's algorithm or DFS with cycle detection
        in_degree: dict[str, int] = dict.fromkeys(needed_nodes, 0)
        subgraph_adj: dict[str, list[str]] = {node: [] for node in needed_nodes}

        for src, tgt in self.edges:
            if src in needed_nodes and tgt in needed_nodes:
                subgraph_adj[src].append(tgt)
                in_degree[tgt] += 1

        queue: deque[str] = deque([node for node, deg in in_degree.items() if deg == 0])
        order: list[str] = []

        while queue:
            curr = queue.popleft()
            order.append(curr)

            for neighbor in subgraph_adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(needed_nodes):
            raise GraphCycleError(
                f"Cycle detected in prerequisite graph while computing learning path "
                f"for '{target_concept_id}'."
            )

        return order
