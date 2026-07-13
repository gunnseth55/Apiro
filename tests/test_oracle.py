"""
tests/test_oracle.py — Unit tests for HypothesisOracle.

Covers two things:
  1. _parse / _parse_json / _parse_lines — canned-string parsing tests,
     no Ollama server or ChromaDB corpus required.
  2. generate()'s retry/backoff logic — _call_llm is mocked (via
     pytest-mock's `mocker` fixture) so these run instantly with no real
     LLM, and time.sleep is patched so backoff delays don't slow down
     the suite.

Requires pytest-mock (`pip install pytest-mock`) for the `mocker` fixture
used in TestRetryLogic.

Run with:
    pytest tests/test_oracle.py -v
"""

import pytest

from apiro.hypothesis.oracle import HypothesisOracle
from apiro.patient.context import PatientContext


class TestParseJSON:
    """Primary path: model returns well-formed JSON as instructed."""

    def test_clean_json(self):
        raw = '{"diagnoses": ["Acute cholecystitis", "Acute pancreatitis", "Peptic ulcer disease"]}'
        result = HypothesisOracle._parse(raw, n=3)
        assert result == ["Acute cholecystitis", "Acute pancreatitis", "Peptic ulcer disease"]

    def test_preserves_order(self):
        raw = '{"diagnoses": ["First", "Second", "Third"]}'
        result = HypothesisOracle._parse(raw, n=3)
        assert result[0] == "First"
        assert result[-1] == "Third"

    def test_truncates_to_n(self):
        raw = '{"diagnoses": ["Diagnosis A", "Diagnosis B", "Diagnosis C", "Diagnosis D", "Diagnosis E"]}'
        result = HypothesisOracle._parse(raw, n=3)
        assert len(result) == 3
        assert result == ["Diagnosis A", "Diagnosis B", "Diagnosis C"]

    def test_deduplicates_case_insensitive(self):
        raw = '{"diagnoses": ["Acute MI", "acute mi", "ACUTE MI", "Pulmonary embolism"]}'
        result = HypothesisOracle._parse(raw, n=5)
        assert result == ["Acute MI", "Pulmonary embolism"]

    def test_drops_too_short_entries(self):
        raw = '{"diagnoses": ["Acute cholecystitis", "ok", "MI", "Sepsis"]}'
        result = HypothesisOracle._parse(raw, n=5)
        # "ok" (len 2) dropped; "MI" (len 2) also dropped by the > 2 length rule
        assert "ok" not in result
        assert "MI" not in result
        assert "Acute cholecystitis" in result
        assert "Sepsis" in result

    def test_wrapped_in_markdown_fence_fails_gracefully(self):
        # Models sometimes ignore format:"json" and wrap in ```json fences
        # despite instructions not to. This should NOT crash — it should
        # fail json.loads() and fall through to the line parser instead.
        raw = '```json\n{"diagnoses": ["Acute MI"]}\n```'
        result = HypothesisOracle._parse(raw, n=3)
        # Whatever it returns, it must not raise, and should not silently
        # include the markdown fence characters as a "diagnosis".
        assert all("`" not in item for item in result)


class TestParseLinesFallback:
    """Fallback path: model ignores the JSON instruction entirely."""

    def test_falls_back_on_plain_text(self):
        raw = "1. Acute cholecystitis\n2. Acute pancreatitis (most likely)\n- Peptic ulcer disease\n"
        result = HypothesisOracle._parse(raw, n=3)
        assert result == ["Acute cholecystitis", "Acute pancreatitis", "Peptic ulcer disease"]

    def test_fallback_strips_bullets_and_parentheticals(self):
        raw = "* Sepsis (high confidence)\n* DKA\n"
        result = HypothesisOracle._parse(raw, n=2)
        assert result == ["Sepsis", "DKA"]

    def test_fallback_rejects_leftover_json_noise(self):
        # Regression test for the bug caught during manual testing: if the
        # model used a wrong key name ("differential" instead of
        # "diagnoses"), _parse_json correctly returns [], but the fallback
        # line-parser used to treat the whole raw JSON blob as one garbage
        # "diagnosis" line. It must now return [] instead.
        raw = '{"differential": ["Acute cholecystitis"]}'
        result = HypothesisOracle._parse(raw, n=3)
        assert result == []

    def test_fallback_never_includes_brace_or_quote_characters(self):
        raw = '{"diagnoses": [oops malformed'
        result = HypothesisOracle._parse(raw, n=3)
        assert all(not any(ch in item for ch in '{}[]"') for item in result)


