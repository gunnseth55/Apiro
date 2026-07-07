"""
apiro/hypothesis/bayesian_scorer.py — BayesianScorer
======================================================

Applies hard demographic constraint rules and ranks hypotheses by final score.

WHY THIS EXISTS:
  EvidenceMatcher produces raw evidence match scores. But clinical reasoning
  also incorporates hard logical impossibilities (e.g., ovarian cancer in a male
  patient) and prior probability adjustments (e.g., a known background condition
  should not be the acute diagnosis). The BayesianScorer encodes these as
  deterministic rules — no LLM needed.

DESIGN:
  - Hard constraints: any rule violation zeros the score instantly.
  - Background suppression: if a hypothesis appears in context.history,
    it is treated as a chronic background condition and downranked heavily.
  - Final ranked list: sorted by final_score descending.

  This is NOT full Bayesian inference (we don't have true priors). It is a
  rule-weighted scoring layer on top of EvidenceMatcher's evidence scores.
  The name reflects the design intent: the system is structured to accept
  true prior probability tables in the future.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from apiro.hypothesis.evidence_matcher import HypothesisScore
from apiro.patient.context import PatientContext

logger = logging.getLogger(__name__)


@dataclass
class RankedHypothesis:
    """
    A hypothesis with its final score after all rules and constraints applied.

    Attributes:
        hypothesis:      Disease name.
        raw_score:       Evidence match score from EvidenceMatcher (0-1).
        final_score:     Score after constraint rules applied (0-1).
        matched_findings: Findings from patient that matched evidence.
        rank:            1-indexed rank (1 = most likely).
        rule_notes:      Human-readable notes about applied rules.
    """
    hypothesis: str
    raw_score: float
    final_score: float
    matched_findings: list[str]
    rank: int
    rule_notes: list[str]

    def __repr__(self) -> str:
        return (
            f"[#{self.rank}] {self.hypothesis!r} "
            f"(raw={self.raw_score:.3f}, final={self.final_score:.3f})"
        )


# ── Hard constraint rule definitions ─────────────────────────────────────────
# Each rule: (description, condition_fn) → bool. If True, score = 0.0.

def _is_male(ctx: PatientContext) -> bool:
    return ctx.gender == "M"

def _is_female(ctx: PatientContext) -> bool:
    return ctx.gender == "F"

def _age_under(n: int):
    def _check(ctx: PatientContext) -> bool:
        return ctx.age is not None and ctx.age < n
    return _check

def _age_over(n: int):
    def _check(ctx: PatientContext) -> bool:
        return ctx.age is not None and ctx.age > n
    return _check


# (regex pattern for hypothesis name, constraint fn, note)
_HARD_CONSTRAINTS: list[tuple[re.Pattern, callable, str]] = [
    # Male anatomy
    (re.compile(r"ovarian|uterine|cervical|endometrial|vulvar", re.I),
     _is_male,
     "Impossible in male patient"),
    # Female anatomy
    (re.compile(r"testicular|prostate|penile", re.I),
     _is_female,
     "Impossible in female patient"),
    # Paediatric-only conditions — unlikely in adults
    (re.compile(r"kawasaki|intussusception|pyloric stenosis|wilms", re.I),
     _age_over(18),
     "Paediatric condition — patient is adult"),
    # Geriatric-only patterns — unlikely under 30
    (re.compile(r"alzheimer|senile", re.I),
     _age_under(50),
     "Condition extremely rare under age 50"),
]

# Downrank multiplier for a hypothesis that appears in background history
_HISTORY_BACKGROUND_MULTIPLIER = 0.15


class BayesianScorer:
    """
    Applies hard demographic constraints and background suppression to rank
    hypotheses by final score.

    Args:
        history_suppression: multiplier applied when hypothesis matches history
                             (default 0.15 — strongly downranks, but doesn't zero).
    """

    def __init__(self, history_suppression: float = _HISTORY_BACKGROUND_MULTIPLIER):
        self.history_suppression = history_suppression

    def rank(
        self,
        scores: list[HypothesisScore],
        context: PatientContext,
    ) -> list[RankedHypothesis]:
        """
        Apply constraints and return hypotheses ranked by final score.

        Args:
            scores:  List of HypothesisScore from EvidenceMatcher (any order).
            context: PatientContext for constraint evaluation.

        Returns:
            List of RankedHypothesis sorted by final_score descending, 1-indexed.
        """
        ranked: list[RankedHypothesis] = []

        for score in scores:
            final_score, notes = self._apply_rules(score, context)
            ranked.append(RankedHypothesis(
                hypothesis=score.hypothesis,
                raw_score=score.raw_score,
                final_score=final_score,
                matched_findings=score.matched_findings,
                rank=0,   # assigned below
                rule_notes=notes,
            ))

        # Sort descending by final_score, then by number of matched findings as tiebreak
        ranked.sort(
            key=lambda r: (r.final_score, len(r.matched_findings)),
            reverse=True,
        )

        # Assign ranks
        for i, r in enumerate(ranked):
            r.rank = i + 1

        if ranked:
            logger.info(
                f"[BayesianScorer] Ranked {len(ranked)} hypotheses. "
                f"Top 3: {[r.hypothesis for r in ranked[:3]]}"
            )

        return ranked

    # ── Rule engine ───────────────────────────────────────────────────────────

    def _apply_rules(
        self,
        score: HypothesisScore,
        context: PatientContext,
    ) -> tuple[float, list[str]]:
        """
        Returns (final_score, list_of_rule_notes).
        Hard constraint violations zero the score immediately.
        """
        notes: list[str] = []
        final = score.raw_score

        # ── Hard demographic constraints ──────────────────────────────────────
        for pattern, condition_fn, note in _HARD_CONSTRAINTS:
            if pattern.search(score.hypothesis) and condition_fn(context):
                logger.debug(
                    f"[BayesianScorer] HARD CONSTRAINT: '{score.hypothesis}' → {note}"
                )
                notes.append(f"ZEROED: {note}")
                return 0.0, notes

        # ── Background history suppression ────────────────────────────────────
        if self._is_in_history(score.hypothesis, context):
            final *= self.history_suppression
            note = f"Background condition (history match) → ×{self.history_suppression}"
            notes.append(note)
            logger.debug(f"[BayesianScorer] HISTORY SUPPRESSED: '{score.hypothesis}'")

        return round(final, 4), notes

    @staticmethod
    def _is_in_history(hypothesis: str, context: PatientContext) -> bool:
        """
        Check if the hypothesis name meaningfully overlaps with known history.
        Uses word-overlap: if 2+ significant words from the hypothesis appear
        in any history entry, treat it as a background condition.
        """
        if not context.history:
            return False

        _STOPWORDS = {"disease", "syndrome", "disorder", "condition", "chronic",
                      "known", "history", "a", "an", "the", "of", "with", "and"}

        hyp_words = {
            w.lower() for w in re.findall(r"\b[a-z]{3,}\b", hypothesis.lower())
            if w.lower() not in _STOPWORDS
        }

        for h in context.history:
            hist_words = {
                w.lower() for w in re.findall(r"\b[a-z]{3,}\b", h.lower())
                if w.lower() not in _STOPWORDS
            }
            if len(hyp_words & hist_words) >= 2:
                return True
        return False
