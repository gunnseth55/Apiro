"""
graph/rabbit_hole.py — RabbitHoleDetector
==========================================
Detects when traversal has gone into a rabbit hole:
the entropy curve reverses (starts rising again) after an initial decline,
at depth >= min_depth.

When flagged, the traversal loop skips this node and picks frontier[1].
"""
from __future__ import annotations

import numpy as np

from apiro.graph.belief_graph import BeliefGraph
from apiro.graph.node import Node
from apiro.config import RABBIT_HOLE_MIN_DEPTH, RABBIT_HOLE_REVERSAL_WINDOW


class RabbitHoleDetector:
    """
    Fires when:
      1. current_node.depth >= min_depth (not a root-level node)
      2. The entropy trend over the last `reversal_window` expanded nodes
         has turned POSITIVE (entropy rising after initial decline).
    """

    def __init__(
        self,
        min_depth: int = RABBIT_HOLE_MIN_DEPTH,
        reversal_window: int = RABBIT_HOLE_REVERSAL_WINDOW,
    ):
        self.min_depth       = min_depth
        self.reversal_window = reversal_window

    def check(self, graph: BeliefGraph, current_node: Node) -> bool:
        """
        Return True if this node is a rabbit hole candidate.
        Does NOT mutate the node — call flag_rabbit_hole() to do that.
        """
        if current_node.depth < self.min_depth:
            return False

        trend = graph.get_entropy_trend(self.reversal_window)
        return trend > 0.0

    def flag_rabbit_hole(self, node: Node, graph: BeliefGraph) -> None:
        """
        Mark the node as a rabbit hole and log it.
        The traversal loop should then skip to frontier[1].
        """
        node.is_rabbit_hole = True
        node.metadata["rabbit_hole_trend"] = graph.get_entropy_trend(self.reversal_window)
        node.metadata["rabbit_hole_depth"]  = node.depth

    def get_status(self, graph: BeliefGraph, current_node: Node) -> dict:
        """Diagnostic dict for inspection/logging."""
        trend = graph.get_entropy_trend(self.reversal_window)
        return {
            "is_rabbit_hole":  self.check(graph, current_node),
            "node_depth":      current_node.depth,
            "min_depth":       self.min_depth,
            "entropy_trend":   round(trend, 5),
            "reversal_window": self.reversal_window,
        }
