"""
apiro/run.py
------------
Entry point for a single-case Apiro traversal using all real components.

USAGE:
  python -m apiro.run --case data/synthetic_case_1.json
  python -m apiro.run --case data/synthetic_case_1.json --max-depth 6

All components are REAL (no stubs):
  - EntropyEngine   : Ollama / llama3.1:8b
  - ChromaDB        : local apiro_corpus (768-dim, all-mpnet-base-v2)
  - LLM             : Ollama / llama3.1:8b
  - Contradiction   : cross-encoder/nli-MiniLM2-L6-H768

Requirements:
  - Ollama running: `ollama serve`
  - Corpus built:   `python scripts/build_corpus.py`
"""

import argparse
import json
import logging
import os
import sys
import requests

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apiro.config import (
    OLLAMA_BASE_URL,
    PRIMARY_MODEL,
    DEFAULT_THETA,
    SATURATION_WINDOW,
    SATURATION_MAX_VARIANCE,
    RABBIT_HOLE_MIN_DEPTH,
    RABBIT_HOLE_REVERSAL_WINDOW,
    MAX_TRAVERSAL_DEPTH,
)
from apiro.graph.belief_graph import BeliefGraph
from apiro.graph.node import Node

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)-20s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Real OllamaLLMClient ──────────────────────────────────────────────────────

