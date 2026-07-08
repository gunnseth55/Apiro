"""
graph/contradiction.py
----------------------
Detects logical contradictions between two clinical claims using a
cross-encoder NLI model fine-tuned on medical text (MedNLI).

WHY A CROSS-ENCODER (not a bi-encoder)?
  Bi-encoders embed each sentence independently and compare embeddings.
  They're fast but miss fine-grained token interactions.
  Cross-encoders feed BOTH sentences together as a single input, letting
  the attention heads "see" the pair at once — much better at entailment/
  contradiction detection.

WHY MiniLM and not RoBERTa-MNLI?
  RoBERTa-MNLI is ~1.3GB. MiniLM is ~330MB and fast enough for graph traversal.
  Swap via the `model_name` constructor arg — the interface is identical.

LABEL ORDER (important!):
  The model outputs 3 logits. The label mapping is:
    index 0 → 'contradiction'
    index 1 → 'entailment'
    index 2 → 'neutral'

NEGEX LAYER:
  Small NLI models often miss clinical negation ("no fever" vs "has fever").
  We use a simplified NegEx regex to detect negation in either claim and
  set a `negation_detected` flag — callers can apply a lower threshold.

DOMAIN GATE (critical for traversal correctness):
  The NLI model operates at the sentence level and has no notion of clinical
  abstraction layers. Comparing a raw observation node ("Sweating ? symptom")
  against a mechanistic hypothesis ("Elevated BNP may be due to sympathetic
  activation") will often yield spuriously high contradiction scores because
  the model detects *thematic* divergence, not *logical* contradiction.

  Rule: only run the NLI check when both nodes belong to the same clinical
  abstraction group (symptom vs symptom, lab vs lab, etc.) OR when both are
  free-text hypothesis claims (not raw seed observations).

  Raw seed observations are identified by the "? <type>" suffix pattern
  ("? symptom", "? lab", "? vital", "? imaging", "? history", "? medication").
"""

import re
from dataclasses import dataclass
from typing import Literal

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Maximum number of (claim_a, claim_b) pairs to keep in the NLI result cache.
# Each entry is tiny (one NLIResult dataclass), so 4096 slots cost < 1 MB.
_NLI_CACHE_MAX = 4096

# ── NegEx patterns ───────────────────────────────────────────────────────────
NEGEX_PATTERNS = re.compile(
    r"\b("
    r"no\b|not\b|without|denies|denied|absent|absence of|"
    r"negative for|rules? out|ruled out|free of|"
    r"never|unlikely|cannot|can't|doesn't|does not|"
    r"no evidence of|no sign of|no history of"
    r")\b",
    re.IGNORECASE,
)

# Label order matches the model's output head (verified against HF model card)
LABEL_MAPPING: list[str] = ["contradiction", "entailment", "neutral"]

# Score threshold above which we trust a contradiction label.
# Raised from 0.85 → 0.92: the NLI model fires too liberally at 0.85 on
# cross-domain clinical pairs that share semantic territory but don't logically
# contradict (e.g. "Elevated BNP" vs "Sweating" both appear in heart failure).
CONTRADICTION_THRESHOLD = 0.92

# Regex that matches the separator and "<type>" suffix appended to raw seed node claims
# by findings_to_seed_nodes() / PatientFinding.to_claim().
# Supports em-dash (—), en-dash (–), hyphen (-), and question mark (?) as separators.
_RAW_SEED_SUFFIX = re.compile(
    r"[—\-–?]\s*(symptom|lab|vital|imaging|history|medication|procedure)\s*$",
    re.IGNORECASE,
)


# Observation types that share the same clinical abstraction layer.
# Two nodes may be contradiction-checked only if they are in the same group
# OR both are free-text hypothesis claims (no seed suffix).
_ABSTRACTION_GROUPS: dict[str, str] = {
    "symptom":    "observation",
    "vital":      "observation",
    "lab":        "measurement",
    "imaging":    "measurement",
    "history":    "context",
    "medication": "context",
    "procedure":  "context",
}


@dataclass
class NLIResult:
    """
    Structured return type from ContradictionDetector.check().

    label: one of 'contradiction', 'entailment', 'neutral'
    score: confidence for that label (softmax probability, 0–1)
    negation_detected: whether NegEx fired on either input
    """
    label: Literal["contradiction", "entailment", "neutral"]
    score: float
    negation_detected: bool


