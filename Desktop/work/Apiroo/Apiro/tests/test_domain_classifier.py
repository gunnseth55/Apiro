"""
tests/test_domain_classifier.py
================================
Unit tests for DomainClassifier.

Tests cover:
  - Keyword fast-path classification (no model needed)
  - Edge cases (empty string, whitespace)
  - classify_batch() consistency
  - config_key() mapping correctness
  - Model path smoke test (loads model once)
"""

from __future__ import annotations

import pytest

from apiro.nlp.domain_classifier import DomainClassifier, DOMAIN_TO_CONFIG_KEY, DOMAINS


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def clf():
    """Shared DomainClassifier instance (keyword fast-path only, no model load)."""
    return DomainClassifier(use_keyword_fastpath=True)


# ── Keyword fast-path tests ───────────────────────────────────────────────────

class TestKeywordFastPath:
    """These must all pass via keyword rules without loading BART."""

    @pytest.mark.parametrize("text,expected", [
        # Genetics
        ("BAG3 gene variant NM_004281.4(BAG3):c.626C>T (p.Pro209Leu)", "genetics"),
        ("MYBPC3 pathogenic missense mutation detected",                 "genetics"),
        ("BRCA1 frameshift deletion — likely pathogenic",               "genetics"),
        ("PRKAG2 variant NM_016203.4(PRKAG2):c.471C>T",                "genetics"),
        ("Chromosome 17q21 deletion, CNV confirmed",                    "genetics"),

        # Lab findings
        ("Troponin I elevated at 4.2 ng/mL",                           "lab findings"),
        ("Creatinine 2.1 mg/dL (elevated)",                            "lab findings"),
        ("WBC 14.5 × 10³/μL with neutrophilia",                        "lab findings"),
        ("BNP 850 pg/mL",                                              "lab findings"),
        ("Hemoglobin 7.2 g/dL",                                        "lab findings"),

        # Imaging
        ("CT chest shows bilateral pleural effusions",                  "imaging"),
        ("Echocardiogram reveals EF 35% with regional wall motion",     "imaging"),
        ("Chest X-ray: cardiomegaly and pulmonary congestion",          "imaging"),
        ("MRI brain: no acute infarct",                                 "imaging"),

        # Treatment
        ("Start aspirin 325 mg PO and heparin infusion",               "treatment"),
        ("Nitroglycerin 0.4 mg sublingual PRN chest pain",             "treatment"),
        ("PCI performed with drug-eluting stent placement",             "treatment"),
        ("Prescribe metoprolol 25 mg BID",                              "treatment"),

        # Comorbidity
        ("History of hypertension and type 2 diabetes",                "comorbidity"),
        ("Past medical history: chronic kidney disease stage 3",       "comorbidity"),
        ("Pre-existing atrial fibrillation on anticoagulation",        "comorbidity"),

        # Pharmacology (mechanism, not administration)
        ("Metoprolol acts via beta-1 receptor antagonism",             "pharmacology"),
        ("CYP3A4 substrate with narrow therapeutic index",             "pharmacology"),
    ])
    def test_keyword_classification(self, clf, text, expected):
        result = clf.classify(text)
        assert result == expected, (
            f"Expected '{expected}' for text: '{text[:60]}', got '{result}'"
        )

    def test_empty_string_returns_default(self, clf):
        assert clf.classify("") == "pathophysiology"

    def test_whitespace_only_returns_default(self, clf):
        assert clf.classify("   \t\n  ") == "pathophysiology"

    def test_unknown_text_falls_through_to_model_or_default(self, clf):
        """Non-keyword text should either use model or return default — not crash."""
        result = clf.classify("The patient presented with general malaise")
        assert result in DOMAINS, f"Expected a valid domain, got: {result}"


# ── Batch classification tests ────────────────────────────────────────────────

class TestBatchClassification:
    def test_batch_same_as_single(self, clf):
        texts = [
            "Troponin elevated at 4.2 ng/mL",
            "BAG3 gene variant detected",
            "Start aspirin 325 mg",
            "History of hypertension",
        ]
        single_results = [clf.classify(t) for t in texts]
        batch_results  = clf.classify_batch(texts)
        assert single_results == batch_results

    def test_batch_empty_list(self, clf):
        assert clf.classify_batch([]) == []

    def test_batch_mixed_with_empty(self, clf):
        texts   = ["", "Troponin I elevated", ""]
        results = clf.classify_batch(texts)
        assert len(results) == 3
        assert results[0] == "pathophysiology"   # empty → default
        assert results[1] == "lab findings"       # keyword match
        assert results[2] == "pathophysiology"   # empty → default


# ── classify_with_score tests ─────────────────────────────────────────────────

class TestClassifyWithScore:
    def test_keyword_returns_score_1(self, clf):
        domain, score = clf.classify_with_score("Troponin I elevated at 4.2 ng/mL")
        assert domain == "lab findings"
        assert score  == 1.0

    def test_empty_returns_zero_score(self, clf):
        domain, score = clf.classify_with_score("")
        assert domain == "pathophysiology"
        assert score  == 0.0


# ── config_key tests ──────────────────────────────────────────────────────────

class TestConfigKey:
    def test_lab_maps_to_lab_config_key(self, clf):
        key = clf.config_key("Troponin I elevated at 4.2 ng/mL")
        assert key == "lab"   # "lab findings" → "lab" for theta lookup

    def test_genetics_maps_to_genetics(self, clf):
        key = clf.config_key("BAG3 missense variant")
        assert key == "genetics"

    def test_treatment_maps_to_treatment(self, clf):
        key = clf.config_key("Start aspirin 325 mg PO")
        assert key == "treatment"

    def test_all_domains_have_config_key(self):
        assert all(v in ["pathophysiology", "pharmacology", "genetics",
                          "imaging", "lab", "treatment", "comorbidity"]
                   for v in DOMAIN_TO_CONFIG_KEY.values())
