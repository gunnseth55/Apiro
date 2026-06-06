"""
entropy/engine.py — EntropyEngine
==================================
Extracted and cleaned from scripts/run_experiment.py (calibration phase).

The sole validated signal is token-level Shannon entropy on the first
generated token, queried at three temperatures and combined with
temperature-weighted averaging to reduce sampling noise.

Semantic dispersion was validated as flat across all question groups
and is permanently excluded.
Temperature SENSITIVITY (slope T=0.3→1.2) was excluded because the
Ollama logprob API returns unnormalized probability scores, making
raw slope comparisons unreliable. Temperature weighting for NOISE
REDUCTION is still valid.
"""

import math
import time
from typing import Optional

import numpy as np
import requests

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    OLLAMA_BASE_URL, PRIMARY_MODEL, TOP_LOGPROBS,
    MAX_FIRST_TOKEN, ENTROPY_TEMPERATURES, ENTROPY_TEMP_WEIGHTS,
)


class EntropyEngine:
    """
    Queries Ollama for the first-token logprob distribution and computes
    Shannon entropy. The primary interface for all graph traversal decisions.
    """

    def __init__(
        self,
        model: str = PRIMARY_MODEL,
        ollama_url: str = OLLAMA_BASE_URL,
        top_k: int = TOP_LOGPROBS,
        timeout: int = 120,
        retries: int = 3,
    ):
        self.model      = model
        self.ollama_url = ollama_url
        self.top_k      = top_k
        self.timeout    = timeout
        self.retries    = retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def first_token_entropy(self, prompt: str, temperature: float = 0.3) -> Optional[float]:
        """
        Query Ollama for the top-k logprobs of the FIRST generated token and
        return Shannon entropy in nats.

        Returns None if the model is unreachable or does not surface logprobs.
        """
        lp_result = self._query_logprobs(prompt, temperature)
        if lp_result is None:
            return None
        return self._shannon_entropy(lp_result["logprobs"])

    def temperature_corrected_entropy(self, prompt: str) -> Optional[float]:
        """
        Query at T=0.3, 0.7, 1.2 and return a weighted average:
            H_corrected = 0.6·H(0.3) + 0.3·H(0.7) + 0.1·H(1.2)

        Highest weight on T=0.3 to suppress sampling noise. This is a
        noise-reduction technique, NOT a temperature sensitivity measurement.

        Returns None if all queries fail.
        """
        entropies = {}
        for temp in ENTROPY_TEMPERATURES:
            h = self.first_token_entropy(prompt, temperature=temp)
            if h is not None:
                entropies[temp] = h

        if not entropies:
            return None

        weighted_sum  = sum(ENTROPY_TEMP_WEIGHTS[t] * h for t, h in entropies.items())
        weight_total  = sum(ENTROPY_TEMP_WEIGHTS[t] for t in entropies)
        return weighted_sum / weight_total

    def top1_probability(self, prompt: str, temperature: float = 0.3) -> Optional[float]:
        """
        Return the probability of the single most likely first token.
        Low top-1 probability → model is hedging → high uncertainty.
        """
        lp_result = self._query_logprobs(prompt, temperature)
        if lp_result is None:
            return None
        return float(np.exp(lp_result["logprobs"][0]))

    def is_reachable(self) -> bool:
        """Return True if Ollama server is reachable and the model is available."""
        try:
            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            resp.raise_for_status()
            pulled = {m["name"] for m in resp.json().get("models", [])}
            model_base = self.model.split(":")[0]
            return any(p.startswith(model_base) for p in pulled)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query_logprobs(self, prompt: str, temperature: float) -> Optional[dict]:
        """
        POST to /api/generate with num_predict=1 and logprobs=true.
        Returns {"logprobs": [float, ...], "tokens": [str, ...], "token": str}
        or None on failure.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": MAX_FIRST_TOKEN,
                "top_k": 100,
            },
            "logprobs": True,
            "top_logprobs": self.top_k,
        }
        for attempt in range(self.retries):
            try:
                resp = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()

                logprobs_raw = data.get("logprobs")
                if not logprobs_raw:
                    return None

                first_pos  = logprobs_raw[0] if isinstance(logprobs_raw, list) else logprobs_raw
                top_entries = first_pos.get("top_logprobs", [])
                if not top_entries:
                    return None

                return {
                    "token":    first_pos.get("token", ""),
                    "logprobs": [e["logprob"] for e in top_entries],
                    "tokens":   [e["token"]   for e in top_entries],
                }
            except requests.exceptions.Timeout:
                time.sleep(5 * (attempt + 1))
            except Exception as e:
                time.sleep(3 * (attempt + 1))
        return None

    @staticmethod
    def _shannon_entropy(logprobs: list[float]) -> float:
        """
        Shannon entropy (nats) from a list of log-probabilities.
        Normalises the top-k truncated distribution before computing.
        """
        probs = np.exp(np.array(logprobs, dtype=np.float64))
        probs = probs / probs.sum()
        probs = np.clip(probs, 1e-12, 1.0)
        return float(-np.sum(probs * np.log(probs)))
