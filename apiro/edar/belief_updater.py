"""
apiro/edar/belief_updater.py
=============================
Phase 3: Iterative Bayesian Belief Revision.

This is the core "thinking" of the EDAR engine. Unlike the HT engine's
cosine similarity ranking, this module performs genuine probabilistic
reasoning: each piece of evidence from the patient's presentation updates
the posterior probability of each candidate disease via Bayes' rule.

Algorithm:
  - Start with uniform prior P(Disease_i) = 1/N for all N candidates.
  - For each candidate disease, compute confirmation/absence/contradiction
    RATES (not raw counts) relative to its expected finding count.
  - Apply rate-based Bayesian updates scaled by sqrt(n_expected):
      * High confirmation rate → multiply P(D) by BOOST_FACTOR^(rate × scale)
      * High absence rate     → multiply P(D) by ABSENT_PENALTY^(rate × scale)
      * Any contradiction     → multiply P(D) by CONTRADICT_PENALTY^(rate × scale)
  - Normalise all posteriors to sum to 1.0 after all updates.
  - Apply a demographic prior: age/gender-based prevalence correction.

WHY RATE-BASED RATHER THAN COUNT-BASED:
  The original count-based approach applied absent_penalty once per absent
  finding. This created a structural bias: well-documented diseases (e.g. TB,
  Harrison's chapter = 20 extracted findings) received exponentially larger
  penalties than poorly-documented diseases (e.g. Folliculitis = 4 findings),
  even when their confirmation *rates* were comparable.

  The rate × sqrt(n_expected) formulation fixes this:
    - "Rate" normalises so 15/20 absent gets the same base penalty as 3/4 absent.
    - "sqrt(n_expected)" means more expected findings still adds *some* weight
      (stronger evidence when confirmed), but grows sub-linearly rather than
      linearly, preventing count inflation from dominating.

Zero LLM calls.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from apiro.edar.evidence_graph import EvidenceNode
from apiro.patient.context import PatientContext

logger = logging.getLogger(__name__)

# ── Belief update factors ──────────────────────────────────────────────────────
# Interpretable as per-unit likelihood ratios applied at the *rate* level:
_CONFIRM_BOOST      = 1.60   # confirmed-rate boost   (was 1.40 — stronger reward for matches)
_ABSENT_PENALTY     = 0.85   # absent-rate penalty     (was 0.82 — slightly softer per unit)
_CONTRADICT_PENALTY = 0.15   # contradiction penalty   (kept strong — direct contradictions hurt)

# Minimum effective n_expected for sqrt scaling.
# Ensures diseases with only 1-3 extracted findings still get a minimum scale
# so we don't treat them as having essentially no evidence at all.
_MIN_EFFECTIVE_N = 4

# Minimum posterior to prevent numerical underflow
_MIN_POSTERIOR = 1e-9


class BayesianBeliefUpdater:
    """
    Applies rate-normalised Bayesian evidence updates to a set of EvidenceNodes,
    producing final posterior probabilities for each candidate disease.

    The update is fully transparent: each step logs why a disease's
    probability rose or fell. This is the "reasoning trace" of EDAR.

    Args:
        confirm_boost:      Likelihood multiplier for a confirmed finding.
        absent_penalty:     Likelihood multiplier for an absent finding.
        contradict_penalty: Likelihood multiplier for a contradicted finding.
        age_prior:          Whether to apply age-based prevalence correction.
    """

    def __init__(
        self,
        confirm_boost:      float = _CONFIRM_BOOST,
        absent_penalty:     float = _ABSENT_PENALTY,
        contradict_penalty: float = _CONTRADICT_PENALTY,
        age_prior:          bool = True,
    ):
        self.confirm_boost      = confirm_boost
        self.absent_penalty     = absent_penalty
        self.contradict_penalty = contradict_penalty
        self.age_prior          = age_prior

    def _compute_age_prior(self, disease: str, context: PatientContext) -> float:
        """
        Simple age-based prevalence correction.
        Penalises paediatric diseases in adults and vice versa.
        Returns a multiplier [0.1, 1.0].
        """
        if not context.age or not self.age_prior:
            return 1.0

        try:
            age = int(str(context.age).split()[0])
        except (ValueError, IndexError):
            return 1.0

        disease_lower = disease.lower()

        paediatric_terms = [
            "childhood", "paediatric", "pediatric", "juvenile", "neonatal",
            "infant", "congenital", "kawasaki", "wilms", "neuroblastoma",
            "dravet", "duchenne", "legg-calve", "osteosarcoma",
        ]
        if age > 18 and any(t in disease_lower for t in paediatric_terms):
            return 0.25

        adult_terms = [
            "alzheimer", "atherosclerosis", "coronary artery disease", "copd",
            "type 2 diabetes", "benign prostatic", "osteoporosis", "gout",
        ]
        if age < 15 and any(t in disease_lower for t in adult_terms):
            return 0.30

        return 1.0

    def _rate_based_log_update(self, node: EvidenceNode) -> float:
        """
        Compute the log-probability update for one disease node using
        rate-normalised Bayesian revision.

        The key formula:
            delta_log_p = (confirm_rate × scale × log(boost))
                        + (absent_rate  × scale × log(penalty))
                        + (contradict_rate × scale × log(contradict_penalty))

        where scale = sqrt(max(n_expected, _MIN_EFFECTIVE_N))

        This ensures:
          1. The update magnitude grows with evidence quantity (more expected
             findings = stronger signal when they're confirmed).
          2. The update doesn't scale *linearly* with n_expected, preventing
             count-inflation bias for well-documented diseases.
          3. Confirmation and absence are always evaluated relative to each
             other (rates), not as independent absolute counts.

        Returns:
            delta_log_p: the log-space update to add to log(prior).
        """
        n_expected = len(node.expected_findings)
        if n_expected == 0:
            return 0.0  # No information — stay at prior

        n_confirmed    = len(node.confirmed)
        n_absent       = len(node.absent)
        n_contradicted = len(node.contradicted)

        # Rates (all in [0, 1], sum ≤ 1.0)
        confirm_rate    = n_confirmed    / n_expected
        absent_rate     = n_absent       / n_expected
        contradict_rate = n_contradicted / n_expected

        # Sub-linear scaling: sqrt(n_expected), floored to avoid tiny scales
        # for diseases with very few extracted findings
        scale = math.sqrt(max(n_expected, _MIN_EFFECTIVE_N))

        delta = 0.0
        delta += confirm_rate    * scale * math.log(self.confirm_boost)
        delta += absent_rate     * scale * math.log(self.absent_penalty)
        delta += contradict_rate * scale * math.log(self.contradict_penalty)

        # Extra mild penalty for zero confirmations: a disease the patient
        # matches on literally none of its expected findings is suspicious,
        # even after the rate-based absent penalty above.
        if n_confirmed == 0 and n_expected > 0:
            delta += math.log(0.70)  # ×0.70 extra (was ×0.50 — softened)

        logger.debug(
            f"  [{node.disease[:35]:<35}] "
            f"rate={confirm_rate:.0%}✅ {absent_rate:.0%}❌ {contradict_rate:.0%}⚡  "
            f"scale={scale:.2f}  delta={delta:+.3f}"
        )

        return delta

    def update(
        self,
        evidence_graph: dict[str, EvidenceNode],
        context: Optional[PatientContext] = None,
    ) -> list[tuple[str, float, EvidenceNode]]:
        """
        Apply rate-normalised Bayesian evidence updates to all disease candidates.

        Args:
            evidence_graph: Dict of disease_name → EvidenceNode
            context:        PatientContext for demographic priors

        Returns:
            Sorted list of (disease_name, posterior, EvidenceNode), highest first.
        """
        diseases = list(evidence_graph.keys())
        n = len(diseases)
        if n == 0:
            return []

        # ── Uniform prior ────────────────────────────────────────────────────
        posteriors: dict[str, float] = {d: 1.0 / n for d in diseases}

        logger.info(
            f"[BayesianBeliefUpdater] Updating {n} candidates "
            f"(rate-normalised, scale=sqrt(n_expected))..."
        )

        # ── Rate-normalised Bayesian update ───────────────────────────────────
        for disease, node in evidence_graph.items():
            log_p = math.log(posteriors[disease])

            # Rate-based evidence update (core fix)
            log_p += self._rate_based_log_update(node)

            # Age/demographic prior
            if context is not None:
                age_factor = self._compute_age_prior(disease, context)
                if age_factor != 1.0:
                    log_p += math.log(age_factor)
                    logger.debug(f"  [{disease[:35]:<35}] age_prior={age_factor:.2f}")

            posteriors[disease] = max(math.exp(log_p), _MIN_POSTERIOR)
            node.posterior = posteriors[disease]

        # ── Normalise to sum to 1 ────────────────────────────────────────────
        total = sum(posteriors.values())
        if total > 0:
            for d in posteriors:
                posteriors[d] /= total
                evidence_graph[d].posterior = posteriors[d]

        # ── Sort and return ──────────────────────────────────────────────────
        ranked = sorted(
            [(d, posteriors[d], evidence_graph[d]) for d in diseases],
            key=lambda x: -x[1],
        )

        logger.info(
            f"[BayesianBeliefUpdater] Ranked {len(ranked)} candidates. "
            f"Top 3: {[(r[0][:40], f'{r[1]:.4f}') for r in ranked[:3]]}"
        )

        return ranked
