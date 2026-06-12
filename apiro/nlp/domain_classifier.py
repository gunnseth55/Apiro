"""
nlp/domain_classifier.py
=========================
Zero-shot domain classifier for clinical text.

Maps any free-text clinical claim or finding into one of Apiro's 7 medical
domains using facebook/bart-large-mnli as a zero-shot NLI classifier.

Design notes:
  - No fine-tuning required: BART-MNLI handles biomedical domain labels well
    out of the box because the label names are semantically descriptive.
  - A keyword-based fast-path handles obvious short cases (e.g. "BRCA1" → genetics,
    "metoprolol" → pharmacology) without incurring model latency.
  - Batch classification is supported for pipeline efficiency.
  - Falls back to DEFAULT_DOMAIN if confidence is below MIN_CONFIDENCE.

Usage:
    from apiro.nlp.domain_classifier import DomainClassifier
    clf = DomainClassifier()
    clf.classify("Troponin I elevated at 4.2 ng/mL")        # → "lab findings"
    clf.classify("BRCA1 pathogenic variant detected")        # → "genetics"
    clf.classify("Start metoprolol 25 mg BID")              # → "treatment"
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Domain labels (must match config.THETA_BY_DOMAIN keys) ────────────────────

DOMAINS = [
    "pathophysiology",
    "pharmacology",
    "genetics",
    "imaging",
    "lab findings",
    "treatment",
    "comorbidity",
]

# Internal → config key mapping (lab findings → lab for theta lookup)
DOMAIN_TO_CONFIG_KEY = {
    "pathophysiology": "pathophysiology",
    "pharmacology":    "pharmacology",
    "genetics":        "genetics",
    "imaging":         "imaging",
    "lab findings":    "lab",
    "treatment":       "treatment",
    "comorbidity":     "comorbidity",
}

DEFAULT_DOMAIN   = "pathophysiology"
MIN_CONFIDENCE   = 0.25    # below this → fall back to DEFAULT_DOMAIN

# ── Keyword fast-path ─────────────────────────────────────────────────────────
# Order matters: first match wins. Checked before the model.
_KEYWORD_RULES: list[tuple[re.Pattern, str]] = [
    # Genetics
    (re.compile(
        r"\b(gene|variant|mutation|snp|allele|genotype|locus|exon|"
        r"chromosome|haplotype|polymorphism|vcf|gnomad|clinvar|omim|"
        r"pathogenic|likely pathogenic|vus|frameshift|missense|nonsense|"
        r"deletion|duplication|inversion|cnv|brca|tp53|bag3|mybpc3|prkag2|"
        r"pkp2|scn[15]a|hbb|cftr|ttn|kcnq1)\b",
        re.IGNORECASE,
    ), "genetics"),

    # Lab findings
    (re.compile(
        r"\b(troponin|creatinine|hemoglobin|hematocrit|wbc|platelet|"
        r"sodium|potassium|chloride|bicarbonate|bun|glucose|lactate|"
        r"alt|ast|bilirubin|inr|pt|ptt|crp|esr|ferritin|d.?dimer|"
        r"bnp|nt.probnp|albumin|calcium|magnesium|phosphorus|tsh|"
        r"ng\/ml|iu\/l|mmol\/l|meq\/l|mg\/dl|g\/dl)\b",
        re.IGNORECASE,
    ), "lab findings"),

    # Imaging
    (re.compile(
        r"\b(ct|mri|x.?ray|echocardiogram|echo|ultrasound|pet|spect|"
        r"angiogram|angiography|mammogram|colonoscopy|endoscopy|"
        r"radiograph|scan|imaging|opacity|consolidation|effusion|"
        r"infiltrate|atelectasis|cardiomegaly|pneumothorax)\b",
        re.IGNORECASE,
    ), "imaging"),

    # Pharmacology (drug mechanisms — not administration)
    (re.compile(
        r"\b(mechanism of action|receptor|agonist|antagonist|inhibitor|"
        r"substrate|bioavailability|half.?life|pharmacokinetic|"
        r"pharmacodynamic|ic50|ec50|binding affinity|cytochrome|"
        r"p450|cyp3a4|adme)\b",
        re.IGNORECASE,
    ), "pharmacology"),

    # Treatment (administered drugs + procedures)
    (re.compile(
        r"\b(administer|prescribe|start|initiate|discontinue|titrate|"
        r"dose|dosage|infusion|injection|surgery|procedure|intervention|"
        r"pci|cabg|stenting|dialysis|intubation|ventilation|"
        r"aspirin|heparin|warfarin|metoprolol|lisinopril|atorvastatin|"
        r"nitroglycerin|furosemide|amiodarone|vancomycin|ceftriaxone)\b",
        re.IGNORECASE,
    ), "treatment"),

    # Comorbidity
    (re.compile(
        r"\b(comorbid|history of|past medical|pmh|prior|chronic|"
        r"pre.?existing|concurrent|coexisting|background|underlying)\b",
        re.IGNORECASE,
    ), "comorbidity"),
]


# ── DomainClassifier ──────────────────────────────────────────────────────────

class DomainClassifier:
    """
    Classifies clinical text into one of Apiro's 7 medical domains.

    Uses a two-tier approach:
      1. Fast keyword matching (regex, ~0 ms) for obvious cases.
      2. Zero-shot NLI with facebook/bart-large-mnli for ambiguous text.

    Args:
        model_name:      HuggingFace model identifier. Defaults to
                         facebook/bart-large-mnli (1.6 GB, best quality).
                         Use 'typeform/distilbart-mnli-12-3' (400 MB) for
                         lower memory usage.
        use_keyword_fastpath: Enable keyword rules (default True). Disable
                              for pure-model classification.
        device:          PyTorch device. Default 'cpu' for stability.
    """

    MODEL_NAME = "facebook/bart-large-mnli"
    _cached_pipeline = None  # Class-level cache for zero-shot classification pipeline

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        use_keyword_fastpath: bool = True,
        device: str = "cpu",
    ):
        self.model_name           = model_name
        self.use_keyword_fastpath = use_keyword_fastpath
        self.device               = device

    @property
    def _pipeline(self):
        self._load()
        return DomainClassifier._cached_pipeline

    def _load(self) -> None:
        """Lazy-load the zero-shot classification pipeline."""
        if DomainClassifier._cached_pipeline is not None:
            return
        try:
            from transformers import pipeline
            logger.info(f"[DomainClassifier] Loading {self.model_name} on {self.device}...")
            DomainClassifier._cached_pipeline = pipeline(
                "zero-shot-classification",
                model=self.model_name,
                device=0 if self.device == "cuda" else -1,
            )
            logger.info("[DomainClassifier] Model loaded.")
        except Exception as e:
            logger.error(f"[DomainClassifier] Failed to load model: {e}")
            raise


    # ── Keyword fast-path ──────────────────────────────────────────────────

    def _keyword_classify(self, text: str) -> Optional[str]:
        """
        Return a domain label if a keyword rule matches, else None.
        First match wins (rules ordered by specificity).
        """
        for pattern, domain in _KEYWORD_RULES:
            if pattern.search(text):
                return domain
        return None

    # ── Model classification ───────────────────────────────────────────────

    def _model_classify(self, text: str) -> tuple[str, float]:
        """
        Run zero-shot NLI classification.
        Returns (domain, confidence_score).
        """
        self._load()

        # Build hypothesis template for clinical framing
        result = self._pipeline(
            text,
            candidate_labels=DOMAINS,
            hypothesis_template="This clinical text is about {}.",
            multi_label=False,
        )
        top_label = result["labels"][0]
        top_score = result["scores"][0]
        return top_label, top_score

    # ── Public API ─────────────────────────────────────────────────────────

    def classify(self, text: str) -> str:
        """
        Classify a single clinical text string into an Apiro domain.

        Returns:
            Domain string — one of DOMAINS, or DEFAULT_DOMAIN on failure.
        """
        text = text.strip()
        if not text:
            return DEFAULT_DOMAIN

        # Fast-path: keyword rules
        if self.use_keyword_fastpath:
            domain = self._keyword_classify(text)
            if domain:
                logger.debug(f"[DomainClassifier] Keyword match → '{domain}': {text[:60]}")
                return domain

        # Slow-path: BART zero-shot
        try:
            domain, score = self._model_classify(text)
            if score < MIN_CONFIDENCE:
                logger.debug(
                    f"[DomainClassifier] Low confidence ({score:.2f}) → defaulting "
                    f"to '{DEFAULT_DOMAIN}'"
                )
                return DEFAULT_DOMAIN
            logger.debug(f"[DomainClassifier] Model → '{domain}' ({score:.2f}): {text[:60]}")
            return domain
        except Exception as e:
            logger.warning(f"[DomainClassifier] Model error: {e}. Using default.")
            return DEFAULT_DOMAIN

    def classify_with_score(self, text: str) -> tuple[str, float]:
        """
        Like classify() but also returns the confidence score.

        Keyword matches return confidence=1.0.
        Model matches return the raw NLI score.
        """
        text = text.strip()
        if not text:
            return DEFAULT_DOMAIN, 0.0

        if self.use_keyword_fastpath:
            domain = self._keyword_classify(text)
            if domain:
                return domain, 1.0

        try:
            domain, score = self._model_classify(text)
            if score < MIN_CONFIDENCE:
                return DEFAULT_DOMAIN, score
            return domain, score
        except Exception:
            return DEFAULT_DOMAIN, 0.0

    def classify_batch(self, texts: list[str]) -> list[str]:
        """
        Classify a list of texts, using the fast-path where possible
        and batching model calls for efficiency.

        Returns list of domain labels in the same order as input.
        """
        results: list[str | None] = [None] * len(texts)
        model_indices: list[int]  = []

        # Fast-path first pass
        for i, text in enumerate(texts):
            text = text.strip()
            if not text:
                results[i] = DEFAULT_DOMAIN
                continue
            if self.use_keyword_fastpath:
                domain = self._keyword_classify(text)
                if domain:
                    results[i] = domain
                    continue
            model_indices.append(i)

        # Model pass for remaining texts
        if model_indices:
            self._load()
            batch_texts = [texts[i] for i in model_indices]
            try:
                batch_results = self._pipeline(
                    batch_texts,
                    candidate_labels=DOMAINS,
                    hypothesis_template="This clinical text is about {}.",
                    multi_label=False,
                )
                # pipeline returns a list when given a list
                if isinstance(batch_results, dict):
                    batch_results = [batch_results]
                for idx, result in zip(model_indices, batch_results):
                    score = result["scores"][0]
                    domain = result["labels"][0] if score >= MIN_CONFIDENCE else DEFAULT_DOMAIN
                    results[idx] = domain
            except Exception as e:
                logger.warning(f"[DomainClassifier] Batch model error: {e}. Using defaults.")
                for idx in model_indices:
                    results[idx] = DEFAULT_DOMAIN

        return [r or DEFAULT_DOMAIN for r in results]

    def config_key(self, text: str) -> str:
        """
        Classify text and return the config.py key (e.g. 'lab' not 'lab findings').
        Used for theta lookup in SaturationDetector.
        """
        domain = self.classify(text)
        return DOMAIN_TO_CONFIG_KEY.get(domain, domain)