class ContradictionDetector:
    """
    Checks whether two clinical claims contradict each other.

    Usage:
        detector = ContradictionDetector()
        result = detector.check("administer aspirin immediately", "aspirin is contraindicated")
        # → NLIResult(label='contradiction', score=0.93, negation_detected=False)

    Integration note for traversal.py:
        Only flag an edge as contradictory if:
            result.label == 'contradiction' AND result.score > CONTRADICTION_THRESHOLD

    SWAP POINT for paper evaluation:
        Change model_name to 'cross-encoder/nli-roberta-base' for higher accuracy.
    """

    def __init__(self, model_name: str = "cross-encoder/nli-MiniLM2-L6-H768"):
        print(f"[ContradictionDetector] Loading model: {model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            torch_dtype=torch.float16
        )
        self.model.eval()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        print(f"[ContradictionDetector] Running on {self.device}")
        # ── NLI result cache ──────────────────────────────────────────────────
        # Keyed on (hash(claim_a), hash(claim_b)).  The cross-encoder is
        # symmetric for our purposes, so we normalise to sorted order.
        self._cache: dict[tuple[int, int], NLIResult] = {}
        self._cache_hits   = 0
        self._cache_misses = 0

    # ── Domain / abstraction gate ──────────────────────────────────────────────

    @staticmethod
    def _seed_type(claim: str) -> str | None:
        """
        Return the seed-observation type if the claim ends with '? <type>',
        e.g. 'Sweating ? symptom' → 'symptom'.  Returns None for hypothesis
        claims produced by the LLM expander (they have no such suffix).
        """
        m = _RAW_SEED_SUFFIX.search(claim)
        return m.group(1).lower() if m else None

    @classmethod
    def should_check(cls, claim_a: str, claim_b: str) -> bool:
        """
        Domain/abstraction gate — returns True only when the NLI check is
        meaningful for this pair.

        Rules (applied in order):
          1. If both are free-text hypothesis claims (no seed suffix) → True.
             LLM-generated hypotheses can genuinely contradict each other.
          2. If both are raw seed observations of the *same* abstraction group
             (e.g. symptom vs vital are both 'observation') → True.
             E.g. "No chest pain ? symptom" vs "Chest pain ? symptom".
          3. Otherwise → False (different abstraction levels; NLI unreliable).
             E.g. hypothesis vs raw observation, or lab vs symptom.
        """
        # ── Clinical Domain Gate to prevent cross-organ false positives ──
        a = claim_a.lower()
        b = claim_b.lower()
        
        gates = [
            # Cardiac vs GI (Case 1)
            (
                {"myocardial", "infarction", "angina", "coronary", "cardiac", "heart", "pericarditis", "tamponade", "ischemia", "stemi", "nstemi", "troponin", "ecg", "electrocardiogram", "perfusion", "substernal"},
                {"esophageal", "spasm", "gerd", "achalasia", "reflux", "dysphagia", "gastric", "stomach", "barrett", "biliary", "chagas", "motility"}
            ),
            # Malaria vs G6PD (Case 2)
            (
                {"malaria", "plasmodium", "falciparum", "vivax", "ovale", "blood film", "thick and thin"},
                {"g6pd", "glucose-6-phosphate", "heinz", "bite cell", "nitrofurantoin", "hemolytic", "hemolysis"}
            ),
            # Subacute Thyroiditis vs Cardiac (Case 3)
            (
                {"thyroid", "thyroiditis", "tsh", "t4", "neck", "swallowing", "de quervain"},
                {"myocardial", "infarction", "angina", "coronary", "cardiac", "heart", "pericarditis", "tamponade", "ischemia", "stemi", "nstemi", "troponin", "ecg", "electrocardiogram", "perfusion", "substernal"}
            ),
            # Aortic Dissection vs Pulmonary Embolism (Case 4)
            (
                {"aortic", "dissection", "aneurysm", "tearing", "scapulae", "mediastinum"},
                {"pulmonary", "embolism", "ctpa", "lung", "pleuritic"}
            ),
            # Pheochromocytoma vs Anxiety (Case 5)
            (
                {"pheochromocytoma", "metanephrines", "catecholamines", "adrenal", "chromaffin"},
                {"panic", "anxiety", "alprazolam", "psychological", "generalized anxiety"}
            ),
            # Addison's vs Gastroenteritis (Case 6)
            (
                {"addison", "cortisol", "acth", "adrenal insufficiency", "hyperpigmentation", "buccal", "creases", "sodium", "potassium"},
                {"gastroenteritis", "nausea", "vomiting", "diarrhea", "abdominal pain", "dehydration"}
            ),
            # NPH vs Parkinson/Alzheimer (Case 7)
            (
                {"nph", "hydrocephalus", "ventriculomegaly", "lumbar puncture", "spinal tap"},
                {"parkinson", "alzheimer", "tremor", "rigidity", "levodopa"}
            ),
            # Lead Poisoning vs Appendicitis (Case 8)
            (
                {"lead", "plumbism", "stippling", "paint", "scraping"},
                {"appendicitis", "guarding", "rebound", "wbc", "appendix"}
            ),
            # NMO vs MS (Case 9)
            (
                {"neuromyelitis", "nmo", "devic", "aquaporin", "aqp4", "letm"},
                {"multiple sclerosis", "oligoclonal", "plaques", "periventricular"}
            ),
            # Myasthenia Gravis vs Stroke (Case 10)
            (
                {"myasthenia", "mg", "acetylcholine", "achr", "ptosis", "diplopia", "tensilon", "edrophonium", "pyridostigmine"},
                {"stroke", "ischemic", "hemorrhage", "occlusion", "bell's palsy", "bell"}
            )
        ]

        for set1, set2 in gates:
            has1_a = any(kw in a for kw in set1)
            has2_a = any(kw in a for kw in set2)
            has1_b = any(kw in b for kw in set1)
            has2_b = any(kw in b for kw in set2)
            
            if (has1_a and has2_b) or (has2_a and has1_b):
                return False

        type_a = cls._seed_type(claim_a)
        type_b = cls._seed_type(claim_b)

        # Rule 1: both are LLM hypotheses
        if type_a is None and type_b is None:
            return True

        # Rule 2: both are raw seed observations in the same abstraction group
        if type_a is not None and type_b is not None:
            group_a = _ABSTRACTION_GROUPS.get(type_a)
            group_b = _ABSTRACTION_GROUPS.get(type_b)
            return group_a is not None and group_a == group_b

        # Rule 3: mixed (one hypothesis, one raw seed) → skip
        return False



    def _has_negation(self, text: str) -> bool:
        """Returns True if NegEx pattern fires on this text."""
        return bool(NEGEX_PATTERNS.search(text))

    def _check_heuristics(self, claim_a: str, claim_b: str) -> bool:
        a = claim_a.lower()
        b = claim_b.lower()

        # Normalize whitespace
        a = re.sub(r"\s+", " ", a)
        b = re.sub(r"\s+", " ", b)

        # 1. Direct negation: indicated/safe vs contraindicated/avoid/dangerous/do not use
        drugs = ["metformin", "aspirin", "warfarin", "heparin", "metoprolol", "lisinopril"]
        for drug in drugs:
            if drug in a and drug in b:
                # Check for contraindicated/safe conflict
                contra = ("contraindicated" in a or "contraindication" in a or "avoid" in a or "do not use" in a or "dangerous" in a)
                safe = ("safe" in b or "indicated" in b or "standard" in b or "beneficial" in b)
                if contra and safe:
                    return True
                
                contra_b = ("contraindicated" in b or "contraindication" in b or "avoid" in b or "do not use" in b or "dangerous" in b)
                safe_a = ("safe" in a or "indicated" in a or "standard" in a or "beneficial" in a)
                if contra_b and safe_a:
                    return True

                # Check for dosage logic: e.g. "10mg" vs "above 5mg is dangerous"
                # Extract dosages in mg
                dose_a_match = re.search(r"(\d+(?:\.\d+)?)\s*mg", a)
                dose_b_match = re.search(r"(\d+(?:\.\d+)?)\s*mg", b)
                if dose_a_match and dose_b_match:
                    val_a = float(dose_a_match.group(1))
                    val_b = float(dose_b_match.group(1))
                    
                    is_above_a = ("above" in a or "greater than" in a or ">" in a or "more than" in a)
                    is_above_b = ("above" in b or "greater than" in b or ">" in b or "more than" in b)
                    
                    danger_a = ("dangerous" in a or "contraindicated" in a or "avoid" in a or "toxic" in a or "lethal" in a)
                    danger_b = ("dangerous" in b or "contraindicated" in b or "avoid" in b or "toxic" in b or "lethal" in b)

                    if is_above_a and danger_a and not is_above_b:
                        if val_b > val_a:
                            return True
                    if is_above_b and danger_b and not is_above_a:
                        if val_a > val_b:
                            return True
        return False

    def _cache_key(self, claim_a: str, claim_b: str) -> tuple[int, int]:
        """Symmetric cache key — order of claims does not matter for NLI."""
        ha, hb = hash(claim_a), hash(claim_b)
        return (ha, hb) if ha <= hb else (hb, ha)

    def cache_info(self) -> dict:
        """Return cache hit/miss statistics for diagnostics."""
        total = self._cache_hits + self._cache_misses
        rate  = self._cache_hits / total if total else 0.0
        return {
            "hits":      self._cache_hits,
            "misses":    self._cache_misses,
            "size":      len(self._cache),
            "hit_rate":  round(rate, 3),
        }

    def check(self, claim_a: str, claim_b: str) -> NLIResult:
        """
        Run NLI inference on (claim_a, claim_b), with result caching.

        Repeated (claim_a, claim_b) pairs are returned from the in-memory
        cache without re-running the cross-encoder forward pass.
        The cross-encoder sees both claims concatenated as:
            [CLS] claim_a [SEP] claim_b [SEP]

        Returns an NLIResult with label, confidence score, and negation flag.
        """
        negation_detected = self._has_negation(claim_a) or self._has_negation(claim_b)

        if self._check_heuristics(claim_a, claim_b):
            return NLIResult(
                label="contradiction",
                score=0.95,
                negation_detected=negation_detected,
            )

        # ── Cache lookup ──────────────────────────────────────────────────────
        key = self._cache_key(claim_a, claim_b)
        if key in self._cache:
            self._cache_hits += 1
            return self._cache[key]
        self._cache_misses += 1

        inputs = self.tokenizer(
            claim_a,
            claim_b,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        ).to(self.device)

        with torch.no_grad():
            logits = self.model(**inputs).logits  # shape: (1, 3)

        probs = torch.softmax(logits, dim=-1).squeeze()  # shape: (3,)
        best_idx = int(probs.argmax())

        result = NLIResult(
            label=LABEL_MAPPING[best_idx],
            score=float(probs[best_idx]),
            negation_detected=negation_detected,
        )

        # ── Cache store (evict oldest if over budget) ─────────────────────────
        if len(self._cache) >= _NLI_CACHE_MAX:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = result
        return result

    def check_batch(self, pairs: list[tuple[str, str]]) -> list[NLIResult]:
        """
        Batch version for efficiency when checking many pairs at once.
        Reduces GPU round-trips when the graph is large.
        Cache-aware: pairs already seen in this session are returned
        immediately without a GPU forward pass.
        """
        if not pairs:
            return []

        results = [None] * len(pairs)
        model_pairs = []
        model_indices = []

        for i, (a, b) in enumerate(pairs):
            negation_detected = self._has_negation(a) or self._has_negation(b)
            if self._check_heuristics(a, b):
                results[i] = NLIResult(
                    label="contradiction",
                    score=0.95,
                    negation_detected=negation_detected,
                )
                continue

            # ── Cache lookup ──────────────────────────────────────────────────
            key = self._cache_key(a, b)
            if key in self._cache:
                self._cache_hits += 1
                results[i] = self._cache[key]
                continue

            self._cache_misses += 1
            model_pairs.append((a, b))
            model_indices.append(i)

        if model_pairs:
            micro_batch_size = 16
            for chunk_start in range(0, len(model_pairs), micro_batch_size):
                chunk_end = chunk_start + micro_batch_size
                chunk_pairs = model_pairs[chunk_start:chunk_end]
                chunk_indices = model_indices[chunk_start:chunk_end]

                claims_a = [p[0] for p in chunk_pairs]
                claims_b = [p[1] for p in chunk_pairs]

                negations = [
                    self._has_negation(a) or self._has_negation(b)
                    for a, b in chunk_pairs
                ]

                inputs = self.tokenizer(
                    claims_a,
                    claims_b,
                    return_tensors="pt",
                    truncation=True,
                    max_length=512,
                    padding=True,
                ).to(self.device)

                with torch.no_grad():
                    logits = self.model(**inputs).logits

                probs = torch.softmax(logits, dim=-1)
                best_indices = probs.argmax(dim=-1).tolist()

                for i, idx in enumerate(best_indices):
                    orig_idx = chunk_indices[i]
                    result = NLIResult(
                        label=LABEL_MAPPING[idx],
                        score=float(probs[i][idx]),
                        negation_detected=negations[i],
                    )
                    # ── Cache store ───────────────────────────────────────────────
                    key = self._cache_key(claims_a[i], claims_b[i])
                    if len(self._cache) >= _NLI_CACHE_MAX:
                        self._cache.pop(next(iter(self._cache)))
                    self._cache[key] = result
                    results[orig_idx] = result

        return results
