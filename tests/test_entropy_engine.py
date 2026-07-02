"""
tests/test_entropy_engine.py
============================
Unit tests for EntropyEngine — specifically the new
epistemic_certainty_entropy() method and _build_verification_prompt().

These tests run WITHOUT Ollama (the actual Ollama call is mocked).
They verify:
  1. _build_verification_prompt produces a well-formed yes/no prompt.
  2. epistemic_certainty_entropy() calls temperature_corrected_entropy()
     on the verification prompt (not the raw claim).
  3. The yes/no prompt forces closed-form framing of the claim.
  4. Context chunks are embedded in the prompt when provided.
  5. None fallback: if temperature_corrected_entropy returns None, the
     method also returns None.
"""

from unittest.mock import MagicMock, patch
import pytest

from apiro.entropy.engine import EntropyEngine


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_engine() -> EntropyEngine:
    """Return an EntropyEngine with no real Ollama connection needed."""
    return EntropyEngine(model="llama3.1:8b", ollama_url="http://localhost:11434")


# ── _build_verification_prompt ────────────────────────────────────────────────

class TestBuildVerificationPrompt:
    """Verify the closed-form yes/no prompt structure."""

    def test_contains_claim(self):
        claim = "Troponin elevation indicates myocardial injury."
        prompt = EntropyEngine._build_verification_prompt(claim)
        assert claim.strip() in prompt

    def test_contains_yes_or_no_instruction(self):
        prompt = EntropyEngine._build_verification_prompt("any claim")
        assert "Yes or No" in prompt

    def test_no_context_no_evidence_block(self):
        prompt = EntropyEngine._build_verification_prompt("some claim", context_chunks=None)
        assert "Clinical evidence:" not in prompt

    def test_context_chunks_included(self):
        chunks = [
            "Troponin is a cardiac biomarker.",
            "Elevated troponin is seen in STEMI.",
        ]
        prompt = EntropyEngine._build_verification_prompt("some claim", context_chunks=chunks)
        assert "Clinical evidence:" in prompt
        assert "Troponin is a cardiac biomarker." in prompt
        assert "Elevated troponin is seen in STEMI." in prompt

    def test_empty_context_chunks_no_evidence_block(self):
        """Empty list should not produce an evidence block."""
        prompt = EntropyEngine._build_verification_prompt("some claim", context_chunks=[])
        assert "Clinical evidence:" not in prompt

    def test_prompt_ends_with_yes_no_instruction(self):
        """The closed-form instruction must be at the end."""
        prompt = EntropyEngine._build_verification_prompt("claim here")
        assert prompt.strip().endswith("Answer with Yes or No only.")

    def test_whitespace_only_chunks_skipped(self):
        """Chunks that are only whitespace should be excluded from evidence block."""
        chunks = ["  ", "Real evidence sentence."]
        prompt = EntropyEngine._build_verification_prompt("claim", context_chunks=chunks)
        assert "Real evidence sentence." in prompt
        # Whitespace-only chunk should not appear as a bullet
        assert "-     " not in prompt


# ── epistemic_certainty_entropy ───────────────────────────────────────────────

class TestEpistemicCertaintyEntropy:
    """
    Verify that epistemic_certainty_entropy() routes to
    temperature_corrected_entropy() with the *verification prompt*,
    not the raw claim.
    """

    def test_calls_temperature_corrected_entropy_not_raw_claim(self):
        """
        The key correctness property: the method must NOT pass the raw claim
        to temperature_corrected_entropy. It must construct a yes/no prompt first.
        """
        engine = make_engine()
        claim = "Aspirin is contraindicated in haemorrhagic stroke."

        captured_prompts = []

        def fake_tce(prompt: str):
            captured_prompts.append(prompt)
            return 0.42

        engine.temperature_corrected_entropy = fake_tce
        result = engine.epistemic_certainty_entropy(claim)

        assert result == 0.42
        assert len(captured_prompts) == 1
        # Must NOT have received the raw claim verbatim as the full prompt
        assert captured_prompts[0] != claim
        # Must contain yes/no instruction
        assert "Yes or No" in captured_prompts[0]
        # Must embed the claim inside the prompt
        assert claim in captured_prompts[0]

    def test_passes_context_chunks_into_prompt(self):
        """Context chunks from RAG must appear in the verification prompt."""
        engine = make_engine()
        claim = "Beta-blockers reduce post-MI mortality."
        chunks = ["Beta-blockers shown to reduce mortality in RCTs.", "Contraindicated in asthma."]

        captured = []

        def fake_tce(prompt: str):
            captured.append(prompt)
            return 0.18

        engine.temperature_corrected_entropy = fake_tce
        engine.epistemic_certainty_entropy(claim, context_chunks=chunks)

        assert "Beta-blockers shown to reduce mortality in RCTs." in captured[0]
        assert "Contraindicated in asthma." in captured[0]

    def test_returns_none_when_ollama_fails(self):
        """If temperature_corrected_entropy returns None, propagate None."""
        engine = make_engine()
        engine.temperature_corrected_entropy = lambda prompt: None
        result = engine.epistemic_certainty_entropy("any claim")
        assert result is None

    def test_returns_float_on_success(self):
        engine = make_engine()
        engine.temperature_corrected_entropy = lambda prompt: 0.693
        result = engine.epistemic_certainty_entropy("some clinical claim")
        assert isinstance(result, float)
        assert result == pytest.approx(0.693)

    def test_no_context_still_produces_valid_entropy(self):
        """None context should not error; prompt should still include yes/no."""
        engine = make_engine()
        engine.temperature_corrected_entropy = lambda prompt: 0.35
        result = engine.epistemic_certainty_entropy("claim", context_chunks=None)
        assert result == pytest.approx(0.35)


# ── Integration: prompt signal correctness rationale ─────────────────────────

class TestEpistemicSignalRationale:
    """
    These tests document WHY the yes/no prompt is the correct signal.
    They are documentation-as-tests, not behaviour assertions per se.
    """

    def test_verification_prompt_is_closed_not_open_ended(self):
        """
        An open-ended prompt like 'Chest pain radiating to left arm suggests ...'
        has high entropy because the model can continue with anything.
        A yes/no prompt collapses the first-token distribution to {Yes, No},
        making entropy a true measure of binary epistemic certainty.
        """
        open_claim = "Chest pain radiating to left arm"
        prompt = EntropyEngine._build_verification_prompt(open_claim)

        # The prompt must NOT be the same as the raw claim
        assert prompt != open_claim
        # Must constrain the first token
        assert "Yes or No only" in prompt

    def test_low_entropy_means_high_confidence(self):
        """
        When the model is confident (P(Yes) -> 1), entropy -> 0.
        SaturationDetector theta=0.25 will fire when all frontier nodes are below it.
        This test documents the semantic meaning of the entropy values.
        """
        # ln(2) ≈ 0.693 nats = maximum binary uncertainty (50/50 Yes/No split)
        import math
        max_binary_entropy = math.log(2)
        saturation_theta = 0.25

        assert saturation_theta < max_binary_entropy, (
            "Saturation theta must be well below ln(2) so we stop only when "
            "the model is genuinely confident, not when it's at 50/50."
        )
