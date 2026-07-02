"""
graph/breadth_first.py
=======================
Breadth-first traversal baseline for comparison against Apiro's entropy-first
strategy in the Phase 3 evaluation.

The only difference from ApiroTraversal (graph/traversal.py):
  - get_frontier() returns nodes in insertion order (FIFO queue) instead of
    entropy-descending order.
  - All other logic (saturation, rabbit hole, contradiction) is identical.

This is the "dumb" baseline that doesn't use entropy as a priority signal.
If Apiro's entropy-first traversal consistently finds the ground-truth diagnosis
in fewer node expansions, the core claim of the paper is validated.
"""

from __future__ import annotations

import logging
import time
from collections import deque

from apiro.graph.belief_graph import BeliefGraph
from apiro.graph.node import Node
from apiro.graph.edge import Edge
from apiro.graph.traversal import TraversalResult
from apiro.config import CONTRADICTION_THRESHOLD_BF


logger = logging.getLogger(__name__)


class BreadthFirstTraversal:
    """
    FIFO traversal baseline — expands nodes in the order they were added,
    ignoring entropy scores. Used as the comparison baseline in Phase 3 evaluation.

    Args:
        expander:      NodeExpander (shared with entropy-first traversal).
        saturation:    SaturationDetector (same theta/window as entropy-first).
        rabbit_hole:   RabbitHoleDetector (same parameters as entropy-first).
        contradiction: ContradictionDetector (same model as entropy-first).
        max_depth:     Maximum node depth before stopping.
        max_nodes:     Hard cap on total expanded nodes.
    """

    def __init__(
        self,
        expander,
        saturation,
        rabbit_hole,
        contradiction,
        max_depth: int = 5,
        max_nodes: int = 50,
    ):
        self.expander      = expander
        self.saturation    = saturation
        self.rabbit_hole   = rabbit_hole
        self.contradiction = contradiction
        self.max_depth     = max_depth
        self.max_nodes     = max_nodes

    def run(self, seed_nodes: list[Node], graph: BeliefGraph) -> TraversalResult:
        """
        Run breadth-first traversal from seed nodes.

        Signature matches ApiroTraversal.run() so both are interchangeable
        in the evaluator.

        Args:
            seed_nodes: List of Node objects to seed the graph.
            graph:      Empty BeliefGraph to populate (passed in for consistency
                        with ApiroTraversal API).

        Returns:
            TraversalResult with populated graph and run statistics.
        """
        queue: deque[Node] = deque()

        for seed in seed_nodes:
            graph.add_node(seed)
            queue.append(seed)

        start_time     = time.time()
        expanded       = 0
        stop_reason    = "frontier_empty"
        rabbit_holes   = 0
        contradictions = 0

        while queue:
            # Saturation check (same as entropy-first)
            if self.saturation.is_saturated(graph):
                stop_reason = "saturation"
                break

            node = queue.popleft()

            # Skip already-resolved nodes (can happen if added multiple times)
            if node.resolved:
                continue

            # Depth / node cap
            if node.depth >= self.max_depth:
                continue
            if expanded >= self.max_nodes:
                stop_reason = "max_nodes"
                break

            # Rabbit hole check
            if self.rabbit_hole.check(graph, node):
                self.rabbit_hole.flag_rabbit_hole(node, graph)
                rabbit_holes += 1
                logger.info(f"[BreadthFirst] Rabbit hole: '{node.claim[:60]}' — skipping.")
                continue

            # Expand
            try:
                new_nodes = self.expander.expand(node, graph)
            except Exception as e:
                logger.warning(f"[BreadthFirst] Expand failed for '{node.claim[:40]}': {e}")
                graph.mark_resolved(node.id)
                continue

            graph.mark_resolved(node.id)
            expanded += 1

            # Add children and check contradictions
            for new_node in new_nodes:
                graph.add_node(new_node)
                queue.append(new_node)   # FIFO — no entropy ordering

                for existing in list(graph.nodes.values()):
                    if existing.id == new_node.id:
                        continue
                    try:
                        result = self.contradiction.check(new_node.claim, existing.claim)
                        if result.label == "contradiction" and result.score > CONTRADICTION_THRESHOLD_BF:

                            edge = Edge(
                                parent_id=new_node.id,
                                child_id=existing.id,
                                relation="contradicts",
                                contradiction_flag=True,
                                confidence=float(result.score),
                            )
                            graph.add_edge(edge)
                            contradictions += 1
                    except Exception:
                        pass

        duration = round(time.time() - start_time, 2)
        
        # ── Synthesize differential ───────────────────────────────────────────
        try:
            synthesis = self.expander.synthesize_differential(graph)
        except Exception as e:
            logger.error(f"[BreadthFirst] Synthesis failed: {e}")
            synthesis = ["[Synthesis failed]"]

        return TraversalResult(
            graph=graph,
            stop_reason=stop_reason,
            total_nodes=len(graph.nodes),
            total_edges=len(graph.edges),
            rabbit_hole_count=rabbit_holes,
            contradiction_count=contradictions,
            duration_seconds=duration,
            synthesis=synthesis,
        )
