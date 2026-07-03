"""
graph/contradiction.py (Signal Rewrite)
----------------------------------------
Detects logical contradictions between two clinical claims using an LLM judge
instead of a cross-encoder NLI model.

WHY THIS CHANGE:

OLD (broken):
    cross-encoder/nli-MiniLM2-L6-H768 — a small NLI model trained on MNLI.
    Problem: fires on THEMATIC DIVERGENCE, not logical contradiction.
    "Patient has urinary obstruction" vs "Patient has productive cough"
    scores 0.97 contradiction because the sentences are topically unrelated.
    In multi-system disease, this prunes the correct cross-system evidence.

NEW (fixed):
    LLM judge with a targeted clinical question:
        "Can a single patient have both of these findings simultaneously?
         Answer YES or NO only."
    
    This correctly distinguishes:
      - Logical exclusions: "No fever present" vs "Patient has fever" → NO
      - Parallel findings: "Urinary obstruction" vs "Productive cough" → YES
      - Drug conflicts: "Aspirin indicated" vs "Aspirin contraindicated" → NO

COST:
    Each contradiction check requires one LLM call instead of one GPU forward
    pass. The LLM cache below makes this acceptable — repeated pairs are
    returned instantly without a network call.

    In practice, the number of contradiction checks per traversal is bounded:
        N_new_nodes × N_existing_nodes = 3 × ~30 = 90 pairs max.
    Most pairs will be skipped by should_check() (same as before) and cached
    hits are instant. The net slowdown is manageable.

INTERFACE:
    Identical to the original ContradictionDetector. No callers need changes.
    The NLIResult dataclass is preserved for compatibility.
"""

import re
import logging
import time
from dataclasses import dataclass
from typing import Literal, Optional

import requests

from apiro.config import OLLAMA_BASE_URL, PRIMARY_MODEL

logger = logging.getLogger(__name__)

# Maximum number of pairs to cache.
_CACHE_MAX = 4096

# Regex that matches the separator and "<type>" suffix appended to raw seed node claims.
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

# NegEx patterns (retained for negation_detected flag)
NEGEX_PATTERNS = re.compile(
    r"\b("
    r"no\b|not\b|without|denies|denied|absent|absence of|"
    r"negative for|rules? out|ruled out|free of|"
    r"never|unlikely|cannot|can't|doesn't|does not|"
    r"no evidence of|no sign of|no history of"
    r")\b",
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
    """
    Structured return type — interface-identical to the old ContradictionDetector.
    label: 'contradiction' | 'entailment' | 'neutral'
    score: confidence (0–1)
    negation_detected: whether NegEx fired on either input
    """
    label: Literal["contradiction", "entailment", "neutral"]
    score: float
    negation_detected: bool


# Singleton LLM client shared across all instances
_llm_url: str = OLLAMA_BASE_URL
_llm_model: str = PRIMARY_MODEL


class ContradictionDetector:
    """
    LLM-based logical contradiction detection.

    Usage:
        detector = ContradictionDetector()
        result = detector.check("aspirin is indicated", "aspirin is contraindicated")
        # → NLIResult(label='contradiction', score=0.95, negation_detected=False)

    The LLM is asked a direct clinical logic question: can these two findings
    coexist in the same patient? This is semantically correct and avoids the
    thematic-divergence false positives of NLI models.
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
        logger.info(f"[ContradictionDetector] Using LLM judge: {model} @ {ollama_url}")

    # ── Domain / abstraction gate ─────────────────────────────────────────────
    # Preserved from original: only check pairs where it's meaningful.

    @staticmethod
    def _seed_type(claim: str) -> str | None:
        m = _RAW_SEED_SUFFIX.search(claim)
        return m.group(1).lower() if m else None

    @classmethod
    def should_check(cls, claim_a: str, claim_b: str) -> bool:
        """
        Gate: run contradiction check only when the pair is meaningful.

        Rules:
          1. Both LLM hypotheses (no seed suffix) → always check.
          2. Both raw seed observations in the same abstraction group → check.
          3. Mixed (one hypothesis, one raw seed) → skip.

        NOTE: We removed the hardcoded keyword gates from the original because
        the LLM judge can handle cross-organ pairs correctly without them.
        """
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

        # Rule 3: mixed → skip
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
            "size": len(self._cache),
            "hit_rate": round(rate, 3),
        }

    def check(self, claim_a: str, claim_b: str) -> NLIResult:
        """
        Run LLM-based contradiction check on (claim_a, claim_b).
        Cached: repeated pairs are returned instantly.
        """
        negation_detected = self._has_negation(claim_a) or self._has_negation(claim_b)

        # Cache lookup
        key = self._cache_key(claim_a, claim_b)
        if key in self._cache:
            self._cache_hits += 1
            return self._cache[key]
        self._cache_misses += 1

        result = self._llm_judge(claim_a, claim_b, negation_detected)

        # Store in cache
        if len(self._cache) >= _CACHE_MAX:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = result
        return result

    def check_batch(self, pairs: list[tuple[str, str]]) -> list[NLIResult]:
        """Batch version — calls check() for each pair (cache-aware)."""
        return [self.check(a, b) for a, b in pairs]

    # ── LLM judge ──────────────────────────────────────────────────────────────

    def _llm_judge(
        self,
        claim_a: str,
        claim_b: str,
        negation_detected: bool,
    ) -> NLIResult:
        """Ask the LLM if the two findings can coexist in the same patient."""
        prompt = CONTRADICTION_JUDGE_PROMPT.format(
            claim_a=claim_a.strip(),
            claim_b=claim_b.strip(),
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 5,
            },
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
                    # LLM says they CANNOT coexist → contradiction
                    logger.debug(
                        f"[ContradictionDetector] CONTRADICTION: '{claim_a[:40]}' vs '{claim_b[:40]}'"
                    )
                    return NLIResult(
                        label="contradiction",
                        score=0.95,
                        negation_detected=negation_detected,
                    )
                else:
                    # YES or ambiguous → not a contradiction
                    return NLIResult(
                        label="neutral",
                        score=0.95,
                        negation_detected=negation_detected,
                    )

            except requests.exceptions.Timeout:
                time.sleep(3 * (attempt + 1))
            except Exception as e:
                logger.warning(
                    f"[ContradictionDetector] LLM judge failed (attempt {attempt+1}): {e}"
                )
                time.sleep(2 * (attempt + 1))

        # On total failure → assume NOT a contradiction (safe default: don't prune)
        logger.error("[ContradictionDetector] All LLM judge attempts failed — defaulting to neutral.")
        return NLIResult(label="neutral", score=0.5, negation_detected=negation_detected)
