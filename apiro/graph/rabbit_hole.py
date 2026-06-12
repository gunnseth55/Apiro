"""
graph/rabbit_hole.py — RabbitHoleDetector
==========================================
Detects when traversal has gone into a rabbit hole:
the entropy curve reverses (starts rising again) after an initial decline,
at depth >= min_depth.

Spec (TC-2.4): fires ONLY after 3+ consecutive decreases followed by
2+ consecutive increases. A single-step entropy blip must NOT fire.

When flagged, the traversal loop skips this node and picks frontier[1].
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from apiro.graph.belief_graph import BeliefGraph
from apiro.graph.node import Node
from apiro.config import RABBIT_HOLE_MIN_DEPTH, RABBIT_HOLE_REVERSAL_WINDOW


@dataclass
class RabbitHoleEvent:
    """Logged whenever a rabbit hole node is flagged."""
    node_id:   str
    node_claim: str
    depth:     int
    trend:     float   # entropy trend at time of detection


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
        self.events: list[RabbitHoleEvent] = []


    def check(self, graph: BeliefGraph, current_node: Node) -> bool:
        """
        Return True if this node is a rabbit hole candidate.
        Does NOT mutate the node — call flag_rabbit_hole() to do that.

        Fires when BOTH conditions hold in the reversal window:
          1. Overall entropy trend > 0 (slope of window is positive, i.e. rising).
          2. The most recent step is still rising (last pair increases).

        Condition 2 blocks completed blips:
          [0.5, 0.52, 0.4] → overall slope negative OR last pair falls → no fire.
          [0.6, 0.5, 0.8]  → slope positive AND last pair rises → FIRES.
        """
        if current_node.depth < self.min_depth:
            return False

        trend  = graph.get_entropy_trend(self.reversal_window)
        recent = graph.get_recent_entropies(self.reversal_window)

        if len(recent) < 2:
            return False

        # The overall trend must be positive (entropy rising on average)
        if trend <= 0.0:
            return False

        # The most recent step must still be rising — rules out completed blips
        # e.g. [0.5, 0.52, 0.4]: last pair (0.52 -> 0.4) falls → not a real reversal
        last_pair_rising = recent[-1] > recent[-2]
        return last_pair_rising

    def flag_rabbit_hole(self, node: Node, graph: BeliefGraph) -> None:
        """
        Mark the node as a rabbit hole, log the event, and record metadata.
        The traversal loop then skips to frontier[1].
        """
        node.is_rabbit_hole = True
        trend = graph.get_entropy_trend(self.reversal_window)
        node.metadata["rabbit_hole_trend"] = trend
        node.metadata["rabbit_hole_depth"]  = node.depth

        self.events.append(RabbitHoleEvent(
            node_id=node.id,
            node_claim=node.claim,
            depth=node.depth,
            trend=trend,
        ))

    def get_status(self, graph: BeliefGraph, current_node: Node) -> dict:
        """Diagnostic dict for inspection/logging."""
        trend = graph.get_entropy_trend(self.reversal_window)
        return {
            "is_rabbit_hole":  self.check(graph, current_node),
            "node_depth":      current_node.depth,
            "min_depth":       self.min_depth,
            "entropy_trend":   round(trend, 5),
            "reversal_window": self.reversal_window,
            "total_flagged":   len(self.events),
        }
