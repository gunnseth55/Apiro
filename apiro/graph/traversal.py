"""
graph/traversal.py
------------------
Contains two traversal strategies:

1. ApiroTraversal (CLASSIC) — Phase 2 generative expansion:
   Entropy-first BFS that blindly expands frontier nodes via LLM.
   Kept for backwards compatibility and comparison.

2. HypothesisTestingTraversal (NEW) — hypothesis-testing inference:
   Phase 1: Extract structured PatientContext.
   Phase 2: Generate N candidate diagnoses via HypothesisOracle (1 LLM call).
   Phase 3: Score each hypothesis deterministically via EvidenceMatcher (0 LLM calls).
   Phase 4: Apply demographic constraints via BayesianScorer (0 LLM calls).
   Phase 5 (optional): Targeted graph enrichment for top-3 hypotheses only.

Select via the `--mode classic|hypothesis` flag in run.py.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from apiro.config import CONTRADICTION_THRESHOLD_EF, CONTRADICTION_PENALTY
from apiro.graph.belief_graph import BudgetExceededError

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


@dataclass
class HypothesisTestingResult:
    """
    Summary returned by HypothesisTestingTraversal.run().

    Carries the ranked hypotheses, evidence scores, and timing stats.
    """
    synthesis:           list[str]              # Top 3 diagnoses
    ranked_hypotheses:   list                   # list[RankedHypothesis]
    duration_seconds:    float
    patient_context:     object                 # PatientContext
    stop_reason:         str = "scored"
    # Classic graph stats (populated if graph enrichment ran)
    total_nodes:         int = 0
    total_edges:         int = 0
    rabbit_hole_count:   int = 0
    contradiction_count: int = 0
    graph:               Optional[object] = None


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
        vignette: str = None,
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

            try:
                new_nodes = self.expander.expand(node, graph)
            except BudgetExceededError as e:
                logger.warning(f"[Traversal] Budget exceeded: {e}. Stopping traversal gracefully.")
                stop_reason = "budget_exceeded"
                break
            graph.mark_resolved(node.id)

            # ── Contradiction check: new nodes vs ALL existing nodes ───────────
            # Collect all pairs that pass the domain gate first, then run a
            # single batched NLI forward pass instead of one GPU call per pair.
            existing_nodes = list(graph.nodes.values())

            batch_pairs:   list[tuple[str, str]]      = []
            batch_meta:    list[tuple[object, object]] = []  # (new_node, existing)

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
                    if not self.contradiction.should_check(new_node.claim, existing.claim):
                        logger.debug(
                            f"[Traversal] Contradiction gate: skipping cross-abstraction "
                            f"pair '{new_node.claim[:30]}' vs '{existing.claim[:30]}'"
                        )
                        continue

                    # Single pair NLI check (bypasses batched GPU kernel bugs, matches cache)
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
                        # Seed nodes (depth 0) are ground truth and must never be penalized.
                        # If a hypothesis contradicts ground truth, the hypothesis is penalized.
                        if new_node.depth == 0 and existing.depth == 0:
                            # Both are ground truth, do not penalize either
                            continue
                        elif new_node.depth == 0:
                            weaker = existing
                        elif existing.depth == 0:
                            weaker = new_node
                        else:
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


# ── HypothesisTestingTraversal ────────────────────────────────────────────────

class HypothesisTestingTraversal:
    """
    New hypothesis-testing inference engine.

    Pipeline (1-3 LLM calls total vs 100+ in classic mode):

    Phase 1 — PatientContext extraction (1 LLM call).
    Phase 2 — Hypothesis Generation via HypothesisOracle (1 LLM call).
    Phase 3 — Deterministic Scoring via EvidenceMatcher + BayesianScorer (0 LLM calls).
    Phase 4 — Optional targeted graph enrichment for top-3 hypotheses (0-6 LLM calls).
    """

    def __init__(
        self,
        oracle,
        matcher,
        scorer,
        expander=None,
        saturation=None,
        rabbit_hole=None,
        contradiction=None,
        n_hypotheses: int = 8,
        enrich_top_k: int = 3,
        log_dir: str = "data",
    ):
        self.oracle = oracle
        self.matcher = matcher
        self.scorer = scorer
        self.expander = expander
        self.saturation = saturation
        self.rabbit_hole = rabbit_hole
        self.contradiction = contradiction
        self.n_hypotheses = n_hypotheses
        self.enrich_top_k = enrich_top_k
        self.log_dir = log_dir
        self._traversal_log: list[dict] = []

    def run(
        self,
        vignette: str,
        case_name: str = "run",
        seed_nodes: list = None,
        graph=None,
        max_depth: int = 2,
    ) -> "HypothesisTestingResult":
        from apiro.patient.context import extract_patient_context

        start_time = time.time()
        self._traversal_log = []

        # Phase 1: PatientContext
        logger.info("[HypothesisTestingTraversal] Phase 1: Extracting PatientContext...")
        context = extract_patient_context(vignette)
        self._log({"event": "patient_context_extracted", "summary": context.summary()})
        logger.info(f"[HypothesisTestingTraversal] PatientContext: {context.summary()}")

        # Phase 2: Generate candidates
        logger.info(f"[HypothesisTestingTraversal] Phase 2: Generating {self.n_hypotheses} candidates...")
        hypotheses = self.oracle.generate(context, n=self.n_hypotheses)
        self._log({"event": "hypotheses_generated", "hypotheses": hypotheses})
        logger.info(f"[HypothesisTestingTraversal] Candidates: {hypotheses}")

        if not hypotheses:
            logger.warning("[HypothesisTestingTraversal] Oracle returned no hypotheses.")
            return HypothesisTestingResult(
                synthesis=[],
                ranked_hypotheses=[],
                duration_seconds=round(time.time() - start_time, 2),
                patient_context=context,
                stop_reason="oracle_failure",
            )

        # Phase 3: Score deterministically
        logger.info(f"[HypothesisTestingTraversal] Phase 3: Scoring {len(hypotheses)} hypotheses...")
        evidence_scores = self.matcher.score_all(hypotheses, context)
        ranked = self.scorer.rank(evidence_scores, context)
        self._log({
            "event": "hypotheses_scored",
            "ranked": [{"rank": r.rank, "hypothesis": r.hypothesis,
                        "raw_score": r.raw_score, "final_score": r.final_score,
                        "matched": len(r.matched_findings), "rules": r.rule_notes}
                       for r in ranked],
        })
        for r in ranked[:5]:
            logger.info(f"  {r}")

        synthesis = [r.hypothesis for r in ranked[:3] if r.final_score > 0.0]

        # Phase 4 (optional): Targeted graph enrichment
        total_nodes = 0
        total_edges = 0
        rabbit_holes = 0
        contradictions = 0
        enriched_graph = None

        if self.expander and graph is not None and synthesis:
            logger.info(f"[HypothesisTestingTraversal] Phase 4: Enriching top {min(self.enrich_top_k, len(synthesis))} hypotheses...")
            from apiro.graph.node import Node
            for i, hyp in enumerate(synthesis[:self.enrich_top_k]):
                hyp_node = Node(id=f"hyp_{i}", claim=hyp, entropy_score=0.693,
                                domain="pathophysiology", depth=0)
                graph.add_node(hyp_node)
                self._log({"event": "enrichment_seed", "hypothesis": hyp, "node_id": f"hyp_{i}"})
                try:
                    new_nodes = self.expander.expand(hyp_node, graph)
                    graph.mark_resolved(hyp_node.id)
                    if self.contradiction:
                        existing = list(graph.nodes.values())
                        for nn in new_nodes:
                            for ex in existing:
                                if ex.id == nn.id:
                                    continue
                                if not self.contradiction.should_check(nn.claim, ex.claim):
                                    continue
                                res = self.contradiction.check(nn.claim, ex.claim)
                                if res.label == "contradiction" and res.score > CONTRADICTION_THRESHOLD_EF:
                                    contradictions += 1
                                    nn.contradiction_penalty = CONTRADICTION_PENALTY
                except BudgetExceededError:
                    logger.warning("[HypothesisTestingTraversal] Graph budget exceeded.")
                    break
                except Exception as e:
                    logger.warning(f"[HypothesisTestingTraversal] Enrichment error: {e}")
            enriched_graph = graph
            total_nodes = graph.node_count()
            total_edges = len(graph.edges)
            if self.rabbit_hole:
                rabbit_holes = len(self.rabbit_hole.events)

        duration = round(time.time() - start_time, 2)
        self._log({"event": "traversal_complete", "stop_reason": "scored",
                   "synthesis": synthesis, "duration_seconds": duration})
        self._write_log(case_name)
        logger.info(f"[HypothesisTestingTraversal] Done. synthesis={synthesis}, time={duration}s")

        return HypothesisTestingResult(
            synthesis=synthesis,
            ranked_hypotheses=ranked,
            duration_seconds=duration,
            patient_context=context,
            stop_reason="scored",
            total_nodes=total_nodes,
            total_edges=total_edges,
            rabbit_hole_count=rabbit_holes,
            contradiction_count=contradictions,
            graph=enriched_graph,
        )

    def _log(self, event: dict) -> None:
        self._traversal_log.append(event)

    def _write_log(self, case_name: str) -> str:
        os.makedirs(self.log_dir, exist_ok=True)
        log_path = os.path.join(self.log_dir, f"ht_traversal_log_{case_name}.jsonl")
        with open(log_path, "w") as f:
            for event in self._traversal_log:
                f.write(json.dumps(event) + "\n")
        logger.info(f"[HypothesisTestingTraversal] Log written to {log_path}")
        return log_path
