import logging
import re
import numpy as np

logger = logging.getLogger(__name__)

def _check_synthesis_hit(
    synthesis: list[str],
    ground_truth: str,
    embedder=None,
    llm_client=None,
) -> tuple[bool, str]:
    """
    Check if the ground truth is semantically present in any synthesized diagnosis.

    Returns:
        (hit: bool, match_type: str) where match_type is:
          'exact'  — synonym, exact match, or close similarity
          'broad'  — similarity matching
          'miss'   — no match found
    """
    if not synthesis:
        return False, "miss"

    gt = ground_truth.lower()

    # ─ 1. Substring match ─────────────────────────────────────────────────────
    gt_clean = re.sub(r"\s*\([^)]*\)", "", gt).strip()
    qualifiers = r"\b(wild-type|acute|chronic|primary|secondary|mild|severe|suspected|probable|likely)\b"
    gt_clean = re.sub(qualifiers, "", gt_clean).strip()
    gt_clean = re.sub(r"\s+", " ", gt_clean)
    gt_clean = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", gt_clean)

    for diag in synthesis:
        if gt_clean and gt_clean in diag.lower():
            return True, "exact"

    # ─ 2. LLM-as-a-Judge (primary fallback for synonym/clinical matching) ───
    if llm_client is not None:
        try:
            preds_text = "\n".join(f"  - {d}" for d in synthesis)
            prompt = (
                "You are a medical evaluation assistant.\n"
                "Determine if the predicted diagnoses contain or represent the ground truth diagnosis.\n\n"
                f"Ground Truth: {ground_truth}\n"
                f"Predicted Diagnoses:\n{preds_text}\n\n"
                "Rule: If any predicted diagnosis is an exact match, a clinical synonym, "
                "or a direct manifestation/cause/broader class (e.g. 'Nitrofurantoin-induced hemolytic anemia' matches 'G6PD Deficiency' "
                "in this clinical context, or 'Lupus Cerebritis' is a synonym for 'Neuropsychiatric Systemic Lupus Erythematosus'), "
                "respond with 'YES'. Otherwise respond with 'NO'.\n\n"
                "Response (YES/NO only):"
            )
            response = llm_client.chat(prompt).strip().upper()
            if "YES" in response:
                logger.info(f"[LLM-Judge] Match confirmed for '{ground_truth}' vs {synthesis}")
                return True, "exact"
            else:
                logger.info(f"[LLM-Judge] No match for '{ground_truth}' vs {synthesis} (response: {response})")
        except Exception as e:
            logger.error(f"[LLM-Judge] Failed: {e}")

    # ─ 3. Semantic similarity fallback ────────────────────────────────────────
    if embedder is not None:
        try:
            gt_emb    = embedder._model.encode([ground_truth], normalize_embeddings=True)[0]
            diag_embs = embedder._model.encode(synthesis,     normalize_embeddings=True)
            sims      = np.dot(diag_embs, gt_emb)
            max_sim   = float(np.max(sims))

            if max_sim >= 0.75:
                return True, "exact"
            if max_sim >= 0.60:
                return True, "broad"
        except Exception as e:
            logger.error(f"[_check_synthesis_hit] Semantic similarity failed: {e}")

    return False, "miss"
auc < bf_auc * (1.0 - EVAL_AUC_TIEBREAKER_MARGIN):
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
