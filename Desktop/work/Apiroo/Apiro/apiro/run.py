"""
apiro/run.py
------------
Entry point for Phase 2 traversal.

USAGE:
  python -m apiro.run --case synthetic_case_1.json
  python -m apiro.run --case synthetic_case_1.json --max-depth 6 --real-entropy

STUB vs REAL components:
  By default everything uses stubs so this runs without API keys or model download.
  Pass --real-entropy to use the live EntropyEngine (requires Ollama running).
  Comments marked "SWAP POINT" show exactly what to replace for full integration.
"""

import argparse
import json
import logging
import os
import sys

from apiro.graph.belief_graph import BeliefGraph
from apiro.graph.node import Node
from apiro.graph.expander import NodeExpander, StubEntropyEngine, StubChromaClient
from apiro.graph.saturation import SaturationDetector
from apiro.graph.rabbit_hole import RabbitHoleDetector
from apiro.graph.traversal import ApiroTraversal
from apiro.graph.stub_llm import StubLLMClient, CyclingStubLLMClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_case(case_path: str) -> dict:
    """Load a synthetic case JSON. Looks in data/ if not an absolute path."""
    if not os.path.isabs(case_path):
        base = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            case_path,
            os.path.join(base, "..", "data", case_path),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                case_path = candidate
                break

    logger.info(f"Loading case: {case_path}")
    with open(case_path) as f:
        return json.load(f)


def build_seed_nodes(case_data: dict) -> list[Node]:
    """Convert the JSON seed_nodes list into Node objects."""
    nodes = []
    for s in case_data["seed_nodes"]:
        nodes.append(Node(
            id=s["id"],
            claim=s["claim"],
            entropy_score=s["entropy"],
            domain=s["domain"],
            depth=s.get("depth", 0),
        ))
    return nodes


def build_components(case_id: str, use_real_entropy: bool = False, use_cycling_llm: bool = False):
    """
    Instantiate all Phase 2 components.

    SWAP POINTS:
      - StubEntropyEngine  → from apiro.entropy.engine import EntropyEngine  # REAL
      - StubChromaClient   → import chromadb; client = chromadb.Client()     # REAL
      - StubLLMClient      → OllamaLLMClient / AnthropicLLMClient            # REAL
      - ContradictionDetector is separately available — requires model download
    """
    # ── Entropy engine ────────────────────────────────────────────────────────
    if use_real_entropy:
        # SWAP POINT: real EntropyEngine from Phase 1
        from apiro.entropy.engine import EntropyEngine

        class _EntropyAdapter:
            """Adapter: wraps EntropyEngine.epistemic_certainty_entropy() as .compute().

            Uses the correct yes/no verification prompt so that entropy measures
            model uncertainty at the clinical decision boundary, not open-ended
            generation diversity.
            """
            def __init__(self):
                self._engine = EntropyEngine()

            def compute(self, claim: str, context_chunks=None) -> float:
                result = self._engine.epistemic_certainty_entropy(claim, context_chunks)
                return result if result is not None else 0.5

        entropy_engine = _EntropyAdapter()
        logger.info("Using real EntropyEngine (Ollama required)")
    else:
        entropy_engine = StubEntropyEngine()
        logger.info("Using StubEntropyEngine (no Ollama needed)")

    # ── ChromaDB client ───────────────────────────────────────────────────────
    # SWAP POINT: replace StubChromaClient with a real chromadb.Client()
    chroma_client = StubChromaClient()

    # ── LLM client ────────────────────────────────────────────────────────────
    if use_cycling_llm or "case_2" in case_id:
        llm_client = CyclingStubLLMClient()
        logger.info("Using CyclingStubLLMClient (triggers rabbit hole for case_2)")
    else:
        llm_client = StubLLMClient()

    # ── Contradiction detector ─────────────────────────────────────────────────
    # Full detector downloads MiniLM (~330MB) on first run.
    # We try to load it; fall back to a simple string-match stub if unavailable.
    try:
        from apiro.graph.contradiction import ContradictionDetector
        contradiction = ContradictionDetector()
    except Exception as e:
        logger.warning(f"Could not load ContradictionDetector ({e}). Using stub.")
        contradiction = _StubContradictionDetector()

    expander = NodeExpander(
        entropy_engine=entropy_engine,
        chroma_client=chroma_client,
        llm_client=llm_client,
        contradiction_detector=contradiction,
    )

    saturation  = SaturationDetector(theta=0.25, window=5, max_variance=0.04)
    rabbit_hole = RabbitHoleDetector(min_depth=3, reversal_window=4)

    traversal = ApiroTraversal(
        expander=expander,
        saturation=saturation,
        rabbit_hole=rabbit_hole,
        contradiction=contradiction,
    )

    return traversal, saturation


class _StubContradictionDetector:
    """Simple string-matching fallback when MiniLM cannot be loaded."""

    def check(self, claim_a: str, claim_b: str):
        from dataclasses import dataclass

        @dataclass
        class R:
            label: str
            score: float
            negation_detected: bool

        a, b = claim_a.lower(), claim_b.lower()
        if "aspirin" in a and "aspirin" in b and (
            "contraindicated" in a or "contraindicated" in b
        ):
            return R("contradiction", 0.91, False)
        return R("neutral", 0.55, False)


def main():
    parser = argparse.ArgumentParser(description="APIRO Phase 2 traversal runner")
    parser.add_argument("--case",         required=True,       help="Path to synthetic case JSON")
    parser.add_argument("--max-depth",    type=int, default=8, help="Max traversal depth")
    parser.add_argument("--log-dir",      default="data",      help="Directory for traversal logs")
    parser.add_argument("--output-dir",   default="data",      help="Directory for graph JSON output")
    parser.add_argument("--cycling-llm",  action="store_true", help="Use cycling LLM stub (rabbit hole test)")
    parser.add_argument("--real-entropy", action="store_true", help="Use real EntropyEngine (Ollama required)")
    args = parser.parse_args()

    case_data = load_case(args.case)
    case_id   = case_data.get("case_id", "unknown")
    logger.info(f"Case: {case_id} — {case_data.get('description', '')}")

    seed_nodes = build_seed_nodes(case_data)
    logger.info(f"Seed nodes: {len(seed_nodes)}")

    traversal, _ = build_components(case_id, use_real_entropy=args.real_entropy, use_cycling_llm=args.cycling_llm)
    traversal.log_dir = args.log_dir

    graph  = BeliefGraph()
    result = traversal.run(
        seed_nodes=seed_nodes,
        graph=graph,
        max_depth=args.max_depth,
        case_name=case_id,
    )

    # Export graph JSON
    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, f"graph_{case_id}.json")
    graph.export_json(path=output_path)

    print("\n" + "=" * 60)
    print(f"  APIRO Phase 2 — {case_id}")
    print("=" * 60)
    print(f"  Stop reason:     {result.stop_reason}")
    print(f"  Nodes:           {result.total_nodes}")
    print(f"  Edges:           {result.total_edges}")
    print(f"  Rabbit holes:    {result.rabbit_hole_count}")
    print(f"  Contradictions:  {result.contradiction_count}")
    print(f"  Duration:        {result.duration_seconds}s")
    print(f"  Graph JSON:      {output_path}")
    print(f"  Traversal log:   {args.log_dir}/traversal_log_{case_id}.jsonl")
    print("=" * 60 + "\n")

    return result


if __name__ == "__main__":
    main()
