"""
apiro/edar/evidence_graph.py
==============================
Phase 2: Evidence Graph Construction.

For each candidate disease, we query the corpus to find its textbook
expected findings, then classify every expected finding as:
  - CONFIRMED    : semantically present in the patient's actual data
  - ABSENT       : expected by textbook but not seen in patient
  - CONTRADICTED : patient has a finding semantically opposite to expected

This produces a structured EvidenceNode per disease, which feeds directly
into the BayesianBeliefUpdater in Phase 3.

Zero LLM calls. All comparisons use cosine similarity on sentence embeddings.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
_CONFIRM_THRESHOLD     = 0.40   # cosine sim above this → finding is CONFIRMED
_CONTRADICT_THRESHOLD  = 0.25   # cosine sim below this with an antonym pair → CONTRADICTED

# Maximum expected findings extracted per disease.
# Keeping this low prevents well-documented diseases from accumulating
# disproportionate absent-finding penalties in Phase 3.
_MAX_EXPECTED_FINDINGS = 12

# ── Clinical symptom filter ───────────────────────────────────────────────────
# Only accept extracted text as an "expected finding" if it describes a
# clinically observable presentation element. This excludes pure pathological
# descriptions (caseous necrosis, granuloma morphology) that will never
# appear in a patient vignette, preventing spurious absent-finding penalties.
_CLINICAL_SYMPTOM_TERMS = re.compile(
    r"\b("
    r"fever|febrile|pyrexia|afebrile|temperature|hypothermia|hyperthermia|"
    r"cough|sputum|hemoptysis|dyspnea|shortness of breath|tachypnea|"
    r"pain|ache|tender|swelling|edema|mass|lump|"
    r"fatigue|malaise|weakness|lethargy|weight loss|anorexia|cachexia|"
    r"night sweats?|chills?|rigors?|diaphoresis|"
    r"lymphaden|hepato|spleno|jaundice|icteric|"
    r"nausea|vomit|diarrhea|constipation|abdominal|"
    r"headache|confusion|altered mental|seizure|meningism|photophobia|"
    r"rash|lesion|erythema|purulent|discharge|ulcer|pustule|vesicle|"
    r"tachycardia|bradycardia|hypertension|hypotension|"
    r"elevated|increased|decreased|low|high|abnormal|"
    r"WBC|ESR|CRP|creatinine|hemoglobin|platelet|leukocyte|lymphocyte|"
    r"blood culture|sputum culture|urine|chest X-ray|CT scan|MRI|ultrasound"
    r")\b",
    re.IGNORECASE,
)


def _is_useful_finding(text: str) -> bool:
    """
    Return True only if text describes a clinically observable finding.

    Filters out:
      - Pure pathology prose ("caseous necrosis", "epithelioid granulomata")
      - Generic connective sentences ("This is characterised by", "It presents in")
      - Findings with no clinical symptom terms (lab-only or radiology-only without
        the patient context to confirm them)
    """
    if not _CLINICAL_SYMPTOM_TERMS.search(text):
        return False
    # Exclude generic textbook prose openers that aren't real findings
    skip_starters = re.compile(
        r"^(this|these|it |the disease|the condition|classically|typically|in most|"
        r"histolog|patholog|granuloma|necrosis|fibrosis|calcif)",
        re.IGNORECASE,
    )
    return not skip_starters.match(text.strip())


# ── Antonym pairs for quick contradiction detection ───────────────────────────
_ANTONYM_PAIRS = [
    ({"fever", "febrile", "pyrexia", "hyperthermia"}, {"afebrile", "no fever", "normothermia", "apyrexial"}),
    ({"tachycardia", "rapid heart rate", "elevated heart rate"}, {"bradycardia", "slow heart rate"}),
    ({"hypertension", "high blood pressure", "elevated bp"}, {"hypotension", "low blood pressure", "shock"}),
    ({"hypoxia", "low oxygen", "desaturation"}, {"normal oxygen", "normoxic"}),
    ({"hepatomegaly", "enlarged liver"}, {"no hepatomegaly", "normal liver"}),
    ({"lymphadenopathy", "enlarged lymph nodes", "swollen lymph"}, {"no lymphadenopathy", "normal lymph nodes"}),
    ({"anemia", "low hemoglobin", "low hgb"}, {"polycythemia", "elevated hemoglobin"}),
    ({"leukocytosis", "elevated wbc", "high white cell"}, {"leukopenia", "low wbc", "neutropenia"}),
]


def _check_contradiction(expected: str, patient_findings: list[str]) -> bool:
    """
    Check if the expected finding is contradicted by any patient finding.
    Uses antonym pair matching for speed (no NLI model needed).
    """
    exp_lower = expected.lower()
    for positive_set, negative_set in _ANTONYM_PAIRS:
        exp_in_positive = any(term in exp_lower for term in positive_set)
        exp_in_negative = any(term in exp_lower for term in negative_set)

        if exp_in_positive:
            for finding in patient_findings:
                f_lower = finding.lower()
                if any(term in f_lower for term in negative_set):
                    return True
        if exp_in_negative:
            for finding in patient_findings:
                f_lower = finding.lower()
                if any(term in f_lower for term in positive_set):
                    return True
    return False


@dataclass
class EvidenceNode:
    """
    Evidence profile for a single candidate disease.

    Attributes:
        disease:            Disease name
        expected_findings:  Textbook expected symptoms/signs for this disease
        confirmed:          Expected findings present in patient (✅)
        absent:             Expected findings NOT in patient (❌)
        contradicted:       Findings where patient has the opposite (⚡)
        prior:              Uniform starting probability (set by updater)
        posterior:          Final Bayesian posterior after evidence processing
        support_chunks:     Raw corpus chunks that described this disease
    """
    disease:            str
    expected_findings:  list[str] = field(default_factory=list)
    confirmed:          list[str] = field(default_factory=list)
    absent:             list[str] = field(default_factory=list)
    contradicted:       list[str] = field(default_factory=list)
    prior:              float = 0.0
    posterior:          float = 0.0
    support_chunks:     list[str] = field(default_factory=list)

    @property
    def confirmation_rate(self) -> float:
        """Fraction of expected findings that are confirmed in patient."""
        total = len(self.expected_findings)
        if total == 0:
            return 0.0
        return len(self.confirmed) / total

    @property
    def contradiction_rate(self) -> float:
        """Fraction of expected findings that are contradicted in patient."""
        total = len(self.expected_findings)
        if total == 0:
            return 0.0
        return len(self.contradicted) / total

    def __repr__(self) -> str:
        return (
            f"EvidenceNode(disease={self.disease!r}, "
            f"confirmed={len(self.confirmed)}/{len(self.expected_findings)}, "
            f"contradicted={len(self.contradicted)}, "
            f"posterior={self.posterior:.4f})"
        )


class EvidenceGraphBuilder:
    """
    Builds EvidenceNodes for each candidate disease by:
      1. Querying the corpus for textbook expected findings of the disease.
      2. Extracting those findings as a clean list, filtered to clinical symptoms.
      3. Comparing each expected finding against the patient's actual findings
         using cosine similarity (via the pre-loaded sentence transformer).

    Zero LLM calls. All similarity computed on embeddings.

    Args:
        embedder:       Apiro Embedder (SentenceTransformer + ChromaDB).
        n_results:      Number of corpus chunks to retrieve per disease.
        confirm_threshold:  Cosine similarity above which a finding is CONFIRMED.
    """

    def __init__(
        self,
        embedder,
        n_results: int = 10,
        confirm_boost: float = 1.80,
    ):
        self.embedder = embedder
        self.n_results = n_results
        self.confirm_threshold = _CONFIRM_THRESHOLD

    def _extract_findings_from_text(self, text: str) -> list[str]:
        """
        Extract candidate findings from a single textbook chunk.

        Strategy (tried in order of quality):
          1. Sentence-level split: better preserves medical context, avoids
             breaking a symptom description mid-phrase.
          2. Bullet/semicolon split: handles list-style textbook entries.

        Both passes are filtered through _is_useful_finding() to discard
        histological/pathological descriptions that will never be in a
        patient vignette.
        """
        candidates: list[str] = []

        # ── Pass 1: sentence-level split ─────────────────────────────────────
        # Split on ". " followed by a capital letter (safe sentence boundary).
        # This keeps "S. aureus" from being split (no following capital).
        sentences = re.split(r"(?<=[a-z\.!?])\.\s+(?=[A-Z])", text)
        for sent in sentences:
            sent = sent.strip().rstrip(".,;:()")
            if 10 <= len(sent) <= 180 and len(sent.split()) >= 3 and _is_useful_finding(sent):
                candidates.append(sent)

        # ── Pass 2: bullet/semicolon split ───────────────────────────────────
        # Many textbook entries use bullet lists; these are missed by sentence split.
        parts = re.split(r"[;\n•·\-\*]", text)
        for part in parts:
            part = part.strip().rstrip(".,;:()")
            if 6 <= len(part) <= 130 and len(part.split()) >= 2 and _is_useful_finding(part):
                candidates.append(part)

        return candidates

    def _get_expected_findings(self, disease_name: str) -> tuple[list[str], list[str]]:
        """
        Query corpus for expected symptoms/signs of a disease.
        Returns (list_of_finding_strings, list_of_raw_chunk_texts).

        Key design decisions vs. the original implementation:
          - Sentence-level splitting preferred over character-level splitting.
          - Clinical symptom keyword gate rejects histological/pathological text.
          - Hard cap at _MAX_EXPECTED_FINDINGS (12) prevents count-based bias
            in the Bayesian updater (well-documented diseases had 20+ fragments).
          - Earlier corpus results (most semantically similar to query) are
            preferred, so findings from the best-matching chunks dominate.
        """
        queries = [
            f"symptoms and signs of {disease_name}",
            f"{disease_name} clinical presentation diagnosis",
        ]
        all_chunks = []
        for query in queries:
            chunks = self.embedder.query(query, n_results=self.n_results // 2 + 2)
            all_chunks.extend(chunks)

        # Deduplicate chunks, preserving order (best matches first)
        seen_texts: set[str] = set()
        unique_chunks = []
        for c in all_chunks:
            txt = c.get("text", "")
            if txt not in seen_texts and txt:
                seen_texts.add(txt)
                unique_chunks.append(c)

        raw_texts = [c.get("text", "") for c in unique_chunks]

        # Extract and filter findings from each chunk
        findings: list[str] = []
        for text in raw_texts:
            chunk_findings = self._extract_findings_from_text(text)
            findings.extend(chunk_findings)

        # Deduplicate and cap at _MAX_EXPECTED_FINDINGS
        seen: set[str] = set()
        unique_findings: list[str] = []
        for f in findings:
            key = f.lower()[:60]
            if key not in seen:
                seen.add(key)
                unique_findings.append(f)
            if len(unique_findings) >= _MAX_EXPECTED_FINDINGS:
                break

        logger.debug(
            f"[EvidenceGraphBuilder] '{disease_name}': extracted {len(unique_findings)} "
            f"clinical findings from {len(unique_chunks)} chunks"
        )

        return unique_findings, raw_texts

    def build(self, disease_name: str, context) -> EvidenceNode:
        """
        Build an EvidenceNode for one candidate disease against the patient context.

        Args:
            disease_name: The candidate disease to evaluate.
            context:      PatientContext with the patient's actual findings.

        Returns:
            EvidenceNode with confirmed/absent/contradicted findings populated.
        """
        expected, raw_chunks = self._get_expected_findings(disease_name)

        # Collect all patient findings into one flat list for comparison
        patient_findings = []
        if context.chief_complaint:
            patient_findings.append(context.chief_complaint)
        patient_findings.extend(context.symptoms)
        for k, v in context.labs.items():
            patient_findings.append(f"{k}: {v}")
        patient_findings.extend(context.history)
        patient_findings.extend(context.imaging)

        node = EvidenceNode(
            disease=disease_name,
            expected_findings=expected,
            support_chunks=raw_chunks[:3],
        )

        if not expected or not patient_findings:
            logger.debug(f"[EvidenceGraphBuilder] No findings to compare for '{disease_name}'")
            return node

        # Embed all expected findings and all patient findings in batch
        try:
            model = self.embedder._model
            expected_embs = model.encode(expected, normalize_embeddings=True, show_progress_bar=False)
            patient_embs  = model.encode(patient_findings, normalize_embeddings=True, show_progress_bar=False)
        except Exception as e:
            logger.warning(f"[EvidenceGraphBuilder] Embedding failed for '{disease_name}': {e}")
            return node

        # For each expected finding, find its best-matching patient finding
        for i, exp_finding in enumerate(expected):
            exp_emb = expected_embs[i]
            sims = np.dot(patient_embs, exp_emb)
            best_sim = float(np.max(sims))

            if best_sim >= self.confirm_threshold:
                node.confirmed.append(exp_finding)
            elif _check_contradiction(exp_finding, patient_findings):
                node.contradicted.append(exp_finding)
            else:
                node.absent.append(exp_finding)

        logger.debug(
            f"[EvidenceGraphBuilder] '{disease_name}': "
            f"✅{len(node.confirmed)} ❌{len(node.absent)} ⚡{len(node.contradicted)} "
            f"(of {len(expected)} expected, confirmation_rate={node.confirmation_rate:.0%})"
        )

        return node

    def build_all(self, candidates: list[str], context) -> dict[str, EvidenceNode]:
        """
        Build EvidenceNodes for all candidate diseases.

        Returns:
            Dict mapping disease_name → EvidenceNode.
        """
        logger.info(f"[EvidenceGraphBuilder] Building evidence graph for {len(candidates)} candidates...")
        graph = {}
        for disease in candidates:
            try:
                node = self.build(disease, context)
                graph[disease] = node
            except Exception as e:
                logger.warning(f"[EvidenceGraphBuilder] Failed for '{disease}': {e}")
        logger.info(f"[EvidenceGraphBuilder] Evidence graph complete. {len(graph)} nodes built.")
        return graph
