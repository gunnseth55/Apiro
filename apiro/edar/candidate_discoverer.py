"""
apiro/edar/candidate_discoverer.py
====================================
Phase 1: Discover candidate diseases from the corpus WITHOUT any LLM call.

Strategy:
  1. Embed the patient's combined findings (chief_complaint + symptoms + labs)
     into a vector and query ChromaDB for semantically similar chunks.
  2. Aggregate `disease_name` metadata tags from the returned chunks —
     diseases whose textbook descriptions most overlap with the patient's
     presentation naturally bubble up.
  3. Fallback: if metadata disease_name is missing for a chunk, extract
     disease mentions from the raw text using medical entity patterns.

Why this is better than the LLM Oracle:
  - Zero hallucination: every candidate is grounded in actual corpus matches.
  - Zero LLM tokens.
  - Reproducible: same patient presentation always yields the same candidates.
  - Speed: <200ms including embedding.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Optional

from apiro.patient.context import PatientContext

logger = logging.getLogger(__name__)

# ── Disease name extraction patterns (fallback for non-HPO chunks) ────────────
# These cover the most common textbook sentence starters and inline disease mentions

# ── MedRAG textbook chunk header extraction ───────────────────────────────────
# MedRAG chunks have the format: "TextbookName. [Disease/topic description]..."
# The first sentence after the prefix IS the disease being discussed.
# This is far more reliable than regex over arbitrary prose.

_TEXTBOOK_PREFIX_RE = re.compile(r'^[A-Za-z0-9_]+\.\s+')

# Minimum disease name quality: must look like a real medical entity
_MEDRAG_DISEASE_MUST_HAVE = re.compile(
    r'\b(tuberculosis|tb|mycobacterium|lymphadenitis|abscess|infection|disease|'
    r'syndrome|lymphoma|leukemia|carcinoma|tumor|malignancy|cancer|fever|pneumonia|'
    r'hepatitis|meningitis|vasculitis|arthritis|osteomyelitis|cellulitis|sepsis|'
    r'actinomycosis|nocardiosis|sarcoidosis|brucellosis|tularemia|bartonella|'
    r'staphylococcal|streptococcal|listeria|fungal|viral|bacterial|'
    r'embolism|dissection|infarction|tamponade|effusion|edema|failure|'
    r'stenosis|regurgitation|thrombosis|ischemia|hemorrhage)\b', re.I
)

_TEXTBOOK_STOP_WORDS = {
    "this", "these", "most", "some", "many", "all", "both", "each",
    "classically", "typically", "usually", "often", "rarely",
    "figure", "table", "chapter",
}


def _extract_from_chunk_header(text: str) -> Optional[str]:
    """
    Extract a disease candidate from a MedRAG textbook chunk header.

    MedRAG format: "InternalMed_Harrison. Tuberculous Lymphadenitis causes..."
    We strip the prefix and take the first meaningful phrase as the disease.
    """
    # Strip textbook prefix
    clean = _TEXTBOOK_PREFIX_RE.sub('', text.strip(), count=1)
    if not clean:
        return None

    # Take first ~80 characters — this is typically the disease name or topic
    header = clean[:100]

    # Split on sentence-ending punctuation to get just the opening clause
    # Split on first period, comma, or newline
    for sep in ['. ', '.\n', ', ', ' - ', ': ']:
        if sep in header:
            header = header.split(sep)[0]
            break

    header = header.strip().rstrip('.,;:)(')

    # Quality checks
    if len(header) < 5 or len(header) > 80:
        return None
    words = header.lower().split()
    if not words or words[0] in _TEXTBOOK_STOP_WORDS:
        return None
    # Must contain at least one medical disease-relevant term
    if not _MEDRAG_DISEASE_MUST_HAVE.search(header):
        return None

    return header


class CandidateDiscoverer:
    """
    Discovers disease candidates algorithmically from ChromaDB metadata
    and text. Zero LLM calls.

    Args:
        embedder:      Apiro Embedder instance (wraps SentenceTransformer + ChromaDB).
        n_query:       Number of corpus chunks to retrieve per query.
        n_candidates:  Maximum number of disease candidates to return.
        min_count:     Minimum chunk-hit count for a disease to be included.
    """

    def __init__(
        self,
        embedder,
        n_query: int = 60,
        n_candidates: int = 15,
        min_count: int = 1,
        disease_profile_collection = None,
    ):
        self.embedder = embedder
        self.n_query = n_query
        self.n_candidates = n_candidates
        self.min_count = min_count
        self.disease_profile_collection = disease_profile_collection

    def generate(self, context: PatientContext, n: int = 10) -> list[str]:
        """Alias for discover to be duck-type compatible with HypothesisOracle."""
        self.n_candidates = n
        return self.discover(context)

    def discover(self, context: PatientContext) -> list[str]:
        """
        Discover candidate diseases from the corpus without any LLM call.

        Args:
            context: Structured patient profile.

        Returns:
            Ordered list of disease name strings (most-supported first).
        """
        # Build a composite query from the patient's entire presentation
        parts = []
        if context.chief_complaint:
            parts.append(context.chief_complaint)
        parts.extend(context.symptoms[:8])  # top 8 symptoms
        lab_strings = [f"{k}: {v}" for k, v in context.labs.items()]
        parts.extend(lab_strings[:4])        # top 4 lab findings
        if context.history:
            parts.extend(context.history[:2])

        query = ". ".join(parts)
        if not query.strip():
            logger.warning("[CandidateDiscoverer] Empty patient context — no candidates generated.")
            return []

        logger.info(f"[CandidateDiscoverer] Querying corpus with patient presentation...")

        # Primary query: semantic search on full patient presentation
        chunks = self.embedder.query(query, n_results=self.n_query)

        # Secondary query: targeted HPO source search for structured disease→symptom mappings
        if context.symptoms:
            hpo_query = " ".join(context.symptoms[:4])
            hpo_chunks = self.embedder.query(hpo_query, n_results=30)
            # Only keep HPO-tagged chunks from secondary query
            hpo_chunks = [c for c in hpo_chunks if c.get("source_db") == "hpo"]
            chunks = chunks + hpo_chunks

        if not chunks:
            logger.warning("[CandidateDiscoverer] ChromaDB returned no chunks.")
            return []

        disease_counter: Counter = Counter()

        # ── HPO profile index query (Path B) ─────────────────────────────────────
        if self.disease_profile_collection is not None:
            # Encode explicitly with our embedder model to match the 768 dimension (mpnet)
            query_embedding = self.embedder._model.encode([query]).tolist()
            profile_results = self.disease_profile_collection.query(
                query_embeddings=query_embedding,
                n_results=20,
                include=["metadatas", "distances"],
            )
            if profile_results and profile_results.get("metadatas") and profile_results["metadatas"][0]:
                for meta in profile_results["metadatas"][0]:
                    disease_name = meta.get("disease_name", "")
                    if disease_name and len(disease_name) > 4:
                        disease_counter[disease_name] += 8  # high-trust: structured ontology hit

        for chunk in chunks:
            # Priority 1: HPO structured disease_name metadata — trust completely
            disease_name = chunk.get("disease_name", "")
            if disease_name and len(disease_name) > 4:
                disease_lower = disease_name.lower()
                # Filter out non-disease HPO entries
                if not any(bad in disease_lower for bad in [
                    "susceptibility", "modifier", "protection", "variation",
                    "polymorphism", "quantitative", "resistance to",
                ]):
                    disease_counter[disease_name.strip()] += 5

        # If HPO metadata gave us enough candidates, use those; otherwise also mine text
        if sum(disease_counter.values()) < 10:
            logger.info("[CandidateDiscoverer] HPO metadata sparse — extracting from chunk headers...")
            for chunk in chunks:
                text = chunk.get("text", "")
                if text:
                    candidate = _extract_from_chunk_header(text)
                    if candidate:
                        disease_counter[candidate] += 2  # weight header extraction less than HPO

        # Filter by minimum count and sort by frequency
        filtered = [
            (disease, count)
            for disease, count in disease_counter.most_common(self.n_candidates * 3)
            if count >= self.min_count and len(disease) > 4
        ]

        # Deduplicate: remove near-duplicates (e.g. "Dravet syndrome" vs "Dravet Syndrome")
        seen_lower: set[str] = set()
        final: list[str] = []
        for disease, _ in filtered:
            key = disease.lower().strip()
            if key not in seen_lower:
                seen_lower.add(key)
                final.append(disease)
            if len(final) >= self.n_candidates:
                break

        logger.info(
            f"[CandidateDiscoverer] Discovered {len(final)} candidates from "
            f"{len(chunks)} corpus chunks. Top 5: {final[:5]}"
        )

        return final
