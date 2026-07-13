"""
apiro/hypothesis/oracle.py — HypothesisOracle
===============================================

Generates N broad candidate diagnoses from a PatientContext using a single
anchored LLM call. This replaces the generative graph expansion as the
PRIMARY source of diagnostic hypotheses.

WHY THIS EXISTS:
  Old Apiro expanded from a single symptom node, blindly generating text
  until saturation. This drifted toward rare findings. Instead, we now
  ask the LLM upfront: "Given this patient, what are the 8 most plausible
  diagnoses?" — then use the rest of the pipeline to TEST those candidates
  against evidence rather than generate them from scratch.

KEY DESIGN DECISIONS:
  - The prompt is strictly anchored to chief_complaint and symptoms.
  - History is passed but framed as "known background — do not repeat as diagnosis."
  - Output is requested as JSON (a "diagnoses" array of strings), not plain
    text lines. This replaces the old line-by-line regex parser, which could
    silently drop or mangle entries if the model added stray commentary,
    unexpected numbering, or merged two diagnoses onto one line. JSON with
    Ollama's `format: "json"` constraint is far harder for the model to
    produce malformed, and a `json.loads()` failure is a loud, catchable
    error instead of a silent parsing gap.
  - A regex-based fallback parser is kept for defense-in-depth in case the
    model ever returns non-JSON despite the format constraint (older/smaller
    local models sometimes ignore it under load).
  - n=8 by default: broad enough to catch the real diagnosis, narrow enough
    to keep evidence matching fast.
  - Retries with backoff on failure. A "failure" here means EITHER the HTTP
    request itself failing (timeout, connection error) OR the request
    succeeding but producing zero usable hypotheses after parsing (e.g. the
    model returned empty JSON, or garbled text neither parser could salvage).
    Both are retried identically — a request that "succeeds" but yields
    nothing useful is not meaningfully different from one that fails outright,
    and previously both silently returned [] with no second attempt.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional

import requests

from apiro.config import OLLAMA_BASE_URL, PRIMARY_MODEL
from apiro.patient.context import PatientContext

logger = logging.getLogger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────

_ORACLE_PROMPT = """\
You are a senior clinical diagnostician. Given the following patient presentation, \
generate the {n} most plausible diagnoses ranked from most to least likely.

=== PATIENT ===
Chief Complaint: {chief_complaint}
Age: {age}
Gender: {gender}
Symptoms / Signs: {symptoms}
Lab Results: {labs}
Imaging: {imaging}
Past Medical History / Risk Factors: {history}

=== STRICT RULES ===
1. Generate the {n} most plausible ACUTE diagnoses that BEST EXPLAIN the combination
   of ALL the above findings together — chief complaint, symptoms, labs, AND imaging.
2. Do NOT list pre-existing background conditions from Past Medical History unless
   they directly explain the acute presentation.
3. Return EXACTLY {n} disease names, ordered most to least likely.
4. Be specific (e.g. "Acute cholecystitis" not "Gallbladder disease").
5. Prioritise diagnoses that explain the LAB and IMAGING findings, not just the
   chief complaint symptom — the correct answer often lies in the objective data.

