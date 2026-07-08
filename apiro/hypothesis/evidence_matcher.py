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

MATCHING (v2 — semantic):
  When an embedding model is available (loaded from EMBED_MODEL in config),
  each expected finding is compared to each patient finding using cosine
  similarity. A match is declared when cosine similarity >= SEMANTIC_THRESHOLD.
  This fixes the v1 word-overlap approach, which missed obvious synonyms like
  "fever" ↔ "febrile" or "epigastric pain" ↔ "abdominal tenderness".

  Falls back to word-overlap if the embedding model fails to load.

SCORING:
  raw_score = matched_findings / total_expected_findings
  Range: [0.0, 1.0]. Higher = more evidence supporting this hypothesis.
  Ties broken by number of matched findings (more matches = stronger support).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from apiro.config import EMBED_MODEL
from apiro.patient.context import PatientContext

logger = logging.getLogger(__name__)

# ── Semantic similarity threshold for a "match" ───────────────────────────────
# Calibrated on medical text pairs:
#   "fever" vs "febrile"         → ~0.72
#   "epigastric pain" vs "nausea" → ~0.55
#   "fever" vs "bradycardia"     → ~0.21
_SEMANTIC_THRESHOLD = 0.40

# Fallback: minimum word overlap if embedder unavailable
_MIN_WORD_OVERLAP = 2


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


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors."""
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class EvidenceMatcher:
    """
    Scores candidate hypotheses by matching expected findings against
    the patient's actual PatientContext. Zero LLM calls.

    Args:
        chroma_client:   ChromaDB adapter with a .query() method.
        n_results:       Number of corpus chunks to retrieve per hypothesis.
        semantic_threshold: Cosine similarity threshold for a semantic match.
                            Defaults to _SEMANTIC_THRESHOLD (0.40).
    """

    def __init__(
        self,
        chroma_client,
        n_results: int = 8,
        semantic_threshold: float = _SEMANTIC_THRESHOLD,
    ):
        self.chroma_client = chroma_client
        self.n_results = n_results
        self.semantic_threshold = semantic_threshold

        # Lazy-load the sentence-transformer for semantic matching
        self._encoder = None
        self._embed_cache: dict[str, np.ndarray] = {}
        self._use_semantic = False
        self._load_encoder()

    def _load_encoder(self) -> None:
        """Load sentence-transformers model. Silently degrades to word-overlap."""
        try:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(EMBED_MODEL)
            self._use_semantic = True
            logger.info(f"[EvidenceMatcher] Semantic matching enabled ({EMBED_MODEL})")
        except Exception as e:
            logger.warning(
                f"[EvidenceMatcher] Could not load encoder ({e}); "
                "falling back to word-overlap matching."
            )
            self._use_semantic = False

    def _embed(self, text: str) -> Optional[np.ndarray]:
        """Embed a string, with caching. Returns None on failure."""
        if not self._use_semantic or self._encoder is None:
            return None
        key = text[:200]
        if key in self._embed_cache:
            return self._embed_cache[key]
        try:
            vec = self._encoder.encode(text, normalize_embeddings=True, show_progress_bar=False)
            self._embed_cache[key] = vec
            return vec
        except Exception as e:
            logger.debug(f"[EvidenceMatcher] Embed failed: {e}")
            return None

    def _embed_batch(self, texts: list[str]) -> list[Optional[np.ndarray]]:
        """Batch-embed a list of texts, with per-item caching."""
        if not self._use_semantic or self._encoder is None:
            return [None] * len(texts)
        # Only encode texts not already cached
        uncached = [(i, t) for i, t in enumerate(texts) if t[:200] not in self._embed_cache]
        if uncached:
            idxs, txts = zip(*uncached)
            try:
                vecs = self._encoder.encode(
                    list(txts), normalize_embeddings=True, show_progress_bar=False
                )
                for idx, vec in zip(idxs, vecs):
                    self._embed_cache[texts[idx][:200]] = vec
            except Exception as e:
                logger.debug(f"[EvidenceMatcher] Batch embed failed: {e}")
        return [self._embed_cache.get(t[:200]) for t in texts]

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

        # Step 2: Extract expected finding clauses from chunks
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
        matched = self._match_findings(expected_findings, patient_findings)

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
        # Pre-embed all patient findings once for efficiency
        patient_findings = context.all_findings()
        if self._use_semantic:
            self._embed_batch(patient_findings)

        scores = [self.score(h, context) for h in hypotheses]
        scores.sort(key=lambda s: (s.raw_score, len(s.matched_findings)), reverse=True)
        if scores:
            logger.info(
                f"[EvidenceMatcher] Scored {len(scores)} hypotheses. "
                f"Top: {scores[0].hypothesis!r} ({scores[0].raw_score:.3f})"
            )
        else:
            logger.info("[EvidenceMatcher] No hypotheses to score.")
        return scores

    # ── Internals ─────────────────────────────────────────────────────────────

    def _match_findings(
        self,
        expected_findings: list[str],
        patient_findings: list[str],
    ) -> list[str]:
        """
        For each expected finding, check if any patient finding matches it.
        Returns list of expected findings that matched.

        Uses semantic cosine similarity when encoder is available;
        falls back to word-overlap.
        """
        if not patient_findings:
            return []

        matched = []

        if self._use_semantic:
            # Batch-embed expected and patient findings
            all_texts = expected_findings + patient_findings
            all_vecs = self._embed_batch(all_texts)
            exp_vecs = all_vecs[:len(expected_findings)]
            pat_vecs = all_vecs[len(expected_findings):]

            for expected, exp_vec in zip(expected_findings, exp_vecs):
                if exp_vec is None:
                    # Fall back to word overlap for this finding
                    patient_text = " ".join(patient_findings).lower()
                    if self._word_overlap_match(expected, patient_text):
                        matched.append(expected)
                    continue

                # Check if any patient finding exceeds the similarity threshold
                for pat_vec in pat_vecs:
                    if pat_vec is None:
                        continue
                    sim = _cosine(exp_vec, pat_vec)
                    if sim >= self.semantic_threshold:
                        matched.append(expected)
                        logger.debug(
                            f"[EvidenceMatcher] Semantic match: "
                            f"'{expected[:40]}' ↔ patient finding (sim={sim:.3f})"
                        )
                        break
        else:
            # Fallback: word overlap
            patient_text = " ".join(patient_findings).lower()
            for expected in expected_findings:
                if self._word_overlap_match(expected, patient_text):
                    matched.append(expected)

        return matched

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

        Splits on sentence boundaries and keeps clauses containing clinical
        finding keywords. Returns a deduplicated list capped at 20 items.
        """
        _CLINICAL_KEYWORDS = re.compile(
            r"\b(pain|fever|nausea|vomiting|tenderness|elevated|increased|decreased|"
            r"positive|negative|sign|symptom|present|absent|abnormal|normal|"
            r"swelling|jaundice|mass|lump|discharge|bleeding|fatigue|dyspnea|"
            r"cough|edema|pressure|rigidity|rebound|tachycardia|bradycardia|"
            r"hypertension|hypotension|lab|imaging|ct|mri|ultrasound|"
            r"fever|chills|malaise|anorexia|weight|loss|night sweats|"
            r"erythema|rash|pallor|cyanosis|diaphoresis)\b",
            re.IGNORECASE,
        )

        findings: list[str] = []
        seen: set[str] = set()

        for chunk in chunks:
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

        return findings[:20]

    @staticmethod
    def _word_overlap_match(expected: str, patient_text: str) -> bool:
        """
        Fallback word-overlap match. True if >= _MIN_WORD_OVERLAP significant
        words from the expected finding appear in the patient text.
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
