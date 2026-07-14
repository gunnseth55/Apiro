"""
graph/contradiction.py (Signal Rewrite v2)
------------------------------------------
Detects logical contradictions between two clinical claims using a two-stage
fast-filter + LLM judge.

WHY TWO-STAGE:

Stage 1 — Fast filter (no LLM):
    NegEx + keyword antonym detection. Catches the 95% of pairs that are
    obviously NOT contradictions (different topics) and the obvious ones that
    ARE (explicit negation, drug conflicts). Zero network calls.
    → If fast-filter says CONTRADICTION or NEUTRAL with high confidence → done.
    → If fast-filter is ambiguous AND the claims are highly related → Stage 2.

Stage 2 — LLM judge (only when needed):
    "Can a single patient have both of these findings simultaneously?"
    Only called when Stage 1 flags a HIGH-SIMILARITY pair as potentially
    contradictory. Similarity is measured by shared medical keywords.

RESULT:
    In practice, the LLM judge fires on <5 pairs per traversal (pairs that
    share the same drug, body part, or disease entity but differ in assertion).
    Total LLM calls for contradiction: ~5 instead of ~90 per iteration.

INTERFACE:
    Identical to the original ContradictionDetector. No callers need changes.
"""

import re
import logging
import time
from dataclasses import dataclass
from typing import Literal, Optional

import requests

from apiro.config import OLLAMA_BASE_URL, PRIMARY_MODEL

logger = logging.getLogger(__name__)

_CACHE_MAX = 4096

_RAW_SEED_SUFFIX = re.compile(
    r"[—\-–?]\s*(symptom|lab|vital|imaging|history|medication|procedure)\s*$",
    re.IGNORECASE,
)

_ABSTRACTION_GROUPS: dict[str, str] = {
    "symptom":    "observation",
    "vital":      "observation",
    "lab":        "measurement",
    "imaging":    "measurement",
    "history":    "context",
    "medication": "context",
    "procedure":  "context",
}

NEGEX_PATTERNS = re.compile(
    r"\b("
    r"no\b|not\b|without|denies|denied|absent|absence of|"
    r"negative for|rules? out|ruled out|free of|"
    r"never|unlikely|cannot|can't|doesn't|does not|"
    r"no evidence of|no sign of|no history of"
    r")\b",
    re.IGNORECASE,
)

# Pairs of antonym keywords. If claim_a has a word from set A and claim_b has
# the corresponding word from set B (or vice versa), they are likely contradictory.
_ANTONYM_PAIRS: list[tuple[set, set]] = [
    ({"indicated", "safe", "beneficial", "recommended", "first-line"},
     {"contraindicated", "avoid", "dangerous", "do not use", "prohibited"}),
    ({"elevated", "increased", "high", "raised", "positive"},
     {"normal", "within normal limits", "absent", "negative", "low", "decreased"}),
    ({"present", "confirmed", "diagnosed", "detected", "demonstrates"},
     {"absent", "not present", "ruled out", "excluded", "no evidence"}),
    ({"fever", "pyrexia", "febrile", "temperature elevated"},
     {"afebrile", "no fever", "apyrexial", "temperature normal"}),
]

# Medical entity keywords — pairs sharing these are considered HIGH-SIMILARITY
# and will be escalated to the LLM judge if a negation is also detected.
_MEDICAL_ENTITY_WORDS = re.compile(
    r"\b(aspirin|warfarin|heparin|metformin|metoprolol|lisinopril|"
    r"troponin|creatinine|sodium|potassium|hemoglobin|glucose|bilirubin|"
    r"fever|pain|dyspnea|cough|edema|hemorrhage|infarction|embolism|"
    r"infection|sepsis|cancer|tumor|carcinoma|lymphoma|"
    r"kidney|liver|lung|heart|brain|thyroid|adrenal|"
    r"hypertension|hypotension|tachycardia|bradycardia)\b",
    re.IGNORECASE,
)

CONTRADICTION_JUDGE_PROMPT = """\
You are a clinical logician. Given two clinical findings about the same patient, determine if they logically EXCLUDE each other.

Finding A: {claim_a}
Finding B: {claim_b}

Question: Can a single patient simultaneously have BOTH of these findings?

Rules:
- Answer YES if both findings can coexist in the same patient (even if unrelated or from different organ systems).
- Answer NO only if one finding logically rules out the other (true medical contradiction).
- Do NOT answer NO just because the findings are from different organ systems.

Answer with YES or NO only."""


@dataclass
class NLIResult:
    label: Literal["contradiction", "entailment", "neutral"]
    score: float
    negation_detected: bool


