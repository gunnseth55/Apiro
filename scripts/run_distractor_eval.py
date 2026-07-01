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

from apiro.graph.belief_graph import BeliefGraph
from apiro.graph.node import Node
from apiro.graph.traversal import ApiroTraversal

def run_evaluation(real_components: bool):
    # Load distractor cases
    cases_path = PROJECT_ROOT / "data" / "distractor_cases.json"
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
        
        class OllamaLLMClient:
            def __init__(self, url, model):
                self.url   = url
                self.model = model
            def generate(self, prompt: str) -> str:
                import requests as req
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 180},
                }
                resp = req.post(f"{self.url}/api/generate", json=payload, timeout=90)
                return resp.json().get("response", "")
            def chat(self, prompt: str) -> str:
                return self.generate(prompt)

        llm_client = OllamaLLMClient(OLLAMA_BASE_URL, PRIMARY_MODEL)
        contradiction = ContradictionDetector()
        expander = NodeExpander(
            entropy_engine=entropy_engine,
            chroma_client=chroma_adapter,
            llm_client=llm_client,
            contradiction_detector=contradiction,
        )
        saturation = SaturationDetector()
        rabbit_hole = RabbitHoleDetector()
        traversal = ApiroTraversal(
            expander=expander,
            saturation=saturation,
            rabbit_hole=rabbit_hole,
            contradiction=contradiction,
        )
    else:
        # Import stub components
        from apiro.graph.expander import NodeExpander, StubEntropyEngine, StubChromaClient
        from apiro.graph.saturation import SaturationDetector
        from apiro.graph.rabbit_hole import RabbitHoleDetector
        
        # Stub Contradiction Detector simulating soft-pruning on specific distractor pairs
        class StubContradictionDetector:
            def check(self, claim_a: str, claim_b: str):
                from dataclasses import dataclass
                @dataclass
                class R:
                    label: str
                    score: float
                    negation_detected: bool
                a, b = claim_a.lower(), claim_b.lower()
                # Case 1 contradiction: normal troponin/ECG contradicts myocardial infarction
                if ("myocardial infarction" in a or "myocardial infarction" in b) and ("normal troponin" in a or "normal troponin" in b or "normal sinus rhythm" in a or "normal sinus rhythm" in b):
                    return R("contradiction", 0.95, False)
                # Case 2 contradiction: travel/jaundice contradicts negative blood films
                if ("malaria" in a or "malaria" in b) and ("negative for plasmodium" in a or "negative for plasmodium" in b):
                    return R("contradiction", 0.95, False)
                return R("neutral", 0.5, False)
            def should_check(self, claim_a: str, claim_b: str) -> bool:
                return True

        # Stub LLM Client simulating bare LLM vs Apiro
        class StubLLMClient:
            def generate(self, prompt: str) -> str:
                # Bare LLM prompt detection
                if "Based on the following clinical presentation" in prompt:
                    if "dinner" in prompt or "substernal chest pain" in prompt:
                        return "1. Acute Myocardial Infarction\n2. Angina Pectoris\n3. Gastroesophageal Reflux Disease"
                    elif "sub-Saharan Africa" in prompt or "tea-colored urine" in prompt:
                        return "1. Malaria infection\n2. Acute Hepatitis\n3. Hemolytic Anemia"
                
                # Expand node prompts
                p_lower = prompt.lower()
                if "synthesize the final top 3" in prompt:
                    if "esophageal" in p_lower or "chest pain" in p_lower:
                        return "1. Esophageal Spasm\n2. Gastroesophageal Reflux Disease\n3. Angina Pectoris"
                    elif "g6pd" in p_lower or "bite cells" in p_lower:
                        return "1. G6PD Deficiency\n2. Autoimmune Hemolytic Anemia\n3. Urinary Tract Infection"
                
                if "severe substernal chest pain" in p_lower:
                    return "Hypotheses:\n1. Acute Myocardial Infarction is the primary cause\n2. Diffuse Esophageal Spasm should be ruled out\n3. Gastroesophageal Reflux Disease"
                if "normal sinus rhythm" in p_lower or "troponin" in p_lower:
                    return "Hypotheses:\n1. Non-cardiac chest pain\n2. Esophageal Spasm causing spasm pain\n3. Reflux disease"
                if "bite cells" in p_lower or "nitrofurantoin" in p_lower:
                    return "Hypotheses:\n1. G6PD Deficiency hemolytic crisis\n2. Drug-induced hemolytic anemia\n3. Heinz body anemia"
                
                return "Hypotheses:\n1. Alternative differential diagnosis A\n2. Alternative differential diagnosis B\n3. Alternative differential diagnosis C"

            def chat(self, prompt: str) -> str:
                return self.generate(prompt)

        llm_client = StubLLMClient()
        contradiction = StubContradictionDetector()
        expander = NodeExpander(
            entropy_engine=StubEntropyEngine(),
            chroma_client=StubChromaClient(),
            llm_client=llm_client,
            contradiction_detector=contradiction,
        )
        saturation = SaturationDetector(theta=0.25, window=5, max_variance=0.04)
        rabbit_hole = RabbitHoleDetector(min_depth=3, reversal_window=4)
        traversal = ApiroTraversal(
            expander=expander,
            saturation=saturation,
            rabbit_hole=rabbit_hole,
            contradiction=contradiction,
        )

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
        
        # 1. Bare LLM Zero-Shot
        logger.info("  Running Bare LLM Zero-Shot...")
        prompt = (
            "Based on the following clinical presentation, provide a list of your top 3 differential diagnoses. "
            "Output ONLY the top 3 diagnoses as a bulleted or numbered list without any other text:\n\n"
            f"{vignette}"
        )
        bare_output = llm_client.generate(prompt)
        logger.info(f"  Bare LLM Output:\n{bare_output.strip()}")
        
        bare_success = target.lower() in bare_output.lower()

        # 2. Apiro Traversal
        logger.info("  Running Apiro Traversal...")
        graph = BeliefGraph()
        seeds = [
            Node(
                id=s["id"],
                claim=s["claim"],
                entropy_score=s["entropy"],
                domain=s["domain"],
                depth=s["depth"]
            )
            for s in case["seed_nodes"]
        ]
        
        traversal_res = traversal.run(
            seed_nodes=seeds,
            graph=graph,
            max_depth=4,
            case_name=case_id
        )
        
        apiro_output = traversal_res.synthesis
        apiro_output_str = "\n".join(apiro_output)
        logger.info(f"  Apiro Final Synthesis:\n{apiro_output_str.strip()}")
        
        apiro_success = any(target.lower() in item.lower() for item in apiro_output)

        # Log soft-pruned nodes
        for node in graph.nodes.values():
            if getattr(node, "contradiction_penalty", 0.0) > 0:
                logger.info(
                    f"    - Contradiction Soft-Pruned Node: '{node.claim[:45]}' "
                    f"has penalty={node.contradiction_penalty} (is_rabbit_hole={node.is_rabbit_hole})"
                )

        results.append({
            "case_id": case_id,
            "description": case["description"],
            "target": target,
            "bare_llm": {
                "success": bare_success,
                "output": bare_output
            },
            "apiro": {
                "success": apiro_success,
                "output": apiro_output
            }
        })

    # Summary Table
    print("\n" + "=" * 65)
    print("  DISTRACTOR-RESILIENCE EVALUATION SUMMARY")
    print("=" * 65)
    
    bare_wins = sum(1 for r in results if r["bare_llm"]["success"])
    apiro_wins = sum(1 for r in results if r["apiro"]["success"])
    
    for r in results:
        print(f"Case {r['case_id']}: {r['description']}")
        print(f"  Target Diagnosis : {r['target']}")
        print(f"  Bare LLM Success : {'✓ SUCCESS' if r['bare_llm']['success'] else '✗ FAILED (Hallucinated distractor)'}")
        print(f"  Apiro Success    : {'✓ SUCCESS' if r['apiro']['success'] else '✗ FAILED'}")
        print("-" * 65)
        
    print(f"Bare LLM Total Success: {bare_wins}/{len(results)} ({bare_wins/len(results)*100:.1f}%)")
    print(f"Apiro Total Success   : {apiro_wins}/{len(results)} ({apiro_wins/len(results)*100:.1f}%)")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run distractor-resilience evaluation")
    parser.add_argument("--real", action="store_true", help="Use real components (Ollama + ChromaDB)")
    args = parser.parse_args()
    run_evaluation(args.real)