class OllamaLLMClient:
    """Thin wrapper around the Ollama REST API for text generation."""

    def __init__(self, url: str = OLLAMA_BASE_URL, model: str = PRIMARY_MODEL, timeout: int = 45):
        self.url     = url
        self.model   = model
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        payload = {
            "model":  self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 180},
        }
        # Try once, then retry once more before giving up; keeps stalls bounded.
        for attempt in range(2):
            try:
                resp = requests.post(f"{self.url}/api/generate", json=payload, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json().get("response", "")
            except Exception as e:
                if attempt == 1:
                    raise
                import logging
                logging.getLogger(__name__).warning(f"[OllamaLLMClient] Attempt {attempt+1} failed ({e}), retrying...")
        return ""

    def chat(self, prompt: str) -> str:
        return self.generate(prompt)


# ── ChromaDB adapter (mirrors run_phase3_eval.py) ────────────────────────────

class _ChromaAdapter:
    """Wraps Embedder.query() into NodeExpander's expected interface."""

    def __init__(self, embedder):
        self._emb = embedder

    def query(
        self,
        collection_name: str = "",
        query_texts: list = None,
        n_results: int = 6,
        where: dict | None = None,
    ) -> dict:
        query_texts = query_texts or []
        text    = query_texts[0] if query_texts else ""
        results = self._emb.query(text, n_results=n_results, where=where)
        docs    = [r["text"] for r in results]
        return {"documents": [docs]}


# ── Component builder ─────────────────────────────────────────────────────────

def build_components(mode: str = "classic"):
    """Instantiate all real Apiro components. Exits if prerequisites are missing.

    Args:
        mode: 'classic' (original generative expansion) or
              'hypothesis' (new hypothesis-testing inference engine).
    """
    from apiro.graph.expander      import NodeExpander
    from apiro.graph.saturation    import SaturationDetector
    from apiro.graph.rabbit_hole   import RabbitHoleDetector
    from apiro.graph.contradiction import ContradictionDetector
    from apiro.entropy.engine      import EntropyEngine
    from apiro.corpus.embedder     import Embedder
    from apiro.graph.traversal     import ApiroTraversal, HypothesisTestingTraversal

    # ── Ollama check ──────────────────────────────────────────────────────────
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        r.raise_for_status()
        logger.info(f"[OK] Ollama reachable — model: {PRIMARY_MODEL}")
    except Exception as e:
        logger.error(f"[FAIL] Ollama not reachable at {OLLAMA_BASE_URL}: {e}")
        sys.exit(1)

    # ── ChromaDB via Embedder ─────────────────────────────────────────────────
    embedder  = Embedder()
    doc_count = embedder.count
    if doc_count == 0:
        logger.error("[FAIL] ChromaDB corpus is empty. Run: python scripts/build_corpus.py")
        sys.exit(1)
    logger.info(f"[OK] ChromaDB 'apiro_corpus': {doc_count:,} docs.")

    chroma_adapter  = _ChromaAdapter(embedder)
    entropy_engine  = EntropyEngine(model=PRIMARY_MODEL, ollama_url=OLLAMA_BASE_URL)
    llm_client      = OllamaLLMClient()
    contradiction   = ContradictionDetector()

    expander = NodeExpander(
        entropy_engine=entropy_engine,
        chroma_client=chroma_adapter,
        llm_client=llm_client,
        contradiction_detector=contradiction,
    )
    saturation  = SaturationDetector(
        theta=DEFAULT_THETA,
        window=SATURATION_WINDOW,
        max_variance=SATURATION_MAX_VARIANCE,
    )
    rabbit_hole = RabbitHoleDetector(
        min_depth=RABBIT_HOLE_MIN_DEPTH,
        reversal_window=RABBIT_HOLE_REVERSAL_WINDOW,
    )
    traversal = ApiroTraversal(
        expander=expander,
        saturation=saturation,
        rabbit_hole=rabbit_hole,
        contradiction=contradiction,
    )

    if mode == "hypothesis":
        from apiro.hypothesis.oracle          import HypothesisOracle
        from apiro.hypothesis.evidence_matcher import EvidenceMatcher
        from apiro.hypothesis.bayesian_scorer  import BayesianScorer

        oracle  = HypothesisOracle(model=PRIMARY_MODEL, ollama_url=OLLAMA_BASE_URL)
        matcher = EvidenceMatcher(chroma_client=chroma_adapter)
        scorer  = BayesianScorer()
        ht_traversal = HypothesisTestingTraversal(
            oracle=oracle,
            matcher=matcher,
            scorer=scorer,
            expander=expander,
            saturation=saturation,
            rabbit_hole=rabbit_hole,
            contradiction=contradiction,
        )
        return ht_traversal, expander, embedder

    return traversal, expander, embedder


# ── Case loader ───────────────────────────────────────────────────────────────

def load_case(case_path: str) -> dict:
    """Load a case JSON file. Looks in data/ if not an absolute path."""
    if not os.path.isabs(case_path):
        candidates = [
            case_path,
            str(ROOT / "data" / case_path),
        ]
        for c in candidates:
            if os.path.exists(c):
                case_path = c
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
            entropy_score=s.get("entropy", 0.693),
            domain=s.get("domain", "pathophysiology"),
            depth=s.get("depth", 0),
        ))
    return nodes


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="APIRO single-case traversal (real components)")
    parser.add_argument("--case",       required=True,                   help="Path to case JSON")
    parser.add_argument("--max-depth",  type=int, default=MAX_TRAVERSAL_DEPTH, help="Max traversal depth")
    parser.add_argument("--log-dir",    default="data",                  help="Directory for traversal logs")
    parser.add_argument("--output-dir", default="data",                  help="Directory for graph JSON output")
    parser.add_argument(
        "--mode",
        choices=["classic", "hypothesis"],
        default="hypothesis",
        help="Traversal mode: 'classic' (generative BFS) or 'hypothesis' (new inference engine)"
    )
    args = parser.parse_args()

    case_data  = load_case(args.case)
    case_id    = case_data.get("case_id", "unknown")
    logger.info(f"Case: {case_id} — {case_data.get('description', '')}")

    vignette = case_data.get("vignette", "")
    seed_nodes = build_seed_nodes(case_data)
    logger.info(f"Seed nodes: {len(seed_nodes)} | Mode: {args.mode}")

    traversal, _, _ = build_components(mode=args.mode)
    traversal.log_dir = args.log_dir

    graph  = BeliefGraph()
    if args.mode == "hypothesis":
        result = traversal.run(
            vignette=vignette,
            case_name=case_id,
            graph=graph,
        )
    else:
        result = traversal.run(
            seed_nodes=seed_nodes,
            graph=graph,
            max_depth=args.max_depth,
            case_name=case_id,
            vignette=vignette,
        )

    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, f"graph_{case_id}.json")
    graph.export_json(path=output_path)

    print("\n" + "=" * 60)
    print(f"  APIRO — {case_id}")
    print("=" * 60)
    print(f"  Stop reason:     {result.stop_reason}")
    print(f"  Nodes:           {result.total_nodes}")
    print(f"  Rabbit holes:    {result.rabbit_hole_count}")
    print(f"  Contradictions:  {result.contradiction_count}")
    print(f"  Duration:        {result.duration_seconds}s")
    print(f"  Differential:    {result.synthesis}")
    print(f"  Graph JSON:      {output_path}")
    print("=" * 60 + "\n")

    return result


if __name__ == "__main__":
    main()
