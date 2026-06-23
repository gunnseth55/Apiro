#!/usr/bin/env python3
"""
scripts/run_phase3_eval.py
===========================
Phase 3 evaluation: entropy-first vs breadth-first on CUPCase + VivaBench.

Usage:
    venv/bin/python scripts/run_phase3_eval.py \
        --dataset vivabench \
        --n 10 \
        --specialty Cardiovascular \
        --output data/phase3_results.json

Datasets:
    vivabench  — 990 clinician-validated cases with ICD-10 ground truth
    cupcase    — 3562 rare cases, best for rabbit hole testing

Phase 3 goal: entropy-first outperforms BFS in ≥7/10 cases on path length.
"""

import argparse
import logging
import sys
from pathlib import Path

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)-20s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("phase3_eval")

# ── project root ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── config imports ────────────────────────────────────────────────────────────
from apiro.config import (
    OLLAMA_BASE_URL,
    PRIMARY_MODEL,
    DEFAULT_THETA,
    SATURATION_WINDOW,
    SATURATION_MAX_VARIANCE,
    RABBIT_HOLE_MIN_DEPTH,
    RABBIT_HOLE_REVERSAL_WINDOW,
    MAX_TRAVERSAL_DEPTH,
    MAX_NODES_PER_RUN,
)


def build_components():
    """Initialise all shared Apiro components."""
    import requests
    from apiro.graph.expander import NodeExpander
    from apiro.graph.saturation import SaturationDetector
    from apiro.graph.rabbit_hole import RabbitHoleDetector
    from apiro.graph.contradiction import ContradictionDetector
    from apiro.entropy.engine import EntropyEngine
    from apiro.corpus.embedder import Embedder

    # ── Ollama connectivity check ─────────────────────────────────────────
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        r.raise_for_status()
        logger.info(f"[OK] Ollama reachable — model: {PRIMARY_MODEL}")
    except Exception as e:
        logger.error(f"[FAIL] Ollama not reachable at {OLLAMA_BASE_URL}: {e}")
        sys.exit(1)

    # ── ChromaDB via Embedder (all-mpnet-base-v2, 768-dim) ───────────────
    # IMPORTANT: Do NOT pass a raw chromadb.Collection to NodeExpander.
    # The corpus was built with 768-dim embeddings (all-mpnet-base-v2).
    # A raw collection falls back to ChromaDB's default 384-dim model → mismatch.
    # Embedder.query() encodes the query text into 768-dim first, then queries.
    embedder  = Embedder()
    doc_count = embedder.count
    if doc_count == 0:
        logger.error("[FAIL] ChromaDB collection is empty. Run build_corpus first.")
        sys.exit(1)
    logger.info(f"[OK] ChromaDB 'apiro_corpus': {doc_count:,} docs.")

    class _ChromaAdapter:
        """Wraps Embedder.query() into NodeExpander's expected interface.

        Accepts an optional `where` metadata filter and passes it through
        to Embedder.query() so domain-filtered RAG works end-to-end.
        """
        def __init__(self, emb: Embedder):
            self._emb = emb

        def query(
            self,
            collection_name: str = "",
            query_texts: list = None,
            n_results: int = 6,
            where: dict | None = None,
        ) -> dict:
            query_texts = query_texts or []
            text = query_texts[0] if query_texts else ""
            results = self._emb.query(text, n_results=n_results, where=where)
            docs = [r["text"] for r in results]
            return {"documents": [docs]}

    chroma_adapter = _ChromaAdapter(embedder)

    # ── Build components ──────────────────────────────────────────────────
    entropy_engine = EntropyEngine(model=PRIMARY_MODEL, ollama_url=OLLAMA_BASE_URL)

    class OllamaLLMClient:
        def __init__(self, url, model):
            self.url   = url
            self.model = model
            logger.info(f"[OllamaLLMClient] {model} at {url}")

        def generate(self, prompt: str) -> str:
            import requests as req
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 180,
                },
            }
            resp = req.post(f"{self.url}/api/generate", json=payload, timeout=90)
            resp.raise_for_status()
            return resp.json().get("response", "")

        def chat(self, prompt: str) -> str:
            return self.generate(prompt)

    llm_client = OllamaLLMClient(OLLAMA_BASE_URL, PRIMARY_MODEL)

    expander = NodeExpander(
        entropy_engine=entropy_engine,
        chroma_client=chroma_adapter,
        llm_client=llm_client,
    )
    saturation   = SaturationDetector(
        theta=DEFAULT_THETA,
        window=SATURATION_WINDOW,
        max_variance=SATURATION_MAX_VARIANCE,
    )
    rabbit_hole  = RabbitHoleDetector(
        min_depth=RABBIT_HOLE_MIN_DEPTH,
        reversal_window=RABBIT_HOLE_REVERSAL_WINDOW,
    )
    contradiction = ContradictionDetector()

    return expander, saturation, rabbit_hole, contradiction, entropy_engine, embedder


