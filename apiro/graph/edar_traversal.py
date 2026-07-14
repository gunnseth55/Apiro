"""
apiro/graph/edar_traversal.py
================================
Evidence-Driven Abductive Reasoning (EDAR) Traversal.

The difference from HypothesisTestingTraversal is NOT in how candidates
are generated — both use HypothesisOracle (1 LLM call). The difference
is entirely in how they are scored and ranked:

  HT Engine:
    Oracle → cosine similarity score → rank
    (raw semantic distance, single-pass)

  EDAR Engine:
    Oracle → evidence graph (confirmed / absent / contradicted per finding)
           → iterative Bayesian belief revision (each finding updates posterior)
           → discriminative seeking (targeted corpus query to break ties)

The Bayesian update is genuinely different: a confirmed finding multiplies
the posterior by a boost factor, an absent expected finding applies a mild
penalty, and a contradiction devastates the posterior. This models how a
clinician actually reasons: absence of an expected sign matters, and a
directly contradicted sign is near-disqualifying.

LLM calls: exactly 2 (same as HT):
  1. PatientContext extraction from raw text
  2. HypothesisOracle candidate generation

Everything from Phase 3 onward is pure math and corpus retrieval.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from apiro.config import DATA_DIR
from apiro.edar.belief_updater import BayesianBeliefUpdater
from apiro.edar.discriminator import Discriminator
from apiro.edar.evidence_graph import EvidenceGraphBuilder, EvidenceNode
from apiro.patient.context import PatientContext, extract_patient_context

logger = logging.getLogger(__name__)


@dataclass
class EdarResult:
    """
    Result returned by EdarTraversal.run().
    Compatible with the PMC evaluation harness.
    """
    synthesis:          list[str]                                # top N disease names
    ranked:             list[tuple[str, float, EvidenceNode]]   # (disease, posterior, node)
    patient_context:    PatientContext
    duration_seconds:   float
    stop_reason:        str = "edar_bayesian"
    n_candidates:       int = 0
    ranked_hypotheses:  list = field(default_factory=list)
    total_nodes:        int = 0
    total_edges:        int = 0


class EdarTraversal:
    """
    EDAR: Oracle shortlisting + Bayesian evidence-graph scoring.

    Phases:
      1. extract_patient_context(vignette)      → PatientContext  [1 LLM]
      2. oracle.generate(context)               → 10 candidates   [1 LLM]
      3. graph_builder.build_all(candidates)    → evidence graph  [0 LLM]
      4. belief_updater.update(evidence_graph)  → ranked posteriors [0 LLM]
      5. discriminator.discriminate(ranked)     → final ranking   [0 LLM]

    Args:
        oracle:           HypothesisOracle instance.
        graph_builder:    EvidenceGraphBuilder instance.
        belief_updater:   BayesianBeliefUpdater instance.
        discriminator:    Discriminator instance (optional Phase 5).
        top_k:            Number of diagnoses to return in synthesis.
        use_discriminator: Whether to run Phase 5.
        log_dir:          Directory for JSONL reasoning traces.
    """

    def __init__(
        self,
        oracle,
        graph_builder: EvidenceGraphBuilder,
        belief_updater: BayesianBeliefUpdater,
        discriminator: Optional[Discriminator] = None,
        top_k: int = 3,
        use_discriminator: bool = True,
        log_dir: Path = DATA_DIR,
    ):
        self.oracle = oracle
        self.graph_builder = graph_builder
        self.belief_updater = belief_updater
        self.discriminator = discriminator
        self.top_k = top_k
        self.use_discriminator = use_discriminator
        self.log_dir = log_dir
        self._events: list[dict] = []
        self._cb: Optional[Callable] = None

    def _emit(self, event: dict) -> None:
        self._events.append(event)
        if self._cb:
            try:
                self._cb(event)
            except Exception:
                pass

    def _write_log(self, case_name: str) -> None:
        path = self.log_dir / f"edar_log_{case_name}.jsonl"
        try:
            with open(path, "w", encoding="utf-8") as f:
                for ev in self._events:
                    f.write(json.dumps(ev) + "\n")
            logger.info(f"[EdarTraversal] Log written to {path}")
        except Exception as e:
            logger.warning(f"[EdarTraversal] Failed to write log: {e}")

    def run(
        self,
        vignette: str,
        case_name: str = "edar",
        on_event: Optional[Callable] = None,
        **kwargs,
    ) -> EdarResult:
        """
        Run the full EDAR pipeline from raw vignette to ranked diagnosis.
        """
        self._events = []
        self._cb = on_event
        t0 = time.time()

        # ── Phase 1: Extract PatientContext ───────────────────────────────────
        logger.info("[EdarTraversal] Phase 1: Extracting PatientContext...")
        self._emit({"event": "edar_phase", "phase": 1, "description": "Extracting patient profile..."})
        try:
            context = extract_patient_context(vignette)
        except Exception as e:
            logger.error(f"[EdarTraversal] Context extraction failed: {e}")
            return EdarResult(
                synthesis=[], ranked=[], patient_context=PatientContext(chief_complaint=""),
                duration_seconds=time.time() - t0, stop_reason="extraction_failed",
            )

        self._emit({
            "event": "patient_context_extracted",
            "summary": str(context),
            "chief_complaint": context.chief_complaint,
            "symptoms": context.symptoms,
            "labs": list(context.labs.keys()),
        })
        logger.info(f"[EdarTraversal] PatientContext: {context}")

        # ── Phase 2: Oracle generates candidates ─────────────────────────────
        logger.info("[EdarTraversal] Phase 2: Oracle generating candidates (1 LLM call)...")
        self._emit({"event": "edar_phase", "phase": 2, "description": "Generating candidate hypotheses..."})
        try:
            candidates = self.oracle.generate(context, n=10)
        except Exception as e:
            logger.error(f"[EdarTraversal] Oracle failed: {e}")
            return EdarResult(
                synthesis=[], ranked=[], patient_context=context,
                duration_seconds=time.time() - t0, stop_reason="oracle_failed",
            )

        if not candidates:
            return EdarResult(
                synthesis=[], ranked=[], patient_context=context,
                duration_seconds=time.time() - t0, stop_reason="no_candidates",
            )

        self._emit({"event": "hypotheses_generated", "hypotheses": candidates, "source": "oracle_llm"})
        logger.info(f"[EdarTraversal] Candidates: {candidates}")

        # ── Phase 3: Build Evidence Graph ──────────────────────────────────────
        logger.info("[EdarTraversal] Phase 3: Building evidence graph (0 LLM)...")
        self._emit({"event": "edar_phase", "phase": 3, "description": "Building evidence graph..."})

        evidence_graph = self.graph_builder.build_all(candidates, context)

        for disease, node in evidence_graph.items():
            self._emit({
                "event": "evidence_node_built",
                "disease": disease,
                "confirmed": len(node.confirmed),
                "absent": len(node.absent),
                "contradicted": len(node.contradicted),
                "expected": len(node.expected_findings),
            })

        # ── Phase 4: Bayesian Belief Revision ─────────────────────────────────
        logger.info("[EdarTraversal] Phase 4: Bayesian belief revision (0 LLM)...")
        self._emit({"event": "edar_phase", "phase": 4, "description": "Computing Bayesian posteriors..."})

        ranked = self.belief_updater.update(evidence_graph, context)

        self._emit({
            "event": "hypotheses_scored",
            "ranked": [
                {
                    "hypothesis": d,
                    "final_score": round(p, 4),
                    "confirmed": len(n.confirmed),
                    "absent": len(n.absent),
                    "contradicted": len(n.contradicted),
                }
                for d, p, n in ranked[:5]
            ],
        })

        for i, (disease, posterior, node) in enumerate(ranked[:5], 1):
            logger.info(
                f"  [EDAR #{i}] '{disease}' "
                f"(posterior={posterior:.4f}, "
                f"✅{len(node.confirmed)} ❌{len(node.absent)} ⚡{len(node.contradicted)})"
            )

        # ── Phase 5: Discriminative Evidence Seeking ───────────────────────────
        if self.use_discriminator and self.discriminator and len(ranked) >= 2:
            logger.info("[EdarTraversal] Phase 5: Discriminative evidence seeking (0 LLM)...")
            self._emit({"event": "edar_phase", "phase": 5, "description": "Seeking discriminating evidence..."})
            ranked = self.discriminator.discriminate(ranked, context)

        # ── Synthesise ─────────────────────────────────────────────────────────
        synthesis = [d for d, _, _ in ranked[:self.top_k]]
        elapsed = time.time() - t0

        logger.info(f"[EdarTraversal] Done. synthesis={synthesis}, time={elapsed:.2f}s")
        self._emit({
            "event": "traversal_complete",
            "synthesis": synthesis,
            "stop_reason": "edar_bayesian",
            "duration_seconds": round(elapsed, 2),
        })
        self._write_log(case_name)

        ranked_hypotheses_compat = [
            type("RH", (), {
                "hypothesis": d,
                "final_score": p,
                "rank": i + 1,
                "matched_findings": n.confirmed,
                "raw_score": p,
            })()
            for i, (d, p, n) in enumerate(ranked)
        ]

        return EdarResult(
            synthesis=synthesis,
            ranked=ranked,
            patient_context=context,
            duration_seconds=elapsed,
            stop_reason="edar_bayesian",
            n_candidates=len(candidates),
            ranked_hypotheses=ranked_hypotheses_compat,
        )
