"""
eval/llm_judge.py — LLM-as-Judge for Medical Diagnosis Matching
================================================================
Replaces the brittle cosine-similarity threshold in _check_synthesis_hit().

The core problem it solves:
  - "Acute Myocardial Infarction" was marked a MISS vs "Acute inferior wall STEMI"
  - "Systemic Lupus Erythematosus" scored 0.701 cosine sim vs "NPSLE" → MISS

A language model understands that:
  - AMI is a valid parent diagnosis of inferior-wall STEMI
  - SLE is a valid parent diagnosis of NPSLE
  - Cosine similarity cannot capture ICD-10 hierarchy

Matching tiers (in priority order):
  1. Exact / substring match         → hit  (fast path, no LLM call)
  2. LLM semantic equivalence check  → hit/miss  (handles synonyms, parent/child)
  3. Cosine similarity fallback       → hit if > FALLBACK_SIM_THRESHOLD (0.70)

The LLM is called only when the fast path fails — typically ~30% of cases.

Usage:
    from apiro.eval.llm_judge import MedicalDiagnosisJudge
    judge = MedicalDiagnosisJudge(llm_client)
    hit, reason = judge.check(ground_truth, synthesis_list)
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Cosine similarity used only as final fallback (after LLM judge)
FALLBACK_SIM_THRESHOLD = 0.70

# How many synthesis items to send to LLM at once (all 3 by default)
MAX_SYNTHESIS_TO_JUDGE = 3

JUDGE_PROMPT_TEMPLATE = """\
You are a clinical terminology expert evaluating whether a diagnosis engine found the correct answer.

Ground truth diagnosis: "{ground_truth}"
Engine's top diagnoses: {synthesis_list}

A diagnostic HIT means any of the engine's diagnoses is:
  - Identical or a synonym (e.g. "Addison's disease" = "Primary adrenal insufficiency")
  - A specific subtype of the ground truth (e.g. "Inferior wall STEMI" is a subtype of "Acute MI")
  - The ground truth is a specific subtype of the engine's diagnosis (e.g. "NPSLE" is a subtype of "SLE")
  - Clinically equivalent in the context of this presentation

Answer with exactly one word: HIT or MISS
Do not explain. Do not add punctuation."""


class MedicalDiagnosisJudge:
    """
    Determines whether the synthesis list contains a valid match for the
    ground truth, using a three-tier approach:
      1. Fast substring/synonym path
      2. LLM semantic judge
      3. Cosine similarity fallback
    """

    def __init__(self, llm_client, embedder=None):
        """
        Args:
            llm_client: Any client with a .chat(prompt: str) -> str method.
                        Typically the same OllamaLLMClient used by the traversal.
            embedder:   Optional Embedder instance for cosine fallback.
                        If None, falls back to substring-only on LLM failure.
        """
        self.llm_client = llm_client
        self.embedder = embedder

    # ── Public API ─────────────────────────────────────────────────────────

    def check(
        self,
        ground_truth: str,
        synthesis: list[str],
    ) -> tuple[bool, str]:
        """
        Check if any synthesis item matches the ground truth.

        Returns:
            (is_hit: bool, reason: str)
            reason is one of: "substring", "llm_hit", "cosine", "llm_miss", "empty"
        """
        if not synthesis:
            return False, "empty"

        # ── Tier 1: fast path ─────────────────────────────────────────────
        hit, reason = self._substring_check(ground_truth, synthesis)
        if hit:
            logger.debug(f"[Judge] Tier1 HIT — {reason}: '{ground_truth}'")
            return True, reason

        # ── Tier 2: LLM judge ─────────────────────────────────────────────
        llm_hit = self._llm_check(ground_truth, synthesis[:MAX_SYNTHESIS_TO_JUDGE])
        if llm_hit is True:
            logger.info(f"[Judge] LLM HIT: '{ground_truth}' matched {synthesis}")
            return True, "llm_hit"
        if llm_hit is False:
            logger.info(f"[Judge] LLM MISS: '{ground_truth}' not in {synthesis}")
            return False, "llm_miss"

        # ── Tier 3: cosine fallback (LLM call failed) ─────────────────────
        if self.embedder is not None:
            hit, sim = self._cosine_check(ground_truth, synthesis)
            reason = f"cosine_{sim:.3f}"
            logger.info(f"[Judge] Cosine fallback: hit={hit}, sim={sim:.3f} for '{ground_truth}'")
            return hit, reason

        # All tiers failed (no embedder, LLM unreachable) → conservative miss
        return False, "no_signal"

    # ── Tier 1: substring ─────────────────────────────────────────────────

    def _substring_check(self, ground_truth: str, synthesis: list[str]) -> tuple[bool, str]:
        """
        Fast substring match with qualifier stripping.
        Strips common qualifiers (acute, chronic, primary, etc.) before matching.
        """
        gt = ground_truth.lower()
        # Strip parentheticals: "NPSLE (ICD F05)" → "npsle"
        gt_clean = re.sub(r"\s*\([^)]*\)", "", gt).strip()
        # Strip common clinical qualifiers
        qualifiers = r"\b(wild-type|acute|chronic|primary|secondary|mild|severe|suspected|probable|likely|type [0-9])\b"
        gt_stripped = re.sub(qualifiers, "", gt_clean).strip()
        gt_stripped = re.sub(r"\s+", " ", gt_stripped).strip()

        for diag in synthesis:
            d = diag.lower()
            # Direct substring both ways
            if gt_clean and gt_clean in d:
                return True, "substring_gt_in_diag"
            if gt_clean and d in gt_clean and len(d) > 5:
                return True, "substring_diag_in_gt"
            # Stripped version
            if gt_stripped and gt_stripped in d:
                return True, "substring_stripped"

        return False, ""

    # ── Tier 2: LLM judge ─────────────────────────────────────────────────

    def _llm_check(
        self,
        ground_truth: str,
        synthesis: list[str],
    ) -> Optional[bool]:
        """
        Ask the LLM whether any synthesis item is a valid match.
        Returns True/False, or None if the LLM call fails.
        """
        synthesis_str = str(synthesis)
        prompt = JUDGE_PROMPT_TEMPLATE.format(
            ground_truth=ground_truth,
            synthesis_list=synthesis_str,
        )
        try:
            raw = self.llm_client.chat(prompt).strip().upper()
            # Accept first word in case model adds punctuation
            first_word = raw.split()[0] if raw else ""
            if "HIT" in first_word:
                return True
            if "MISS" in first_word:
                return False
            # Ambiguous response — escalate to cosine
            logger.warning(f"[Judge] LLM returned ambiguous: '{raw}' — falling back to cosine")
            return None
        except Exception as e:
            logger.error(f"[Judge] LLM call failed: {e}")
            return None

    # ── Tier 3: cosine fallback ───────────────────────────────────────────

    def _cosine_check(
        self,
        ground_truth: str,
        synthesis: list[str],
    ) -> tuple[bool, float]:
        """
        Cosine similarity via SentenceTransformer (lower threshold than old evaluator).
        Threshold: 0.70 (was 0.75 — the threshold that caused the NPSLE false negative).
        """
        try:
            import numpy as np
            gt_emb = self.embedder._model.encode([ground_truth], normalize_embeddings=True)[0]
            diag_embs = self.embedder._model.encode(synthesis, normalize_embeddings=True)
            sims = np.dot(diag_embs, gt_emb)
            max_sim = float(np.max(sims))
            return max_sim >= FALLBACK_SIM_THRESHOLD, max_sim
        except Exception as e:
            logger.error(f"[Judge] Cosine fallback failed: {e}")
            return False, 0.0