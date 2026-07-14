"""
apiro/edar/discriminator.py
=============================
Phase 4: Discriminative Evidence Seeking — "The Detective Move."

After the Bayesian update, the top 2 candidates may be close. A real
detective doesn't stop there. They ask: "What one finding would prove
it's Disease A and NOT Disease B?"

This module:
  1. Computes the set of findings that appears in Disease A's expected
     profile but NOT in Disease B's (and vice versa).
  2. Queries the corpus for that discriminating finding in the context
     of both diseases.
  3. Checks whether the patient's presentation contains that finding.
  4. Applies a final evidence boost or penalty based on the result.

Zero LLM calls. Pure set algebra + cosine similarity.
"""

from __future__ import annotations

import logging

import numpy as np

from apiro.edar.evidence_graph import EvidenceNode
from apiro.patient.context import PatientContext

logger = logging.getLogger(__name__)

_DISCRIMINATE_CONFIRM_THRESHOLD = 0.48


class Discriminator:
    """
    Finds the key differentiating finding between the top 2 candidates
    and applies a final Bayesian update based on whether the patient
    has that finding.

    Args:
        embedder: Apiro Embedder instance.
        boost:    Posterior multiplier applied to the winner when discriminated.
    """

    def __init__(self, embedder, boost: float = 2.0):
        self.embedder = embedder
        self.boost = boost

    def discriminate(
        self,
        ranked: list[tuple[str, float, EvidenceNode]],
        context: PatientContext,
    ) -> list[tuple[str, float, EvidenceNode]]:
        """
        Apply discriminative evidence seeking between the top 2 candidates.

        If the top 2 candidates are within 20% posterior probability of each
        other, we search for a discriminating finding and apply a final update.

        Args:
            ranked:  Sorted (disease, posterior, node) list from BayesianBeliefUpdater.
            context: Patient context.

        Returns:
            Re-sorted ranked list after discriminative update.
        """
        if len(ranked) < 2:
            return ranked

        top1_name, top1_post, top1_node = ranked[0]
        top2_name, top2_post, top2_node = ranked[1]

        # Only discriminate if they're genuinely close
        if top1_post == 0 or (top1_post - top2_post) / top1_post > 0.30:
            logger.info(
                f"[Discriminator] Candidates not close enough — skipping. "
                f"Top1={top1_post:.4f}, Top2={top2_post:.4f}"
            )
            return ranked

        logger.info(
            f"[Discriminator] Close candidates! '{top1_name}' ({top1_post:.4f}) vs "
            f"'{top2_name}' ({top2_post:.4f}). Seeking discriminating evidence..."
        )

        # Find findings unique to top1 (not in top2's expected)
        top1_expected_lower = {f.lower()[:50] for f in top1_node.expected_findings}
        top2_expected_lower = {f.lower()[:50] for f in top2_node.expected_findings}

        unique_to_top1 = [
            f for f in top1_node.expected_findings
            if f.lower()[:50] not in top2_expected_lower
        ]
        unique_to_top2 = [
            f for f in top2_node.expected_findings
            if f.lower()[:50] not in top1_expected_lower
        ]

        if not unique_to_top1 and not unique_to_top2:
            logger.info("[Discriminator] No unique discriminating findings found.")
            return ranked

        # Collect patient findings for comparison
        patient_findings = [context.chief_complaint] + context.symptoms
        for k, v in context.labs.items():
            patient_findings.append(f"{k}: {v}")
        patient_findings = [f for f in patient_findings if f]

        if not patient_findings:
            return ranked

        try:
            model = self.embedder._model
            patient_embs = model.encode(
                patient_findings, normalize_embeddings=True, show_progress_bar=False
            )
        except Exception as e:
            logger.warning(f"[Discriminator] Embedding failed: {e}")
            return ranked

        def check_present(findings: list[str]) -> bool:
            if not findings:
                return False
            try:
                finding_embs = model.encode(
                    findings[:5], normalize_embeddings=True, show_progress_bar=False
                )
                sims = np.dot(finding_embs, patient_embs.T)
                return float(np.max(sims)) >= _DISCRIMINATE_CONFIRM_THRESHOLD
            except Exception:
                return False

        top1_discriminator_present = check_present(unique_to_top1)
        top2_discriminator_present = check_present(unique_to_top2)

        # Apply discriminative update
        new_top1 = top1_post
        new_top2 = top2_post

        if top1_discriminator_present and not top2_discriminator_present:
            new_top1 *= self.boost
            logger.info(
                f"[Discriminator] ✅ '{top1_name}' discriminator confirmed → boosted to {new_top1:.4f}"
            )
        elif top2_discriminator_present and not top1_discriminator_present:
            new_top2 *= self.boost
            logger.info(
                f"[Discriminator] ✅ '{top2_name}' discriminator confirmed → boosted to {new_top2:.4f}"
            )
        else:
            logger.info("[Discriminator] Both or neither confirmed — no update applied.")
            return ranked

        # Update posteriors in nodes
        top1_node.posterior = new_top1
        top2_node.posterior = new_top2

        # Re-sort
        result = list(ranked)
        result[0] = (top1_name, new_top1, top1_node)
        result[1] = (top2_name, new_top2, top2_node)
        result.sort(key=lambda x: -x[1])

        logger.info(
            f"[Discriminator] Post-discrimination top: '{result[0][0]}' ({result[0][1]:.4f})"
        )
        return result
