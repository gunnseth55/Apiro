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
  - Output is a clean list of disease names, one per line, no explanation.
  - n=8 by default: broad enough to catch the real diagnosis, narrow enough
    to keep evidence matching fast.
"""

from __future__ import annotations

import logging
import re
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
3. Output EXACTLY {n} disease names, one per line, no numbering, no explanation.
4. Be specific (e.g. "Acute cholecystitis" not "Gallbladder disease").
5. Prioritise diagnoses that explain the LAB and IMAGING findings, not just the
   chief complaint symptom — the correct answer often lies in the objective data.

=== OUTPUT ({n} lines only) ==="""


class HypothesisOracle:
    """
    Generates a broad differential diagnosis from a structured PatientContext.

    A single LLM call produces N candidate disease names. These are passed to
    EvidenceMatcher for scoring — NOT expanded generatively in the graph.

    Args:
        model:      Ollama model name.
        ollama_url: Ollama server URL.
        timeout:    Request timeout in seconds.
    """

    def __init__(
        self,
        model: str = PRIMARY_MODEL,
        ollama_url: str = OLLAMA_BASE_URL,
        timeout: int = 90,
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.timeout = timeout

    def generate(
        self,
        context: PatientContext,
        n: int = 8,
    ) -> list[str]:
        """
        Generate N candidate diagnoses from the PatientContext.

        Args:
            context: Structured patient data.
            n:       Number of candidate diagnoses to generate (default 8).

        Returns:
            List of up to N disease name strings, most likely first.
            Returns an empty list on total failure.
        """
        prompt = self._build_prompt(context, n)
        raw = self._call_llm(prompt)
        hypotheses = self._parse(raw, n)

        logger.info(
            f"[HypothesisOracle] Generated {len(hypotheses)} candidates "
            f"for CC='{context.chief_complaint[:60]}'"
        )
        for i, h in enumerate(hypotheses):
            logger.debug(f"  [{i+1}] {h}")

        return hypotheses

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

    @staticmethod
    def _parse(raw: str, n: int) -> list[str]:
        """
        Parse the LLM output into a clean list of disease names.
        Strips numbering, bullets, and explanations. Returns up to n items.
        """
        lines = raw.strip().split("\n")
        results = []
        for line in lines:
            # Strip leading numbers, bullets, dashes
            clean = re.sub(r"^[\d]+[.)]\s*|^[-*•]\s*", "", line.strip())
            # Strip trailing parenthetical explanations like "(most likely)"
            clean = re.sub(r"\s*\(.*?\)\s*$", "", clean).strip()
            if clean and len(clean) > 2:
                results.append(clean)
            if len(results) >= n:
                break
        return results
