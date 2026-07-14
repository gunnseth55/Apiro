#!/usr/bin/env python3
"""
scripts/investigate.py
======================
CLI runner for the Apiro AI Detective using the Hypothesis-Testing Engine.

Usage:
  python scripts/investigate.py --findings "49yo female, dyspnea, history of breast cancer"
"""
import argparse
import sys
import time
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("investigate")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def build_components():
    import requests
    from apiro.corpus.embedder import Embedder
    from apiro.graph.traversal import HypothesisTestingTraversal
    from apiro.hypothesis.oracle import HypothesisOracle
    from apiro.hypothesis.evidence_matcher import EvidenceMatcher
    from apiro.hypothesis.bayesian_scorer import BayesianScorer
    from apiro.config import OLLAMA_BASE_URL, PRIMARY_MODEL

    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        r.raise_for_status()
    except Exception as e:
        print(f"\n❌  Ollama not reachable at {OLLAMA_BASE_URL}: {e}")
        print("    Start it with:  ollama serve")
        sys.exit(1)

    embedder = Embedder()
    doc_count = embedder.count
    if doc_count == 0:
        print("\n❌  ChromaDB corpus is empty.")
        print("    Build it with:  python scripts/build_corpus.py")
        sys.exit(1)

    class _ChromaAdapter:
        def __init__(self, emb: Embedder):
            self._emb = emb
        def query(self, collection_name: str = "", query_texts: list = None, n_results: int = 6, where: dict | None = None) -> dict:
            query_texts = query_texts or []
            text = query_texts[0] if query_texts else ""
            results = self._emb.query(text, n_results=n_results, where=where)
            return {"documents": [[r["text"] for r in results]]}

    chroma_adapter = _ChromaAdapter(embedder)

    from apiro.run import OllamaLLMClient
    llm_client = OllamaLLMClient(url=OLLAMA_BASE_URL, model=PRIMARY_MODEL)

    oracle = HypothesisOracle(model=PRIMARY_MODEL, ollama_url=OLLAMA_BASE_URL)
    matcher = EvidenceMatcher(chroma_client=chroma_adapter)
    scorer = BayesianScorer()

    trav = HypothesisTestingTraversal(
        oracle=oracle,
        matcher=matcher,
        scorer=scorer,
        n_hypotheses=10,
        enrich_top_k=0
    )

    return trav, doc_count

def print_report(result, elapsed: float) -> None:
    print("\n+" + "-" * 58 + "+")
    print("|" + "    APIRO DIFFERENTIAL DIAGNOSIS REPORT".center(58) + "|")
    print("+" + "-" * 58 + "+")

    print(f"\n  Time taken:             {elapsed:.1f} seconds")
    if result.stop_reason:
        print(f"  Stop reason:            {result.stop_reason}")

    print("\n  [ PATIENT CONTEXT ]")
    print(f"  {result.patient_context.summary()}")

    print("\n  [ TOP DIFFERENTIAL DIAGNOSES ]")
    if not result.synthesis:
        print("  No viable hypotheses generated.")
    else:
        for i, dx in enumerate(result.synthesis, 1):
            print(f"  {i}. {dx}")

    if result.ranked_hypotheses:
        print("\n  [ EVIDENCE SCORING DETAILS ]")
        for r in result.ranked_hypotheses[:5]:
            print(f"  - {r.hypothesis[:60]:60s} | Rank: {r.rank} | Score: {r.final_score:.2f} | Matched: {len(r.matched_findings)}")

    print("\n+" + "-" * 58 + "+\n")

def main():
    parser = argparse.ArgumentParser(
        description="Apiro AI Detective — free-text clinical findings → differential diagnosis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--findings", "-f",
        type=str,
        default=None,
        help="Free-text clinical findings. If omitted, enters interactive mode.",
    )
    parser.add_argument(
        "--max-depth", type=int, default=5,
        help="Max traversal depth (legacy flag, kept for compat).",
    )
    parser.add_argument(
        "--real-entropy", action="store_true",
        help="Legacy flag (ignored).",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Optional path to write the belief graph JSON (legacy flag).",
    )
    args = parser.parse_args()

    if args.findings:
        raw_findings = args.findings
    else:
        print("\n" + "=" * 60)
        print("    APIRO -- AI DIAGNOSTIC DETECTIVE")
        print("=" * 60)
        print("  Enter clinical findings (symptoms, labs, vitals, history).")
        print("  Press Enter twice when done.\n")
        lines = []
        try:
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
        except EOFError:
            pass
        raw_findings = "\n".join(lines)

    if not raw_findings.strip():
        print("[-] No findings provided. Exiting.")
        sys.exit(1)

    print("\n[*] Initialising Apiro components...")
    traversal, doc_count = build_components()
    print(f"[+] Components ready. Corpus: {doc_count:,} documents.\n")

    print(f"\n[*] Apiro is investigating...")
    t0 = time.time()
    
    from apiro.graph.belief_graph import BeliefGraph
    graph = BeliefGraph()
    result = traversal.run(
        vignette=raw_findings,
        graph=graph,
        max_depth=args.max_depth,
        case_name="investigate",
    )
    elapsed = time.time() - t0

    print_report(result, elapsed)

if __name__ == "__main__":
    main()
