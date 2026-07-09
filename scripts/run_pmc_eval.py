#!/usr/bin/env python3
"""
scripts/run_distractor_eval.py
==============================
Runs the distractor-resilience evaluation comparing Apiro's belief graph
traversal against a bare LLM's zero-shot output on clinical vignettes
containing strong distractors/decoys.
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)-20s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("distractor_eval")

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from apiro.graph.node import Node

def run_evaluation(real_components: bool):
    # Load distractor cases
    cases_path = PROJECT_ROOT / "data" / "pmc_cases.json"
    with open(cases_path) as f:
        cases = json.load(f)

    # Initialize components
    if real_components:
        import requests
        from apiro.config import OLLAMA_BASE_URL, PRIMARY_MODEL
        from apiro.graph.expander import NodeExpander
        from apiro.graph.saturation import SaturationDetector
        from apiro.graph.rabbit_hole import RabbitHoleDetector
        from apiro.graph.contradiction import ContradictionDetector
        from apiro.entropy.engine import EntropyEngine
        from apiro.corpus.embedder import Embedder

        # Checks
        try:
            r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
            r.raise_for_status()
        except Exception as e:
            logger.error(f"[Ollama Error] Could not reach Ollama at {OLLAMA_BASE_URL}: {e}")
            sys.exit(1)

        embedder = Embedder()
        
        class _ChromaAdapter:
            def __init__(self, emb: Embedder):
                self._emb = emb
            def query(self, collection_name: str = "", query_texts: list = None, n_results: int = 6, where: dict | None = None) -> dict:
                query_texts = query_texts or []
                text = query_texts[0] if query_texts else ""
                results = self._emb.query(text, n_results=n_results, where=where)
                return {"documents": [[r["text"] for r in results]]}

        chroma_adapter = _ChromaAdapter(embedder)
        entropy_engine = EntropyEngine(model=PRIMARY_MODEL, ollama_url=OLLAMA_BASE_URL)


    # Begin evaluation
    logger.info("=" * 65)
    logger.info(f"Running Distractor-Resilience Evaluation (Mode: {'REAL' if real_components else 'MOCK'})")
    logger.info("=" * 65)

    results = []

    for case in cases:
        case_id = case["case_id"]
        vignette = case["vignette"]
        target = case["target_diagnosis"]
        logger.info(f"\nEvaluating Case: {case_id} — {case['description']}")
        
        from apiro.eval.evaluator import _check_synthesis_hit

        # 1. Bare LLM Zero-Shot
        logger.info("  Running Bare LLM Zero-Shot...")
        prompt = (
            "Based on the following clinical presentation, provide a list of your top 3 differential diagnoses. "
            "Output ONLY the top 3 diagnoses as a bulleted or numbered list without any other text:\n\n"
            f"{vignette}"
        )
        bare_output = llm_client.generate(prompt)
        logger.info(f"  Bare LLM Output:\n{bare_output.strip()}")
        
        bare_items = [line.strip() for line in bare_output.split("\n") if line.strip()]
        bare_success, _ = _check_synthesis_hit(
            bare_items,
            target,
            embedder=embedder if real_components else None,
            llm_client=llm_client if real_components else None
        )

        # 2. Standard RAG Baseline
        logger.info("  Running Standard RAG Baseline...")
        if real_components:
            rag_results = embedder.query(vignette, n_results=6)
            rag_context = "\n\n".join([r["text"] for r in rag_results])
            prompt_rag = (
                "Based on the following clinical presentation and the retrieved medical context, provide your top 3 differential diagnoses. "
                "Output ONLY the top 3 diagnoses as a bulleted or numbered list:\n\n"
                f"Vignette: {vignette}\n\nContext:\n{rag_context}"
            )
            rag_output = llm_client.generate(prompt_rag)
        else:
            prompt_rag = f"Standard RAG presentation:\n{vignette}"
            rag_output = llm_client.generate(prompt_rag)
        
        logger.info(f"  RAG Output:\n{rag_output.strip()}")
        
        rag_items = [line.strip() for line in rag_output.split("\n") if line.strip()]
        rag_success, _ = _check_synthesis_hit(
            rag_items,
            target,
            embedder=embedder if real_components else None,
            llm_client=llm_client if real_components else None
        )

        # 3. Apiro Hypothesis-Testing Traversal
        logger.info("  Running Apiro Hypothesis-Testing Traversal...")
        ht_success = False
        ht_output = []
        if real_components:
            try:
                from apiro.hypothesis.oracle          import HypothesisOracle
                from apiro.hypothesis.evidence_matcher import EvidenceMatcher
                from apiro.hypothesis.bayesian_scorer  import BayesianScorer
                from apiro.graph.traversal             import HypothesisTestingTraversal
                from apiro.graph.belief_graph          import BeliefGraph as BG

                oracle     = HypothesisOracle()
                ht_matcher = EvidenceMatcher(chroma_client=chroma_adapter)
                ht_scorer  = BayesianScorer()
                ht_trav    = HypothesisTestingTraversal(
                    oracle=oracle,
                    matcher=ht_matcher,
                    scorer=ht_scorer,
                )
                ht_res = ht_trav.run(vignette=vignette, case_name=f"{case_id}_ht")
                ht_output = ht_res.synthesis
                logger.info(f"  Apiro HT Synthesis: {ht_output}")
                ht_success, _ = _check_synthesis_hit(
                    ht_output,
                    target,
                    embedder=embedder,
                    llm_client=llm_client,
                )
            except Exception as e:
                logger.warning(f"  HT traversal failed: {e}")

        # Log soft-pruned nodes (from any prior graph built in this session)
        results.append({
            "case_id": case_id,
            "description": case["description"],
            "target": target,
            "bare_llm": {"success": bare_success, "output": bare_output},
            "rag":      {"success": rag_success,  "output": rag_output},
            "apiro_ht": {"success": ht_success,   "output": ht_output},
        })
        
        # Flush CUDA memory aggressively at the end of each case to prevent fragmentation
        if real_components:
            import gc
            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    # Summary Table
    print("\n" + "=" * 65)
    print("  DISTRACTOR-RESILIENCE EVALUATION SUMMARY")
    print("=" * 65)
    
    bare_wins  = sum(1 for r in results if r["bare_llm"]["success"])
    rag_wins   = sum(1 for r in results if r["rag"]["success"])
    ht_wins    = sum(1 for r in results if r.get("apiro_ht", {}).get("success", False))
    
    for r in results:
        ht = r.get("apiro_ht", {})
        print(f"Case {r['case_id']}: {r['description']}")
        print(f"  Target Diagnosis  : {r['target']}")
        print(f"  Bare LLM          : {'✓ SUCCESS' if r['bare_llm']['success'] else '✗ FAILED'}")
        print(f"  RAG               : {'✓ SUCCESS' if r['rag']['success'] else '✗ FAILED'}")
        print(f"  Apiro HT          : {'✓ SUCCESS' if ht.get('success') else '✗ FAILED'} — {ht.get('output', [])}")
        print("-" * 65)
        
    print(f"Bare LLM Total Success : {bare_wins}/{len(results)} ({bare_wins/len(results)*100:.1f}%)")
    print(f"RAG Baseline Success   : {rag_wins}/{len(results)} ({rag_wins/len(results)*100:.1f}%)")
    print(f"Apiro HT Success       : {ht_wins}/{len(results)} ({ht_wins/len(results)*100:.1f}%)")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run distractor-resilience evaluation")
    parser.add_argument("--real", action="store_true", help="Use real components (Ollama + ChromaDB)")
    args = parser.parse_args()
    run_evaluation(args.real)
