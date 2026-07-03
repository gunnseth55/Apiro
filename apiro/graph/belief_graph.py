"""
graph/belief_graph.py — BeliefGraph
=====================================
NetworkX-backed directed graph of clinical hypotheses.
The frontier (unresolved nodes sorted by entropy descending) is the
core data structure that drives the entropy-first traversal loop.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import networkx as nx
import numpy as np

from apiro.graph.node import Node
from apiro.graph.edge import Edge


class BudgetExceededError(Exception):
    """Exception raised when the node budget is exceeded."""
    pass


class BeliefGraph:
    """
    Directed acyclic graph of clinical Nodes connected by typed Edges.

    The key invariant: `get_frontier()` always returns unresolved nodes
    sorted by `entropy_score` descending — the traversal loop always
    picks `frontier[0]` (highest uncertainty) to expand next.
    """

    def __init__(self, max_depth: int = 6, max_nodes: int = 150):
        self._graph: nx.DiGraph   = nx.DiGraph()
        self.nodes:  dict[str, Node] = {}   # id → Node
        self.edges:  list[Edge]      = []
        self._expansion_log: list[dict] = []  # ordered history of expanded nodes
        self.max_depth = max_depth
        self.max_nodes = max_nodes

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """Add a node. Silently ignores duplicate IDs. Enforces budget and depth limits."""
        if node.id in self.nodes:
            return
        if len(self.nodes) >= self.max_nodes:
            raise BudgetExceededError(f"Attempted to exceed node budget of {self.max_nodes}")
        if node.depth > self.max_depth:
            # depth enforcement: node at depth 7 rejected when max_depth=6
            return
        self.nodes[node.id] = node
        self._graph.add_node(node.id, entropy=node.entropy_score, domain=node.domain)

    def add_edge(self, edge: Edge) -> None:
        """Add a directed edge. Both nodes must already exist."""
        if edge.parent_id not in self.nodes:
            raise ValueError(f"Parent node {edge.parent_id!r} not in graph.")
        if edge.child_id not in self.nodes:
            raise ValueError(f"Child node {edge.child_id!r} not in graph.")
        self.edges.append(edge)
        self._graph.add_edge(
            edge.parent_id, edge.child_id,
            relation=edge.relation,
            contradiction_flag=edge.contradiction_flag,
            confidence=edge.confidence,
        )

    def mark_resolved(self, node_id: str) -> None:
        """Mark a node as expanded. Records it in the expansion log."""
        if node_id not in self.nodes:
            raise KeyError(f"Node {node_id!r} not found.")
        node = self.nodes[node_id]
        node.resolved = True
        self._expansion_log.append({
            "node_id":      node_id,
            "entropy":      node.entropy_score,
            "domain":       node.domain,
            "depth":        node.depth,
            "is_rabbit_hole": node.is_rabbit_hole,
        })

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_frontier(self, depth_aware: bool = False) -> list[Node]:
        """
        Return all unresolved, non-rabbit-hole nodes sorted by score.

        Args:
            depth_aware: If False (default), sorts strictly by entropy_score descending
                         — the standard baseline contract expected by unit tests.
                         If True, uses depth-aware scoring for the entropy-first traversal:
                           - Depth 0 (seeds): score = 2.0 - entropy, guaranteeing all seeds
                             are expanded before any derived child node (starvation-proof).
                           - Depth >= 1 (derived): score = entropy (chase uncertainty/differentials)
        """
        candidates = [n for n in self.nodes.values() if not n.resolved and not n.is_rabbit_hole]

        if depth_aware:
            def score(n: Node) -> float:
                h = n.entropy_score if n.entropy_score is not None else 0.5
                # Depth 0: always prioritize seed nodes to prevent starvation
                base_score = (2.0 - h) if n.depth == 0 else h
                return base_score - getattr(n, "contradiction_penalty", 0.0)
        else:
            def score(n: Node) -> float:
                h = n.entropy_score if n.entropy_score is not None else 0.0
                return h - getattr(n, "contradiction_penalty", 0.0)

        return sorted(candidates, key=score, reverse=True)

    def get_entropy_trend(self, window: int = 5) -> float:
        """
        Linear trend coefficient of entropy over the last `window` expansions.
        Positive = entropy rising (rabbit hole risk).
        Negative = entropy declining (converging toward saturation).
        Returns 0.0 if fewer than 2 expansions have occurred.
        """
        log = self._expansion_log[-window:]
        if len(log) < 2:
            return 0.0
        entropies = [e["entropy"] for e in log]
        x = np.arange(len(entropies), dtype=float)
        slope = float(np.polyfit(x, entropies, 1)[0])
        return round(slope, 9)

    def get_recent_entropies(self, window: int = 5) -> list[float]:
        """Return entropy values from the last `window` expanded nodes."""
        return [e["entropy"] for e in self._expansion_log[-window:]]

    def get_contradiction_edges(self) -> list[Edge]:
        """Return all edges that were flagged as contradictions."""
        return [e for e in self.edges if e.contradiction_flag]

    def children_of(self, node_id: str) -> list[Node]:
        """Return direct children of a node."""
        return [self.nodes[c] for c in self._graph.successors(node_id) if c in self.nodes]

    def parents_of(self, node_id: str) -> list[Node]:
        """Return direct parents of a node."""
        return [self.nodes[p] for p in self._graph.predecessors(node_id) if p in self.nodes]

    def node_count(self) -> int:
        """Return total number of nodes (alias for n_nodes, used by traversal)."""
        return len(self.nodes)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    @property
    def n_edges(self) -> int:
        return len(self.edges)

    @property
    def n_resolved(self) -> int:
        return sum(1 for n in self.nodes.values() if n.resolved)

    @property
    def n_rabbit_holes(self) -> int:
        return sum(1 for n in self.nodes.values() if n.is_rabbit_hole)

    @property
    def mean_entropy(self) -> Optional[float]:
        entropies = [n.entropy_score for n in self.nodes.values()]
        return float(np.mean(entropies)) if entropies else None

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def to_networkx(self) -> nx.DiGraph:
        """Return the underlying NetworkX DiGraph (read-only view)."""
        return self._graph

    def export_json(self, path: Path | None = None) -> dict:
        """
        Serialise the graph to a dict (always returned) and optionally write
        it to a JSON file when `path` is given.

        Format:
          {
            "nodes": [{id, claim, domain, entropy_score, resolved, depth, ...}],
            "edges": [{parent_id, child_id, relation, contradiction_flag, confidence}],
            "expansion_log": [...],
            "stats": {n_nodes, n_edges, n_resolved, n_rabbit_holes, mean_entropy}
          }
        """
        data = {
            "nodes": [
                {
                    "id":            n.id,
                    "claim":         n.claim,
                    "domain":        n.domain,
                    "entropy_score": n.entropy_score,
                    "resolved":      n.resolved,
                    "is_rabbit_hole": n.is_rabbit_hole,
                    "contradiction_penalty": getattr(n, "contradiction_penalty", 0.0),
                    "depth":         n.depth,
                    "parent_id":     n.parent_id,
                    "sources":       n.sources,
                    "metadata":      n.metadata,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "parent_id":         e.parent_id,
                    "child_id":          e.child_id,
                    "relation":          e.relation,
                    "contradiction_flag": e.contradiction_flag,
                    "confidence":        e.confidence,
                }
                for e in self.edges
            ],
            "expansion_log": self._expansion_log,
            "stats": {
                "n_nodes":        self.n_nodes,
                "n_edges":        self.n_edges,
                "n_resolved":     self.n_resolved,
                "n_rabbit_holes": self.n_rabbit_holes,
                "mean_entropy":   self.mean_entropy,
            },
        }
        if path is not None:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w") as f:
                json.dump(data, f, indent=2)
        return data

    @classmethod
    def from_json(cls, path: Path) -> "BeliefGraph":
        """Load a previously exported graph back into memory."""
        from apiro.graph.node import Node
        from apiro.graph.edge import Edge
        with open(path) as f:
            data = json.load(f)
        g = cls()
        for n in data["nodes"]:
            g.add_node(Node(**n))
        for e in data["edges"]:
            g.add_edge(Edge(**e))
        g._expansion_log = data.get("expansion_log", [])
        return g

    def __repr__(self) -> str:
        return (
            f"BeliefGraph(nodes={self.n_nodes}, edges={self.n_edges}, "
            f"resolved={self.n_resolved}, frontier={len(self.get_frontier())}, "
            f"rabbit_holes={self.n_rabbit_holes})"
        )
