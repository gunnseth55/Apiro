"""
graph/saturation.py — SaturationDetector
==========================================
Determines when the belief graph has converged and traversal should stop.

Three simultaneous conditions must hold:
  1. Mean entropy of the last `window` expanded nodes < theta
  2. Variance of those entropies < max_variance (graph is stable)
  3. Entropy trend coefficient <= 0 (entropy not rising)

Domain-specific theta values are defined in config.THETA_BY_DOMAIN.
"""
from __future__ import annotations

import numpy as np

from apiro.graph.belief_graph import BeliefGraph
from apiro.config import SATURATION_WINDOW, SATURATION_MAX_VARIANCE, THETA_BY_DOMAIN, DEFAULT_THETA


class SaturationDetector:
    """
    Checks whether the belief graph has reached epistemic saturation.
    All three conditions must hold simultaneously.
    """

    def __init__(
        self,
        theta: float = DEFAULT_THETA,
        window: int = SATURATION_WINDOW,
        max_variance: float = SATURATION_MAX_VARIANCE,
    ):
        self.theta        = theta
        self.window       = window
        self.max_variance = max_variance

    def is_saturated(self, graph: BeliefGraph) -> bool:
        """Return True if all 3 saturation conditions hold."""
        status = self.get_status(graph)
        return status["saturated"]

    def get_status(self, graph: BeliefGraph) -> dict:
        """
        Return a full diagnostic dict:
          {
            saturated:    bool,
            avg_entropy:  float | None,
            variance:     float | None,
            trend:        float | None,
            n_samples:    int,
            theta:        float,
            conditions:   {low_entropy, low_variance, non_rising}
          }
        """
        recent = graph.get_recent_entropies(self.window)
        n = len(recent)

        if n < 2:
            return {
                "saturated":   False,
                "avg_entropy": None,
                "variance":    None,
                "trend":       None,
                "n_samples":   n,
                "theta":       self.theta,
                "conditions":  {"low_entropy": False, "low_variance": False, "non_rising": False},
            }

        avg_entropy = float(np.mean(recent))
        variance    = float(np.var(recent))
        trend       = graph.get_entropy_trend(self.window)

        low_entropy  = avg_entropy  < self.theta
        low_variance = variance     < self.max_variance
        non_rising   = trend        <= 0.0

        saturated = low_entropy and low_variance and non_rising

        return {
            "saturated":   saturated,
            "avg_entropy": round(avg_entropy, 5),
            "variance":    round(variance, 5),
            "trend":       round(trend, 5),
            "n_samples":   n,
            "theta":       self.theta,
            "conditions":  {
                "low_entropy":  low_entropy,
                "low_variance": low_variance,
                "non_rising":   non_rising,
            },
        }

    @classmethod
    def for_domain(cls, domain: str, **kwargs) -> "SaturationDetector":
        """
        Convenience constructor that sets theta from config.THETA_BY_DOMAIN.
        Falls back to DEFAULT_THETA for unknown domains.
        """
        theta = THETA_BY_DOMAIN.get(domain.lower(), DEFAULT_THETA)
        return cls(theta=theta, **kwargs)