class TestEdgeCases:
    def test_empty_string_returns_empty_list(self):
        assert HypothesisOracle._parse("", n=3) == []

    def test_diagnoses_key_wrong_type_falls_back(self):
        # "diagnoses" present but not a list -> _parse_json bails -> fallback
        raw = '{"diagnoses": "Acute MI"}'
        result = HypothesisOracle._parse(raw, n=3)
        assert result == []  # fallback line-parser also rejects due to quote chars

    def test_non_string_items_in_diagnoses_are_skipped(self):
        raw = '{"diagnoses": ["Acute MI", 42, null, "Sepsis"]}'
        result = HypothesisOracle._parse(raw, n=5)
        assert result == ["Acute MI", "Sepsis"]

    def test_not_a_json_object_falls_back(self):
        # Valid JSON, but a list instead of an object with "diagnoses" key
        raw = '["Acute MI", "Sepsis"]'
        result = HypothesisOracle._parse(raw, n=3)
        assert result == []  # falls back, and line-parser rejects due to brackets/quotes


class TestRetryLogic:
    """
    Tests for generate()'s retry/backoff behavior. _call_llm is mocked so
    these run instantly with no real Ollama server, and time.sleep is
    patched so backoff delays don't actually slow the test suite down.
    """

    def _make_context(self):
        return PatientContext(
            chief_complaint="chest pain",
            age=58,
            gender="male",
            symptoms=["diaphoresis"],
            labs={"troponin": "elevated"},
            imaging=[],
            history=[],
        )

    def test_succeeds_first_try_no_retry_needed(self, mocker):
        oracle = HypothesisOracle(max_retries=2, retry_backoff_seconds=0.01)
        mock_call = mocker.patch.object(
            oracle, "_call_llm", return_value='{"diagnoses": ["Acute MI", "Aortic dissection"]}'
        )
        mock_sleep = mocker.patch("apiro.hypothesis.oracle.time.sleep")

        result = oracle.generate(self._make_context(), n=2)

        assert result == ["Acute MI", "Aortic dissection"]
        assert mock_call.call_count == 1
        mock_sleep.assert_not_called()

    def test_recovers_after_one_transient_failure(self, mocker):
        oracle = HypothesisOracle(max_retries=2, retry_backoff_seconds=0.01)
        mock_call = mocker.patch.object(
            oracle,
            "_call_llm",
            side_effect=["", '{"diagnoses": ["Acute MI"]}'],
        )
        mock_sleep = mocker.patch("apiro.hypothesis.oracle.time.sleep")

        result = oracle.generate(self._make_context(), n=1)

        assert result == ["Acute MI"]
        assert mock_call.call_count == 2
        mock_sleep.assert_called_once()  # backed off exactly once before retry 2

    def test_recovers_from_unparseable_response_not_just_network_failure(self, mocker):
        # Simulates the HTTP call "succeeding" but returning garbage that
        # parses to nothing — this must be treated as a failure and retried,
        # not silently accepted as "success with zero results".
        oracle = HypothesisOracle(max_retries=1, retry_backoff_seconds=0.01)
        mock_call = mocker.patch.object(
            oracle,
            "_call_llm",
            side_effect=['{"diagnoses": []}', '{"diagnoses": ["Sepsis"]}'],
        )
        mocker.patch("apiro.hypothesis.oracle.time.sleep")

        result = oracle.generate(self._make_context(), n=1)

        assert result == ["Sepsis"]
        assert mock_call.call_count == 2

    def test_returns_empty_list_after_exhausting_all_retries(self, mocker):
        oracle = HypothesisOracle(max_retries=2, retry_backoff_seconds=0.01)
        mock_call = mocker.patch.object(oracle, "_call_llm", return_value="")
        mock_sleep = mocker.patch("apiro.hypothesis.oracle.time.sleep")

        result = oracle.generate(self._make_context(), n=8)

        assert result == []
        # max_retries=2 -> 3 total attempts
        assert mock_call.call_count == 3
        # backoff happens before retry 2 and retry 3, not after the final failure
        assert mock_sleep.call_count == 2

    def test_backoff_delay_doubles_each_attempt(self, mocker):
        oracle = HypothesisOracle(max_retries=2, retry_backoff_seconds=1.0)
        mocker.patch.object(oracle, "_call_llm", return_value="")
        mock_sleep = mocker.patch("apiro.hypothesis.oracle.time.sleep")

        oracle.generate(self._make_context(), n=8)

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0]

    def test_zero_retries_means_exactly_one_attempt(self, mocker):
        oracle = HypothesisOracle(max_retries=0, retry_backoff_seconds=0.01)
        mock_call = mocker.patch.object(oracle, "_call_llm", return_value="")
        mock_sleep = mocker.patch("apiro.hypothesis.oracle.time.sleep")

        result = oracle.generate(self._make_context(), n=8)

        assert result == []
        assert mock_call.call_count == 1
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])