def main():
    parser = argparse.ArgumentParser(description="Apiro Phase 3 Evaluation")
    parser.add_argument(
        "--dataset",
        choices=["vivabench", "cupcase", "both"],
        default="vivabench",
        help="Which dataset to evaluate on.",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=10,
        help="Number of cases to evaluate per dataset.",
    )
    parser.add_argument(
        "--specialty",
        type=str,
        default=None,
        help="VivaBench specialty filter (e.g. 'Cardiovascular', 'Neurological').",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/phase3_results.json",
        help="Path to write JSON results.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=MAX_TRAVERSAL_DEPTH,
        help=f"Max traversal depth per case (default: {MAX_TRAVERSAL_DEPTH} from config).",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=MAX_NODES_PER_RUN,
        help=f"Max nodes expanded per case (default: {MAX_NODES_PER_RUN} from config).",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  APIRO PHASE 3 EVALUATION")
    logger.info(f"  Dataset: {args.dataset}  |  N: {args.n}  |  MaxDepth: {args.max_depth}")
    logger.info("=" * 60)

    # ── Load components ───────────────────────────────────────────────────
    expander, saturation, rabbit_hole, contradiction, entropy_engine, embedder = build_components()

    # ── Load cases ────────────────────────────────────────────────────────
    from apiro.corpus.clinical_case_adapter import ClinicalCaseAdapter
    from apiro.eval.evaluator import CaseEvaluator

    adapter = ClinicalCaseAdapter()
    all_cases = []

    if args.dataset in ("vivabench", "both"):
        raw = adapter.load_vivabench(n=args.n, specialty=args.specialty)
        logger.info(f"Computing seed entropy for {len(raw)} VivaBench cases (this calls Ollama)...")
        all_cases.extend(adapter.build_cases(raw, entropy_engine=entropy_engine))
        logger.info(f"Loaded {len(raw)} VivaBench cases.")

    if args.dataset in ("cupcase", "both"):
        raw = adapter.load_cupcase(n=args.n)
        logger.info(f"Computing seed entropy for {len(raw)} CUPCase cases (this calls Ollama)...")
        all_cases.extend(adapter.build_cases(raw, entropy_engine=entropy_engine))
        logger.info(f"Loaded {len(raw)} CUPCase cases.")

    logger.info(f"Total eval cases: {len(all_cases)}")

    # ── Run evaluation ────────────────────────────────────────────────────
    evaluator = CaseEvaluator(
        expander=expander,
        saturation=saturation,
        rabbit_hole=rabbit_hole,
        contradiction=contradiction,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
        embedder=embedder,
    )

    summary = evaluator.evaluate_all(
        cases=all_cases,
        output_path=args.output,
    )

    # ── Print final summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  PHASE 3 RESULTS")
    print("=" * 60)
    print(f"  EF wins:   {summary['entropy_first_wins']}/{summary['total_cases']}")
    print(f"  BF wins:   {summary['breadth_first_wins']}/{summary['total_cases']}")
    print(f"  Ties:      {summary['ties']}")
    print(f"  Both miss: {summary['both_miss']}")
    print(f"  EF rate:   {summary['ef_win_rate']:.1%}")
    target = "[PASS] (>=70%)" if summary["target_met"] else "[FAIL] (need >=70%)"
    print(f"  Target:    {target}")
    print(f"  Results:   {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