=== OUTPUT FORMAT ===
Return ONLY a valid JSON object, no prose, no markdown fences, in exactly this shape:
{{"diagnoses": ["<most likely diagnosis>", "<second>", "...", "<{n}th>"]}}"""


class HypothesisOracle:
    """
    Generates a broad differential diagnosis from a structured PatientContext.

    A single LLM call produces N candidate disease names. These are passed to
    EvidenceMatcher for scoring — NOT expanded generatively in the graph.

    Args:
        model:                 Ollama model name.
        ollama_url:            Ollama server URL.
        timeout:                Per-request timeout in seconds.
        max_retries:            Additional attempts after the first, on failure
                                 (default 2 -> up to 3 total attempts).
        retry_backoff_seconds:  Base delay before a retry; doubles each attempt
                                 (1.0 -> 1s, 2s, 4s, ...).
    """

    def __init__(
        self,
        model: str = PRIMARY_MODEL,
        ollama_url: str = OLLAMA_BASE_URL,
        timeout: int = 90,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def generate(
        self,
        context: PatientContext,
        n: int = 8,
    ) -> list[str]:
        """
        Generate N candidate diagnoses from the PatientContext.

        Retries on failure — either the HTTP request failing outright, or
        the request succeeding but yielding zero parseable hypotheses.
        Backs off between attempts (1s, 2s, 4s, ... by default) so a
        transient Ollama hiccup doesn't need a full pipeline re-run.

        Args:
            context: Structured patient data.
            n:       Number of candidate diagnoses to generate (default 8).

        Returns:
            List of up to N disease name strings, most likely first.
            Returns an empty list only if EVERY attempt fails — the caller
            (e.g. HypothesisTestingTraversal) must still handle that case,
            since no amount of retrying guarantees success.
        """
        prompt = self._build_prompt(context, n)
        cc_preview = context.chief_complaint[:60]

        total_attempts = self.max_retries + 1
        for attempt in range(1, total_attempts + 1):
            hypotheses = self._attempt_once(prompt, n)
            if hypotheses:
                if attempt > 1:
                    logger.info(
                        f"[HypothesisOracle] Succeeded on attempt {attempt}/{total_attempts} "
                        f"for CC='{cc_preview}'"
                    )
                logger.info(
                    f"[HypothesisOracle] Generated {len(hypotheses)} candidates "
                    f"for CC='{cc_preview}'"
                )
                for i, h in enumerate(hypotheses):
                    logger.debug(f"  [{i+1}] {h}")
                return hypotheses

            is_last_attempt = attempt == total_attempts
            if is_last_attempt:
                logger.error(
                    f"[HypothesisOracle] All {total_attempts} attempts failed/empty "
                    f"for CC='{cc_preview}' — returning empty list."
                )
            else:
                backoff = self.retry_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    f"[HypothesisOracle] Attempt {attempt}/{total_attempts} failed or "
                    f"returned no usable hypotheses for CC='{cc_preview}' — "
                    f"retrying in {backoff:.1f}s."
                )
                time.sleep(backoff)

        return []

    def _attempt_once(self, prompt: str, n: int) -> list[str]:
        """One request + parse, no retry logic. Returns [] on any failure."""
        raw = self._call_llm(prompt)
        if not raw:
            return []
        return self._parse(raw, n)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _build_prompt(self, context: PatientContext, n: int) -> str:
        def _fmt_list(items: list[str]) -> str:
            return ", ".join(items) if items else "None"

        def _fmt_labs(labs: dict[str, str]) -> str:
            if not labs:
                return "None"
            return ", ".join(f"{k}={v}" for k, v in labs.items())

        return _ORACLE_PROMPT.format(
            n=n,
            chief_complaint=context.chief_complaint,
            age=context.age if context.age is not None else "Unknown",
            gender=context.gender if context.gender else "Unknown",
            symptoms=_fmt_list(context.symptoms),
            labs=_fmt_labs(context.labs),
            imaging=_fmt_list(context.imaging),
            history=_fmt_list(context.history),
        )

    def _call_llm(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # Constrain Ollama's decoding to valid JSON. This is the main
            # defense against malformed output — the model literally cannot
            # emit stray commentary or broken structure while this is set.
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": 200,
            },
        }
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception as e:
            logger.error(f"[HypothesisOracle] LLM call failed: {e}")
            return ""

    @classmethod
    def _parse(cls, raw: str, n: int) -> list[str]:
        """
        Parse the LLM output into a clean list of disease names.

        Tries JSON first (the expected format, given `format: "json"` in the
        request). Falls back to the old line-by-line regex parser if JSON
        parsing fails for any reason — e.g. an older/smaller model ignoring
        the format constraint, or a truncated response — so a single bad
        response degrades gracefully instead of returning nothing.
        """
        parsed = cls._parse_json(raw, n)
        if parsed:
            return parsed

        logger.warning(
            "[HypothesisOracle] JSON parse failed or empty — "
            "falling back to line-based parsing."
        )
        return cls._parse_lines(raw, n)

    @staticmethod
    def _parse_json(raw: str, n: int) -> list[str]:
        """
        Parse the expected `{"diagnoses": [...]}` JSON shape.
        Returns [] on any structural problem (missing key, wrong type,
        non-string items, invalid JSON) rather than raising — callers
        treat an empty list as "try the fallback parser".
        """
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

        if not isinstance(obj, dict):
            return []

        items = obj.get("diagnoses")
        if not isinstance(items, list):
            return []

        results: list[str] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, str):
                continue
            name = item.strip()
            if len(name) <= 2:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(name)
            if len(results) >= n:
                break
        return results

    @staticmethod
    def _parse_lines(raw: str, n: int) -> list[str]:
        """
        Legacy fallback: parse plain-text, one-diagnosis-per-line output.
        Strips numbering, bullets, and trailing parenthetical explanations.
        Only used when JSON parsing fails.
        """
        lines = raw.strip().split("\n")
        results = []
        for line in lines:
            # Strip leading numbers, bullets, dashes
            clean = re.sub(r"^[\d]+[.)]\s*|^[-*•]\s*", "", line.strip())
            # Strip trailing parenthetical explanations like "(most likely)"
            clean = re.sub(r"\s*\(.*?\)\s*$", "", clean).strip()
            # Skip anything that's clearly leftover JSON/structural noise
            # (e.g. the model used a different key name and _parse_json
            # bailed, or wrapped its JSON in a markdown code fence) rather
            # than a real diagnosis name — braces/brackets/quotes/backticks
            # never appear in a legitimate disease name.
            if any(ch in clean for ch in '{}[]"`'):
                continue
            if clean.startswith("```"):
                continue
            if clean and len(clean) > 2:
                results.append(clean)
            if len(results) >= n:
                break
        return results