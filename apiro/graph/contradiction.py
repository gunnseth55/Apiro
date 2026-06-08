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
"""

import re
from dataclasses import dataclass
from typing import Literal

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

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

# Score threshold above which we trust a contradiction label
CONTRADICTION_THRESHOLD = 0.85


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
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.eval()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        print(f"[ContradictionDetector] Running on {self.device}")

    def _has_negation(self, text: str) -> bool:
        """Returns True if NegEx pattern fires on this text."""
        return bool(NEGEX_PATTERNS.search(text))

    def check(self, claim_a: str, claim_b: str) -> NLIResult:
        """
        Run NLI inference on (claim_a, claim_b).

        The cross-encoder sees both claims concatenated as:
            [CLS] claim_a [SEP] claim_b [SEP]

        Returns an NLIResult with label, confidence score, and negation flag.
        """
        negation_detected = self._has_negation(claim_a) or self._has_negation(claim_b)

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

        return NLIResult(
            label=LABEL_MAPPING[best_idx],
            score=float(probs[best_idx]),
            negation_detected=negation_detected,
        )

    def check_batch(self, pairs: list[tuple[str, str]]) -> list[NLIResult]:
        """
        Batch version for efficiency when checking many pairs at once.
        Reduces GPU round-trips when the graph is large.
        """
        if not pairs:
            return []

        claims_a = [p[0] for p in pairs]
        claims_b = [p[1] for p in pairs]

        negations = [
            self._has_negation(a) or self._has_negation(b)
            for a, b in pairs
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
            logits = self.model(**inputs).logits  # shape: (batch, 3)

        probs = torch.softmax(logits, dim=-1)
        best_indices = probs.argmax(dim=-1).tolist()

        return [
            NLIResult(
                label=LABEL_MAPPING[idx],
                score=float(probs[i][idx]),
                negation_detected=negations[i],
            )
            for i, idx in enumerate(best_indices)
        ]
