#!/usr/bin/env python3
"""
scripts/run_edar_eval.py
=========================
Full 3-way evaluation: Bare LLM vs Standard RAG vs Apiro EDAR
on the 10 PMC cases in data/pmc_cases.json.

Run with:
  PYTHONPATH=. venv/bin/python scripts/run_edar_eval.py --real
"""
import argparse
import functools
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)-20s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("edar_eval")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run_evaluation(real_components: bool):
    cases_path = ROOT / "data" / "pmc_cases.json"
    with open(cases_path) as f:
        cases = json.load(f)

    from apiro.eval.evaluator import _check_synthesis_hit

    if not real_components:
        logger.error("This eval requires --real (Ollama + ChromaDB). Exiting.")
        sys.exit(1)

    import requests
    from apiro.config import OLLAMA_BASE_URL, PRIMARY_MODEL
    from apiro.corpus.embedder import Embedder
    from apiro.patient.context import extract_patient_context
    from apiro.edar.candidate_discoverer import CandidateDiscoverer
    from apiro.edar.evidence_graph import EvidenceGraphBuilder
    from apiro.edar.belief_updater import BayesianBeliefUpdater
    from apiro.edar.discriminator import Discriminator
    from apiro.graph.edar_traversal import EdarTraversal
    from apiro.run import OllamaLLMClient

    # Check Ollama
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        r.raise_for_status()
    except Exception as e:
        logger.error(f"Ollama not reachable: {e}")
        sys.exit(1)

    # Shared components
    embedder   = Embedder()
    llm_client = OllamaLLMClient(url=OLLAMA_BASE_URL, model=PRIMARY_MODEL)

    class _ChromaAdapter:
        def __init__(self, emb):
            self._emb = emb
        def query(self, collection_name="", query_texts=None, n_results=6, where=None):
            text = (query_texts or [""])[0]
            results = self._emb.query(text, n_results=n_results, where=where)
            return {"documents": [[r["text"] for r in results]]}

    chroma_adapter = _ChromaAdapter(embedder)

    # Build EDAR traversal
    import chromadb
    client = chromadb.PersistentClient(path="data/chroma_db")
    try:
        disease_coll = client.get_collection("disease_profiles")
    except ValueError:
        disease_coll = None
    
    oracle = CandidateDiscoverer(embedder=embedder, n_query=60, n_candidates=15, disease_profile_collection=disease_coll)
    builder    = EvidenceGraphBuilder(embedder=embedder, n_results=10)
    updater    = BayesianBeliefUpdater()
    discrim    = Discriminator(embedder=embedder)

    edar_trav = EdarTraversal(
        oracle=oracle,
        graph_builder=builder,
        belief_updater=updater,
        discriminator=discrim,
        use_discriminator=True,
    )

    # Also build HT traversal for comparison
    from apiro.hypothesis.oracle import HypothesisOracle
    from apiro.hypothesis.evidence_matcher import EvidenceMatcher
    from apiro.hypothesis.bayesian_scorer import BayesianScorer
    from apiro.graph.traversal import HypothesisTestingTraversal

    ht_trav = HypothesisTestingTraversal(
        oracle=HypothesisOracle(),
        matcher=EvidenceMatcher(chroma_client=chroma_adapter),
        scorer=BayesianScorer(),
    )

    logger.info("=" * 70)
    logger.info("  3-WAY EVALUATION: Bare LLM vs RAG vs Apiro EDAR")
    logger.info("=" * 70)

    results = []

    for case in cases:
        case_id  = case["case_id"]
        vignette = case["vignette"]
        target   = case["target_diagnosis"]
        logger.info(f"\n{'─'*70}")
        logger.info(f"Case: {case_id} — {case['description']}")
        logger.info(f"Target: {target}")

        # ── 1. Bare LLM ───────────────────────────────────────────────────────
        logger.info("  [1/3] Bare LLM Zero-Shot...")
        prompt_bare = (
            "Based on the following clinical presentation, provide a list of your top 3 differential diagnoses. "
            "Output ONLY the top 3 diagnoses as a bulleted or numbered list without any other text:\n\n"
            f"{vignette}"
        )
        bare_output = llm_client.generate(prompt_bare)
        bare_items = [l.strip() for l in bare_output.split("\n") if l.strip()]
        bare_success, _ = _check_synthesis_hit(bare_items, target, embedder=embedder, llm_client=llm_client)
        logger.info(f"  Bare LLM: {'✓' if bare_success else '✗'} — {bare_items[:3]}")

        # ── 2. Standard RAG ───────────────────────────────────────────────────
        logger.info("  [2/3] Standard RAG Baseline...")
        rag_chunks  = embedder.query(vignette, n_results=6)
        rag_context = "\n\n".join([r["text"] for r in rag_chunks])
        prompt_rag  = (
            "Based on the following clinical presentation and retrieved medical context, "
            "provide your top 3 differential diagnoses. Output ONLY the top 3 diagnoses as a bulleted list:\n\n"
            f"Vignette: {vignette}\n\nContext:\n{rag_context}"
        )
        rag_output  = llm_client.generate(prompt_rag)
        rag_items   = [l.strip() for l in rag_output.split("\n") if l.strip()]
        rag_success, _ = _check_synthesis_hit(rag_items, target, embedder=embedder, llm_client=llm_client)
        logger.info(f"  RAG:      {'✓' if rag_success else '✗'} — {rag_items[:3]}")

        # ── 3. Apiro EDAR ─────────────────────────────────────────────────────
        logger.info("  [3/3] Apiro EDAR...")
        edar_success = False
        edar_output  = []
        try:
            edar_res    = edar_trav.run(vignette=vignette, case_name=f"{case_id}_edar")
            edar_output = edar_res.synthesis
            edar_success, _ = _check_synthesis_hit(edar_output, target, embedder=embedder, llm_client=llm_client)
            logger.info(f"  EDAR:     {'✓' if edar_success else '✗'} — {edar_output}")
        except Exception as e:
            logger.warning(f"  EDAR failed: {e}")

        results.append({
            "case_id":  case_id,
            "target":   target,
            "bare_llm": {"success": bare_success, "output": bare_items[:3]},
            "rag":      {"success": rag_success,  "output": rag_items[:3]},
            "edar":     {"success": edar_success, "output": edar_output},
        })

    # ── Summary ───────────────────────────────────────────────────────────────
    n = len(results)
    bare_wins = sum(1 for r in results if r["bare_llm"]["success"])
    rag_wins  = sum(1 for r in results if r["rag"]["success"])
    edar_wins = sum(1 for r in results if r["edar"]["success"])

    print("\n" + "=" * 70)
    print("  3-WAY EVALUATION RESULTS")
    print("=" * 70)

    for r in results:
        print(f"\nCase {r['case_id']}: Target → {r['target']}")
        print(f"  Bare LLM : {'✓ PASS' if r['bare_llm']['success'] else '✗ FAIL'} — {r['bare_llm']['output']}")
        print(f"  RAG      : {'✓ PASS' if r['rag']['success'] else '✗ FAIL'}      — {r['rag']['output']}")
        print(f"  EDAR     : {'✓ PASS' if r['edar']['success'] else '✗ FAIL'}     — {r['edar']['output']}")

    print(f"\n{'─'*70}")
    print(f"  Bare LLM  : {bare_wins}/{n} ({bare_wins/n*100:.1f}%)")
    print(f"  RAG       : {rag_wins}/{n}  ({rag_wins/n*100:.1f}%)")
    print(f"  Apiro EDAR: {edar_wins}/{n} ({edar_wins/n*100:.1f}%) ← NEW ENGINE")
    print("=" * 70 + "\n")

    # Save results
    out_path = ROOT / "data" / "edar_eval_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="Use real Ollama + ChromaDB")
    args = parser.parse_args()
    run_evaluation(args.real)