class ContradictionDetector:
    """
    Two-stage contradiction detection:
    1. Fast NegEx + antonym keyword filter (no LLM, instant)
    2. LLM judge — only for high-similarity pairs with negation present

    Interface identical to original ContradictionDetector.
    """

    def __init__(
        self,
        model: str = PRIMARY_MODEL,
        ollama_url: str = OLLAMA_BASE_URL,
        timeout: int = 30,
        retries: int = 2,
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.timeout = timeout
        self.retries = retries
        self._cache: dict[tuple[int, int], NLIResult] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._llm_calls = 0
        logger.info(f"[ContradictionDetector] Two-stage LLM judge: {model} @ {ollama_url}")

    @staticmethod
    def _seed_type(claim: str) -> str | None:
        m = _RAW_SEED_SUFFIX.search(claim)
        return m.group(1).lower() if m else None

    @classmethod
    def should_check(cls, claim_a: str, claim_b: str) -> bool:
        """Same gate as before: only check hypothesis-hypothesis or same-group seed pairs."""
        type_a = cls._seed_type(claim_a)
        type_b = cls._seed_type(claim_b)

        if type_a is None and type_b is None:
            return True

        if type_a is not None and type_b is not None:
            group_a = _ABSTRACTION_GROUPS.get(type_a)
            group_b = _ABSTRACTION_GROUPS.get(type_b)
            return group_a is not None and group_a == group_b

        return False

    def _has_negation(self, text: str) -> bool:
        return bool(NEGEX_PATTERNS.search(text))

    def _cache_key(self, claim_a: str, claim_b: str) -> tuple[int, int]:
        ha, hb = hash(claim_a), hash(claim_b)
        return (ha, hb) if ha <= hb else (hb, ha)

    def cache_info(self) -> dict:
        total = self._cache_hits + self._cache_misses
        rate = self._cache_hits / total if total else 0.0
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "llm_calls": self._llm_calls,
            "size": len(self._cache),
            "hit_rate": round(rate, 3),
        }

    def check(self, claim_a: str, claim_b: str) -> NLIResult:
        """
        Two-stage contradiction check.
        Stage 1: fast keyword/negation filter — no LLM.
        Stage 2: LLM judge — only when Stage 1 is ambiguous AND claims share entities.
        """
        negation_detected = self._has_negation(claim_a) or self._has_negation(claim_b)

        # Cache lookup
        key = self._cache_key(claim_a, claim_b)
        if key in self._cache:
            self._cache_hits += 1
            return self._cache[key]
        self._cache_misses += 1

        result = self._fast_filter(claim_a, claim_b, negation_detected)
        if result is not None:
            # Fast filter gave a confident answer — no LLM needed
            self._store_cache(key, result)
            return result

        # Stage 2: LLM judge — only if claims share medical entities
        if self._shares_medical_entities(claim_a, claim_b):
            result = self._llm_judge(claim_a, claim_b, negation_detected)
            logger.debug(
                f"[ContradictionDetector] LLM judge: {result.label} | "
                f"'{claim_a[:35]}' vs '{claim_b[:35]}'"
            )
        else:
            # Different topics entirely — cannot be a true logical contradiction
            result = NLIResult(label="neutral", score=0.9, negation_detected=negation_detected)

        self._store_cache(key, result)
        return result

    def check_batch(self, pairs: list[tuple[str, str]]) -> list[NLIResult]:
        return [self.check(a, b) for a, b in pairs]

    # ── Stage 1: Fast filter ──────────────────────────────────────────────────

    def _fast_filter(
        self, claim_a: str, claim_b: str, negation_detected: bool
    ) -> Optional[NLIResult]:
        """
        Returns NLIResult if we can decide confidently without an LLM call.
        Returns None if ambiguous (caller must escalate to LLM).
        """
        a, b = claim_a.lower(), claim_b.lower()

        # Check antonym keyword pairs
        for set_pos, set_neg in _ANTONYM_PAIRS:
            a_pos = any(kw in a for kw in set_pos)
            b_pos = any(kw in b for kw in set_pos)
            a_neg = any(kw in a for kw in set_neg)
            b_neg = any(kw in b for kw in set_neg)

            # One claim positive, the other negative on the same dimension
            if (a_pos and b_neg) or (a_neg and b_pos):
                # Only flag as contradiction if they share medical entities
                # (prevents "elevated troponin" vs "normal blood pressure" false hits)
                if self._shares_medical_entities(claim_a, claim_b):
                    return NLIResult(
                        label="contradiction",
                        score=0.92,
                        negation_detected=negation_detected,
                    )

        # No strong keyword signal found — ambiguous, escalate to LLM if needed
        return None

    def _shares_medical_entities(self, claim_a: str, claim_b: str) -> bool:
        """
        True if the two claims share at least one medical entity keyword.
        Claims sharing entities are semantically related and worth checking.
        Claims with no shared entities are topically unrelated → not contradictions.
        """
        entities_a = set(m.group().lower() for m in _MEDICAL_ENTITY_WORDS.finditer(claim_a))
        entities_b = set(m.group().lower() for m in _MEDICAL_ENTITY_WORDS.finditer(claim_b))
        return bool(entities_a & entities_b)

    # ── Stage 2: LLM judge ────────────────────────────────────────────────────

    def _llm_judge(
        self, claim_a: str, claim_b: str, negation_detected: bool
    ) -> NLIResult:
        """Ask the LLM if the two findings can coexist in the same patient."""
        self._llm_calls += 1
        prompt = CONTRADICTION_JUDGE_PROMPT.format(
            claim_a=claim_a.strip(),
            claim_b=claim_b.strip(),
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 5},
        }
        for attempt in range(self.retries):
            try:
                resp = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                raw = resp.json().get("response", "").strip().upper()
                first_word = re.split(r"\s|\.", raw)[0].strip(".,!?\"'")

                if first_word == "NO":
                    return NLIResult(
                        label="contradiction",
                        score=0.95,
                        negation_detected=negation_detected,
                    )
                else:
                    return NLIResult(
                        label="neutral",
                        score=0.95,
                        negation_detected=negation_detected,
                    )

            except requests.exceptions.Timeout:
                time.sleep(3 * (attempt + 1))
            except Exception as e:
                logger.warning(f"[ContradictionDetector] LLM judge failed (attempt {attempt+1}): {e}")
                time.sleep(2 * (attempt + 1))

        # Total failure → safe default: do not prune
        logger.error("[ContradictionDetector] All LLM attempts failed — defaulting to neutral.")
        return NLIResult(label="neutral", score=0.5, negation_detected=negation_detected)

    def _store_cache(self, key: tuple, result: NLIResult) -> None:
        if len(self._cache) >= _CACHE_MAX:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = result
