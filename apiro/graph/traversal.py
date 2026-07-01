"""
graph/traversal.py
------------------
Main orchestration loop for Apiro Phase 2.

ApiroTraversal ties together all Phase 2 components:
  - NodeExpander:          expands frontier nodes into child hypotheses
  - SaturationDetector:    stops when entropy has settled
  - RabbitHoleDetector:    skips branches where entropy reverses
  - ContradictionDetector: flags logical conflicts between nodes

THE LOOP (entropy-first BFS):
  1. Check saturation → stop if saturated
  2. Get frontier (unresolved nodes sorted by entropy DESC)
  3. Stop if frontier is empty or max_depth exceeded
  4. Check if top node is a rabbit hole → skip to frontier[1] if so
  5. Expand the top node via NodeExpander (RAG + LLM → 3 children)
  6. Run full contradiction check: each new child vs ALL existing nodes
  7. Mark node as resolved, log, repeat

STOP CONDITIONS (in priority order):
  1. Saturation: entropy has settled (low, stable, non-rising)
  2. Max depth: hard limit to prevent infinite loops
  3. Empty frontier: all nodes resolved or skipped
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from apiro.config import CONTRADICTION_THRESHOLD_EF, CONTRADICTION_PENALTY

logger = logging.getLogger(__name__)



@dataclass
class TraversalResult:
    """
    Summary returned by ApiroTraversal.run().

    Contains the final graph state and run statistics for export and testing.
    """
    graph:               object
    stop_reason:         str      # "saturation" | "max_depth" | "no_frontier"
    total_nodes:         int
    total_edges:         int
    rabbit_hole_count:   int
    contradiction_count: int
    duration_seconds:    float
    synthesis:           list[str]        # Final differential diagnosis
    saturation_status:   Optional[object] = None  # SaturationStatus if stop was saturation


class ApiroTraversal:
    """
    Orchestrates the entropy-first belief graph traversal.

    Args:
        expander:    NodeExpander instance
        saturation:  SaturationDetector instance
        rabbit_hole: RabbitHoleDetector instance
        contradiction: ContradictionDetector instance
        log_dir:     Directory to write traversal_log_{case_name}.jsonl
    """

    def __init__(
        self,
        expander,
        saturation,
        rabbit_hole,
        contradiction,
        log_dir: str = "data",
    ):
        self.expander    = expander
        self.saturation  = saturation
        self.rabbit_hole = rabbit_hole
        self.contradiction = contradiction
        self.log_dir     = log_dir
        self._traversal_log: list[dict] = []

    # ── Logging helpers ───────────────────────────────────────────────────────

    def _log(self, event: dict) -> None:
        """Append a structured event to the in-memory traversal log."""
        self._traversal_log.append(event)

    def _write_log(self, case_name: str) -> str:
        """Write the traversal log to a JSONL file and return the path."""
        os.makedirs(self.log_dir, exist_ok=True)
        log_path = os.path.join(self.log_dir, f"traversal_log_{case_name}.jsonl")
        with open(log_path, "w") as f:
            for event in self._traversal_log:
                f.write(json.dumps(event) + "\n")
        logger.info(f"[Traversal] Log written to {log_path}")
        return log_path

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(
        self,
        seed_nodes: list,
        graph,
        max_depth: int = 8,
        case_name: str = "run",
    ) -> TraversalResult:
        """
        Run the entropy-first traversal loop.

        Args:
            seed_nodes: list of Node objects to start from
            graph:      empty BeliefGraph to populate
            max_depth:  hard stop — prevents infinite loops
            case_name:  used for log filename

        Returns:
            TraversalResult with the populated graph and run statistics
        """
        start_time = time.time()
        self._traversal_log = []

        # ── Seed the graph ────────────────────────────────────────────────────
        for seed in seed_nodes:
            graph.add_node(seed)
            self._log({
                "event":   "seed_added",
                "node_id": seed.id,
                "claim":   seed.claim,
                "entropy": seed.entropy_score,
                "domain":  seed.domain,
            })

        logger.info(f"[Traversal] Starting with {len(seed_nodes)} seed nodes")

        stop_reason = "no_frontier"
        iteration   = 0

        # ── Main loop ─────────────────────────────────────────────────────────
        while True:
            iteration += 1

            # ── Stop condition 1: Saturation ─────────────────────────────────
            if self.saturation.is_saturated(graph):
                status = self.saturation.get_status(graph)
                stop_reason = "saturation"
                logger.info(
                    f"[Traversal] SATURATED at iteration {iteration}. "
                    f"avg_entropy={status['avg_entropy']:.3f}, "
                    f"variance={status['variance']:.4f}, "
                    f"trend={status['trend']:.4f}"
                )
                self._log({
                    "event":       "saturation_fired",
                    "iteration":   iteration,
                    "avg_entropy": status["avg_entropy"],
                    "variance":    status["variance"],
                    "trend":       status["trend"],
                })
                break

            # ── Get frontier with depth-aware EF scoring ──────────────────────
            # depth_aware=True: depth-0 nodes sorted by certainty (1-H),
            # depth>=1 nodes sorted by uncertainty (H) to chase differentials.
            frontier = graph.get_frontier(depth_aware=True)

            if not frontier:
                stop_reason = "no_frontier"
                logger.info(f"[Traversal] Frontier empty at iteration {iteration}.")
                break

            # ── Stop condition 2: Max depth ───────────────────────────────────
            if frontier[0].depth >= max_depth:
                stop_reason = "max_depth"
                logger.info(f"[Traversal] Max depth {max_depth} reached.")
                break

            # ── Pick best node ────────────────────────────────────────────────
            node = frontier[0]

            # ── Stop condition 3: Rabbit hole check ──────────────────────────
            # If the top node is a rabbit hole, flag it and restart the loop.
            # The next call to get_frontier() will naturally exclude it, so
            # frontier[1] becomes the new top and passes all safety checks.
            if self.rabbit_hole.check(graph, node):
                self.rabbit_hole.flag_rabbit_hole(node, graph)
                self._log({
                    "event":   "rabbit_hole_flagged",
                    "node_id": node.id,
                    "claim":   node.claim,
                    "depth":   node.depth,
                    "entropy": node.entropy_score,
                })
                logger.warning(f"[Traversal] Rabbit hole: '{node.claim[:60]}' — skipping.")
                continue  # restart loop; get_frontier will exclude flagged node

            # ── Expand the node ───────────────────────────────────────────────
            logger.info(
                f"[Traversal] iter={iteration} expanding: '{node.claim[:60]}' "
                f"(depth={node.depth}, entropy={node.entropy_score:.3f})"
            )

            self._log({
                "event":     "expanding",
                "iteration": iteration,
                "node_id":   node.id,
                "claim":     node.claim,
                "entropy":   node.entropy_score,
                "depth":     node.depth,
            })

            new_nodes = self.expander.expand(node, graph)
            graph.mark_resolved(node.id)

            # ── Contradiction check: new nodes vs ALL existing nodes ───────────
            existing_nodes = list(graph.nodes.values())

            for new_node in new_nodes:
                self._log({
                    "event":     "node_expanded",
                    "node_id":   new_node.id,
                    "claim":     new_node.claim,
                    "entropy":   new_node.entropy_score,
                    "domain":    new_node.domain,
                    "depth":     new_node.depth,
                    "parent_id": new_node.parent_id,
                })

                for existing in existing_nodes:
                    if existing.id == new_node.id:
                        continue

                    # ── Abstraction-layer gate ────────────────────────────────
                    # Only run expensive NLI when both claims are at the same
                    # clinical abstraction level (both hypotheses, or both raw
                    # observations of the same type). Cross-level checks
                    # (hypothesis vs raw observation) produce false positives.
                    if not self.contradiction.should_check(new_node.claim, existing.claim):
                        logger.debug(
                            f"[Traversal] Contradiction gate: skipping cross-abstraction "
                            f"pair '{new_node.claim[:30]}' vs '{existing.claim[:30]}'"
                        )
                        continue

                    result = self.contradiction.check(new_node.claim, existing.claim)

                    if result.label == "contradiction" and result.score > CONTRADICTION_THRESHOLD_EF:

                        # Find the edge and flag it
                        for edge in graph.edges:
                            if edge.parent_id == new_node.parent_id and edge.child_id == new_node.id:
                                edge.contradiction_flag = True

                        self._log({
                            "event":              "contradiction_flagged",
                            "node_a":             new_node.claim[:80],
                            "node_b":             existing.claim[:80],
                            "score":              round(result.score, 3),
                            "negation_detected":  result.negation_detected,
                        })
                        logger.info(
                            f"[Traversal] Contradiction: '{new_node.claim[:40]}' "
                            f"vs '{existing.claim[:40]}' (score={result.score:.3f})"
                        )

                        # ── Contradiction-informed soft-pruning ───────────────
                        # The lower-entropy node carries less information and is
                        # more likely to be a spurious tangent. We apply a score
                        # penalty to push it down the traversal frontier queue.
                        new_h      = new_node.entropy_score  or 0.0
                        existing_h = existing.entropy_score  or 0.0
                        weaker = new_node if new_h <= existing_h else existing
                        weaker.contradiction_penalty = CONTRADICTION_PENALTY
                        logger.info(
                            f"[Traversal] Soft-pruned weaker contradicting node: "
                            f"'{weaker.claim[:50]}' (entropy={weaker.entropy_score:.3f}, penalty={CONTRADICTION_PENALTY})"
                        )


        # ── Wrap up ───────────────────────────────────────────────────────────
        duration = round(time.time() - start_time, 2)

        # ── Synthesize differential ───────────────────────────────────────────
        synthesis = self.expander.synthesize_differential(graph)

        self._log({
            "event":            "traversal_complete",
            "stop_reason":      stop_reason,
            "total_nodes":      graph.node_count(),
            "total_edges":      len(graph.edges),
            "synthesis":        synthesis,
            "duration_seconds": duration,
        })

        self._write_log(case_name)

        sat_status = self.saturation.get_status(graph) if stop_reason == "saturation" else None

        result = TraversalResult(
            graph=graph,
            stop_reason=stop_reason,
            total_nodes=graph.node_count(),
            total_edges=len(graph.edges),
            rabbit_hole_count=len(self.rabbit_hole.events),
            contradiction_count=len(graph.get_contradiction_edges()),
            duration_seconds=duration,
            synthesis=synthesis,
            saturation_status=sat_status,
        )

        logger.info(
            f"[Traversal] Done. stop={stop_reason}, nodes={result.total_nodes}, "
            f"edges={result.total_edges}, rabbit_holes={result.rabbit_hole_count}, "
            f"contradictions={result.contradiction_count}, time={duration}s"
        )

        return result
