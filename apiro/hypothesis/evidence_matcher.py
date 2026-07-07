"""
apiro/hypothesis/evidence_matcher.py — EvidenceMatcher
========================================================

Deterministic hypothesis scoring via ChromaDB evidence retrieval.

For each candidate hypothesis (e.g. "Acute cholecystitis"), this module:
  1. Queries ChromaDB: "What findings are typically present in [diagnosis]?"
  2. Retrieves the top-K most relevant medical knowledge chunks.
  3. Extracts the expected clinical findings from those chunks.
  4. Scores how many of those expected findings are present in the patient's
     actual PatientContext (reward-only: no penalty for missing findings).

WHY DETERMINISTIC:
  The old entropy engine asked the LLM how uncertain a node was — which is
  circular (same model that generated the node judges its own uncertainty).
  Evidence matching is pure feature comparison: string/semantic overlap
  between expected findings and actual patient data. Zero LLM calls.

SCORING:
  raw_score = matched_findings / total_expected_findings
  Range: [0.0, 1.0]. Higher = more evidence supporting this hypothesis.
  Ties broken by number of matched findings (more matches = stronger support).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from apiro.patient.context import PatientContext

logger = logging.getLogger(__name__)

# ── Minimum semantic overlap for a "match" (simple keyword approach) ──────────
_MIN_WORD_OVERLAP = 2   # how many significant words must overlap for a match


@dataclass
class HypothesisScore:
    """
    Scoring result for a single hypothesis against the patient's actual data.

    Attributes:
        hypothesis:          The candidate disease name.
        matched_findings:    Patient findings confirmed by retrieved evidence.
        expected_count:      Total expected findings retrieved from corpus.
        raw_score:           matched / expected_count (reward-only, range [0,1]).
        supporting_chunks:   Raw corpus chunks that drove the evidence.
    """
    hypothesis: str
    matched_findings: list[str] = field(default_factory=list)
    expected_count: int = 0
    raw_score: float = 0.0
    supporting_chunks: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"HypothesisScore(hypothesis={self.hypothesis!r}, "
            f"score={self.raw_score:.3f}, "
            f"matched={len(self.matched_findings)}/{self.expected_count})"
        )


class EvidenceMatcher:
    """
    Scores candidate hypotheses by matching expected findings against
    the patient's actual PatientContext. Zero LLM calls.

    Args:
        chroma_client: ChromaDB adapter with a .query() method.
        n_results:     Number of corpus chunks to retrieve per hypothesis.
    """

    def __init__(self, chroma_client, n_results: int = 8):
        self.chroma_client = chroma_client
        self.n_results = n_results

    def score(
        self,
        hypothesis: str,
        context: PatientContext,
    ) -> HypothesisScore:
        """
        Score a single hypothesis against the PatientContext.

        Args:
            hypothesis: Candidate disease name (e.g. "Acute cholecystitis").
            context:    Structured patient data.

        Returns:
            HypothesisScore with matched findings and raw score.
        """
        # Step 1: Retrieve expected findings from the corpus
        query = f"clinical presentation findings symptoms signs of {hypothesis}"
        chunks = self._retrieve(query)

        if not chunks:
            logger.debug(f"[EvidenceMatcher] No corpus coverage for '{hypothesis}'")
            return HypothesisScore(
                hypothesis=hypothesis,
                expected_count=0,
                raw_score=0.0,
                supporting_chunks=[],
            )

        # Step 2: Extract expected finding keywords from chunks
        expected_findings = self._extract_expected_findings(chunks)

        if not expected_findings:
            return HypothesisScore(
                hypothesis=hypothesis,
                expected_count=0,
                raw_score=0.0,
                supporting_chunks=chunks,
            )

        # Step 3: Match against actual patient findings (reward-only)
        patient_findings = context.all_findings()
        patient_text = " ".join(patient_findings).lower()

        matched = []
        for expected in expected_findings:
            if self._is_match(expected, patient_text):
                matched.append(expected)

        raw_score = len(matched) / len(expected_findings) if expected_findings else 0.0

        result = HypothesisScore(
            hypothesis=hypothesis,
            matched_findings=matched,
            expected_count=len(expected_findings),
            raw_score=raw_score,
            supporting_chunks=chunks,
        )

        logger.debug(
            f"[EvidenceMatcher] '{hypothesis}' → "
            f"score={raw_score:.3f} ({len(matched)}/{len(expected_findings)} matches)"
        )
        return result

    def score_all(
        self,
        hypotheses: list[str],
        context: PatientContext,
    ) -> list[HypothesisScore]:
        """
        Score all candidate hypotheses against the PatientContext.

        Returns list of HypothesisScore sorted by raw_score descending.
        """
        scores = [self.score(h, context) for h in hypotheses]
        scores.sort(key=lambda s: (s.raw_score, len(s.matched_findings)), reverse=True)
        logger.info(
            f"[EvidenceMatcher] Scored {len(scores)} hypotheses. "
            f"Top: {scores[0].hypothesis!r} ({scores[0].raw_score:.3f})"
            if scores else "[EvidenceMatcher] No hypotheses to score."
        )
        return scores

    # ── Internals ─────────────────────────────────────────────────────────────

    def _retrieve(self, query: str) -> list[str]:
        """Query ChromaDB for relevant medical knowledge chunks."""
        try:
            try:
                result = self.chroma_client.query(
                    query_texts=[query],
                    n_results=self.n_results,
                )
            except TypeError:
                result = self.chroma_client.query(
                    collection_name="medical_knowledge",
                    query_texts=[query],
                    n_results=self.n_results,
                )
            docs = result.get("documents", [[]])
            return docs[0] if docs else []
        except Exception as e:
            logger.warning(f"[EvidenceMatcher] ChromaDB query failed: {e}")
            return []

    @staticmethod
    def _extract_expected_findings(chunks: list[str]) -> list[str]:
        """
        Extract individual expected clinical findings from corpus chunks.

        Simple approach: split each chunk into clauses on commas/semicolons/periods
        and keep clauses that contain clinical finding keywords.
        Returns a deduplicated list of finding strings.
        """
        _CLINICAL_KEYWORDS = re.compile(
            r"\b(pain|fever|nausea|vomiting|tenderness|elevated|increased|decreased|"
            r"positive|negative|sign|symptom|present|absent|abnormal|normal|"
            r"swelling|jaundice|mass|lump|discharge|bleeding|fatigue|dyspnea|"
            r"cough|edema|pressure|rigidity|rebound|tachycardia|bradycardia|"
            r"hypertension|hypotension|lab|imaging|ct|mri|ultrasound)\b",
            re.IGNORECASE,
        )

        findings: list[str] = []
        seen: set[str] = set()

        for chunk in chunks:
            # Split on sentence boundaries and commas
            clauses = re.split(r"[.;]", chunk)
            for clause in clauses:
                clause = clause.strip()
                if len(clause) < 8:
                    continue
                if _CLINICAL_KEYWORDS.search(clause):
                    key = clause.lower()[:60]
                    if key not in seen:
                        seen.add(key)
                        findings.append(clause)

        return findings[:20]   # cap at 20 expected findings per hypothesis

    @staticmethod
    def _is_match(expected: str, patient_text: str) -> bool:
        """
        Reward-only semantic match: True if enough significant words from the
        expected finding appear in the patient's combined finding text.

        Uses simple word-overlap on medical content words (filters stopwords).
        """
        _STOPWORDS = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "can", "of", "in", "on", "at", "to", "for",
            "with", "by", "from", "or", "and", "but", "if", "as", "it", "its",
            "this", "that", "these", "those", "there", "their", "which", "who",
            "when", "where", "how", "what", "not", "no", "also", "often", "may",
            "typically", "usually", "commonly", "associated",
        }

        expected_words = {
            w.lower() for w in re.findall(r"\b[a-z]{3,}\b", expected.lower())
            if w.lower() not in _STOPWORDS
        }

        if not expected_words:
            return False

        overlap = sum(1 for w in expected_words if w in patient_text)
        return overlap >= _MIN_WORD_OVERLAP
