"""
eval/evaluator.py
==================
Phase 3 evaluation harness for Apiro.

Runs each MIMIC-III case through two traversal strategies and measures which
finds the ground-truth diagnosis faster.

Metrics per case:
  1. diagnostic_hit   — does ground-truth diagnosis appear as a node? (bool)
  2. path_length      — node expansions before ground-truth appears (-1 if miss)
  3. entropy_auc      — area under the entropy-vs-expansion curve (lower = better)
  4. rabbit_holes     — count of rabbit hole events fired
  5. contradictions   — count of contradiction edges flagged
  6. traversal_winner — "entropy_first" | "breadth_first" | "tie" | "both_miss"

Comparison:
  Run each case entropy-first AND breadth-first with the same expander/detectors.
  If entropy_first path_length < breadth_first path_length → entropy_first wins.
  Phase 3 target: entropy_first wins ≥ 7/10 cases.

Usage:
    from apiro.eval.evaluator import CaseEvaluator
    ev = CaseEvaluator(expander, saturation, rabbit_hole, contradiction)
    results = ev.evaluate_all(cases, output_path="data/eval_results.json")
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

from apiro.graph.belief_graph import BeliefGraph
from apiro.graph.node import Node
from apiro.graph.traversal import ApiroTraversal, TraversalResult
from apiro.graph.breadth_first import BreadthFirstTraversal
from apiro.config import EVAL_EXCLUDE_SEED_HITS, EVAL_AUC_TIEBREAKER_MARGIN

logger = logging.getLogger(__name__)


# ── Metric helpers ─────────────────────────────────────────────────────────────

def _contains_diagnosis(graph: BeliefGraph, ground_truth: str) -> tuple[bool, int]:
    """
    Check if any node claim contains the ground_truth diagnosis, using robust
    phrase matching (splitting on parentheses/conjunctions and stripping qualifiers).

    When EVAL_EXCLUDE_SEED_HITS=True (config default), seed nodes (depth==0) are
    excluded from the search. This prevents trivially satisfying the diagnostic-hit
    criterion when the ground truth is explicitly stated in the input findings.

    Returns (hit: bool, step: int) — step is the node's index in expansion order
    (0-indexed, counting from the first generated node), or -1 if not found.
    """
    import re
    gt = ground_truth.lower()

    # Extract sub-phrases/acronyms by splitting on parentheticals and key conjunctions
    delimiters = r"\s+due\s+to\s+|\s+secondary\s+to\s+|\s+associated\s+with\s+|\(|\)|,|\;|\bor\b"
    parts = re.split(delimiters, gt)

    # Common clinical qualifiers that the LLM may omit
    qualifiers = r"\b(wild-type|acute|chronic|primary|secondary|mild|severe|suspected|probable|likely)\b"

    match_targets = []
    for p in parts:
        p_clean = p.strip()
        p_clean = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", p_clean)
        if len(p_clean) >= 3:
            if p_clean not in match_targets:
                match_targets.append(p_clean)

            # Add version without qualifiers
            p_no_qual = re.sub(qualifiers, "", p_clean).strip()
            p_no_qual = re.sub(r"\s+", " ", p_no_qual)
            p_no_qual = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", p_no_qual)
            if len(p_no_qual) >= 3 and p_no_qual not in match_targets:
                match_targets.append(p_no_qual)

    # Also add the full cleaned string without qualifiers
    gt_clean = re.sub(r"\s*\([^)]*\)", "", gt).strip()
    gt_clean = re.sub(qualifiers, "", gt_clean).strip()
    gt_clean = re.sub(r"\s+", " ", gt_clean)
    gt_clean = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", gt_clean)
    if len(gt_clean) >= 3 and gt_clean not in match_targets:
        match_targets.append(gt_clean)

    # If no target extracted, fallback to original ground_truth
    if not match_targets:
        match_targets = [gt]

    # Iterate only over generated nodes (depth > 0) if EVAL_EXCLUDE_SEED_HITS is set
    candidate_nodes = [
        n for n in graph.nodes.values()
        if not (EVAL_EXCLUDE_SEED_HITS and n.depth == 0)
    ]

    for i, node in enumerate(candidate_nodes):
        claim_lower = node.claim.lower()
        if any(target in claim_lower for target in match_targets):
            return True, i

    return False, -1




def _entropy_auc(graph: BeliefGraph) -> float:
    """
    Compute the area under the entropy curve (trapezoidal rule).
    Lower AUC = entropy declined faster = better convergence.
    """
    entropies = graph.get_recent_entropies(window=len(graph.nodes))
    if len(entropies) < 2:
        return float(entropies[0]) if entropies else 0.0
    xs = list(range(len(entropies)))
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(entropies, xs))
    else:
        try:
            return float(np.trapz(entropies, xs))
        except AttributeError:
            # manual trapezoidal rule fallback for compatibility
            y = np.array(entropies)
            return float(np.sum(y[1:] + y[:-1]) / 2.0)



# ── CaseEvaluator ─────────────────────────────────────────────────────────────

class CaseEvaluator:
    """
    Runs entropy-first and breadth-first traversal on each case and computes
    comparative metrics.

    Args:
        expander:      NodeExpander shared by both traversals.
        saturation:    SaturationDetector (same for both).
        rabbit_hole:   RabbitHoleDetector (same for both).
        contradiction: ContradictionDetector (same for both).
        max_depth:     Max traversal depth (same for both).
        max_nodes:     Hard node cap (same for both).
    """

    def __init__(
        self,
        expander,
        saturation,
        rabbit_hole,
        contradiction,
        max_depth: int = 5,
        max_nodes: int = 30,
    ):
        self.expander      = expander
        self.saturation    = saturation
        self.rabbit_hole   = rabbit_hole
        self.contradiction = contradiction
        self.max_depth     = max_depth
        self.max_nodes     = max_nodes

    # ── Single traversal runner ────────────────────────────────────────────

    def _run_entropy_first(self, seed_nodes: list[Node]) -> TraversalResult:
        """Run Apiro's entropy-first traversal and return the TraversalResult."""
        traversal = ApiroTraversal(
            expander=self.expander,
            saturation=self.saturation,
            rabbit_hole=self.rabbit_hole,
            contradiction=self.contradiction,
            log_dir="data",
        )
        graph = BeliefGraph()
        return traversal.run(
            seed_nodes=seed_nodes,
            graph=graph,
            max_depth=self.max_depth,
            case_name="ef_eval",
        )

    def _run_breadth_first(self, seed_nodes: list[Node]) -> TraversalResult:
        """Run breadth-first baseline traversal and return a TraversalResult."""
        traversal = BreadthFirstTraversal(
            expander=self.expander,
            saturation=self.saturation,
            rabbit_hole=self.rabbit_hole,
            contradiction=self.contradiction,
            max_depth=self.max_depth,
            max_nodes=self.max_nodes,
        )
        graph = BeliefGraph()
        return traversal.run(seed_nodes=seed_nodes, graph=graph)

    # ── Single case evaluation ─────────────────────────────────────────────

    def evaluate_case(
        self,
        case: dict,
        result: TraversalResult,
        traversal_type: str,
        ground_truth: str,
    ) -> dict:
        """
        Compute metrics for a single completed traversal.

        Args:
            case:           Case dict with at least {'case_id', 'description'}.
            result:         TraversalResult returned by the traversal.
            traversal_type: 'entropy_first' or 'breadth_first'.
            ground_truth:   Ground truth diagnosis string.

        Returns:
            Metric dict for this case/traversal.
        """
        graph = result.graph
        hit, step = _contains_diagnosis(graph, ground_truth)
        auc       = _entropy_auc(graph)
        trend     = graph.get_entropy_trend(window=min(5, len(graph.nodes)))

        return {
            "case_id":        case.get("case_id", "unknown"),
            "ground_truth":   ground_truth,
            "traversal_type": traversal_type,
            "stop_reason":    result.stop_reason,
            "diagnostic_hit": hit,
            "path_length":    step if hit else -1,
            "entropy_auc":    round(auc, 4),
            "entropy_trend":  round(trend, 5),
            "rabbit_holes":   result.rabbit_hole_count,
            "contradictions": result.contradiction_count,
            "total_nodes":    result.total_nodes,
            "elapsed_s":      result.duration_seconds,
        }

    # ── Head-to-head comparison ────────────────────────────────────────────

    def compare_traversal_orders(
        self,
        case: dict,
        seed_nodes: list[Node],
        ground_truth: str,
    ) -> dict:
        """
        Run both traversal strategies on the same case and compare.

        Returns:
            Comparison dict with both metric sets and a winner declaration.
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"  Evaluating case: {case.get('case_id', '?')} — {case.get('description', '')}")
        logger.info(f"  Ground truth: {ground_truth}")
        logger.info(f"{'='*60}")

        # Entropy-first
        logger.info("  [1/2] Entropy-first traversal...")
        t0 = time.time()
        ef_result  = self._run_entropy_first(seed_nodes)
        ef_metrics = self.evaluate_case(case, ef_result, "entropy_first", ground_truth)

        # Breadth-first
        logger.info("  [2/2] Breadth-first traversal...")
        t0 = time.time()
        bf_result  = self._run_breadth_first(seed_nodes)
        bf_metrics = self.evaluate_case(case, bf_result, "breadth_first", ground_truth)

        # Determine winner
        winner = _determine_winner(ef_metrics, bf_metrics)

        logger.info(
            f"  Result: EF path={ef_metrics['path_length']} | "
            f"BF path={bf_metrics['path_length']} | Winner={winner}"
        )

        return {
            "case_id":      case.get("case_id", "unknown"),
            "ground_truth": ground_truth,
            "entropy_first": ef_metrics,
            "breadth_first": bf_metrics,
            "winner":        winner,
            "ef_elapsed_s":  ef_result.duration_seconds,
            "bf_elapsed_s":  bf_result.duration_seconds,
        }

    # ── Full evaluation run ────────────────────────────────────────────────

    def evaluate_all(
        self,
        cases: list[dict],
        output_path: Optional[str | Path] = None,
    ) -> dict:
        """
        Run compare_traversal_orders() on all cases, aggregate results,
        and write a summary JSON.

        Each case dict must have:
            case_id:      str
            description:  str
            seed_nodes:   list[Node]  (from mimic_adapter.findings_to_seed_nodes)
            ground_truth: str         (ICD diagnosis keyword)

        Returns:
            Summary dict with per-case results + aggregate metrics.
        """
        per_case_results = []
        ef_wins   = 0
        bf_wins   = 0
        ties      = 0
        both_miss = 0

        for i, case in enumerate(cases):
            logger.info(f"\n[CaseEvaluator] Case {i+1}/{len(cases)}: {case.get('case_id')}")
            try:
                result = self.compare_traversal_orders(
                    case=case,
                    seed_nodes=case["seed_nodes"],
                    ground_truth=case["ground_truth"],
                )
                per_case_results.append(result)

                w = result["winner"]
                if w == "entropy_first": ef_wins += 1
                elif w == "breadth_first": bf_wins += 1
                elif w == "tie":          ties += 1
                else:                     both_miss += 1

            except Exception as e:
                logger.error(f"[CaseEvaluator] Case {case.get('case_id')} failed: {e}")
                per_case_results.append({
                    "case_id": case.get("case_id"),
                    "error":   str(e),
                    "winner":  "error",
                })
                both_miss += 1

        n = len(cases)
        summary = {
            "total_cases":         n,
            "entropy_first_wins":  ef_wins,
            "breadth_first_wins":  bf_wins,
            "ties":                ties,
            "both_miss":           both_miss,
            "ef_win_rate":         round(ef_wins / n, 3) if n else 0,
            "target_met":          ef_wins >= int(0.7 * n),   # ≥7/10 per plan
            "per_case":            per_case_results,
        }

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(summary, indent=2))
            logger.info(f"[CaseEvaluator] Results written to {out}")

        _print_summary(summary)
        return summary


# ── Helper functions ───────────────────────────────────────────────────────────

def _determine_winner(ef: dict, bf: dict) -> str:
    """
    Determine the traversal winner for a single case.

    Rules (in priority order):
      1. If one hit and the other didn't → the hit wins.
      2. If both hit → shorter path_length wins.
      3. If path_length is equal → use entropy_auc as secondary tie-breaker.
         EF wins if its AUC is ≥ EVAL_AUC_TIEBREAKER_MARGIN lower than BF's
         (lower AUC = entropy declined faster = better convergence).
      4. Otherwise: "tie".
      5. If neither hit → "both_miss".
    """
    ef_hit = ef["diagnostic_hit"]
    bf_hit = bf["diagnostic_hit"]

    if ef_hit and not bf_hit:
        return "entropy_first"
    if bf_hit and not ef_hit:
        return "breadth_first"
    if not ef_hit and not bf_hit:
        return "both_miss"

    # Both hit — compare path lengths (lower = better)
    ef_path = ef["path_length"]
    bf_path = bf["path_length"]

    if ef_path < bf_path:
        return "entropy_first"
    if bf_path < ef_path:
        return "breadth_first"

    # Tied path length — use entropy_auc as secondary signal.
    # EF wins if its AUC is at least EVAL_AUC_TIEBREAKER_MARGIN fraction lower
    # (meaning entropy converged measurably faster, validating the core claim).
    ef_auc = ef["entropy_auc"]
    bf_auc = bf["entropy_auc"]
    if bf_auc > 0 and ef_auc < bf_auc * (1.0 - EVAL_AUC_TIEBREAKER_MARGIN):
        return "entropy_first"
    if ef_auc > 0 and bf_auc < ef_auc * (1.0 - EVAL_AUC_TIEBREAKER_MARGIN):
        return "breadth_first"

    return "tie"


def _print_summary(summary: dict) -> None:
    """Print a human-readable evaluation summary to the log."""
    logger.info("\n" + "="*60)
    logger.info("  APIRO PHASE 3 EVALUATION SUMMARY")
    logger.info("="*60)
    logger.info(f"  Total cases:         {summary['total_cases']}")
    logger.info(f"  Entropy-first wins:  {summary['entropy_first_wins']}")
    logger.info(f"  Breadth-first wins:  {summary['breadth_first_wins']}")
    logger.info(f"  Ties:                {summary['ties']}")
    logger.info(f"  Both miss:           {summary['both_miss']}")
    logger.info(f"  EF win rate:         {summary['ef_win_rate']:.1%}")
    target = "✅ PASS" if summary["target_met"] else "❌ FAIL (need ≥70%)"
    logger.info(f"  Phase 3 target:      {target}")
    logger.info("="*60)
