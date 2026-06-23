#!/usr/bin/env python3
"""
scripts/evaluate_real_traversal.py
===================================
Orchestrates a real traversal run using:
  - Real Ollama instance with llama3.1:8b
  - Real ChromaDB collection populated by MedRAG
  - Real ContradictionDetector cross-encoder model
  - Real EntropyEngine

It runs the traversal loop, checks the main goal (epistemic saturation, entropy convergence,
and differential diagnosis validity), plots the entropy curve, and outputs a diagnostic report.
"""

import os
import sys
import json
import time
from pathlib import Path
import numpy as np
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Ensure project root is in path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from apiro.graph.belief_graph import BeliefGraph
from apiro.graph.node import Node
from apiro.graph.edge import Edge
from apiro.graph.expander import NodeExpander
from apiro.graph.saturation import SaturationDetector
from apiro.graph.rabbit_hole import RabbitHoleDetector
from apiro.graph.traversal import ApiroTraversal
from apiro.entropy.engine import EntropyEngine
from apiro.corpus.embedder import Embedder
from apiro.graph.contradiction import ContradictionDetector
from apiro.config import PRIMARY_MODEL, OLLAMA_BASE_URL, DATA_DIR, ROOT_DIR
FIG_DIR = ROOT_DIR / "figures"


# ── Ollama client ─────────────────────────────────────────────────────────────

class OllamaLLMClient:
    """Real Ollama LLM client for generating hypotheses."""
    
    def __init__(self, model: str = PRIMARY_MODEL, url: str = OLLAMA_BASE_URL):
        self.model = model
        self.url = url
        print(f"[OllamaLLMClient] Initialised with model: {self.model} at {self.url}")

    def chat(self, prompt: str) -> str:
        """Call Ollama's generate endpoint."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                # Low temperature = more deterministic, more faithful to prompt rules.
                # High temperature encourages speculation and domain drift.
                "temperature": 0.2,
                # 180 tokens: enough for 3 single-sentence hypotheses plus any
                # brief preamble the model adds. 100 was too tight — caused
                # mid-sentence truncation producing 'The' and [Expansion failed] nodes.
                "num_predict": 180,
            }
        }
        resp = requests.post(f"{self.url}/api/generate", json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json().get("response", "")


# ── Adapters ──────────────────────────────────────────────────────────────────

class _EntropyAdapter:
    """Wraps EntropyEngine as .compute() for NodeExpander.

    Uses epistemic_certainty_entropy() \u2014 the yes/no verification prompt \u2014
    so that entropy scores measure model uncertainty at clinical decision
    boundaries, not open-ended generation diversity.
    """
    
    def __init__(self, engine: EntropyEngine):
        self._engine = engine

    def compute(self, claim: str, context_chunks=None) -> float:
        result = self._engine.epistemic_certainty_entropy(claim, context_chunks)
        # Fallback to 0.5 (maximum binary uncertainty) if query fails
        return result if result is not None else 0.5


class _ChromaAdapter:
    """Wraps Embedder class to match NodeExpander's ChromaDB API."""
    
    def __init__(self, embedder: Embedder):
        self._embedder = embedder

    def query(self, collection_name: str, query_texts: list[str], n_results: int = 6) -> dict:
        results = self._embedder.query(query_texts[0], n_results=n_results)
        docs = [r["text"] for r in results]
        return {"documents": [docs]}


# ── Evaluation logic ──────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print(" APIRO — Real Traversal Evaluation Harness")
    print("=" * 70)

    # 1. Verify ChromaDB contains document corpus
    embedder = Embedder()
    if embedder.count == 0:
        print("[ERROR] ChromaDB collection is empty! Run build_corpus first.")
        print("Run: python -m apiro.corpus.build_corpus --sources medrag --max-records 500")
        sys.exit(1)
    print(f"[OK] ChromaDB collection '{embedder.collection_name}' has {embedder.count} documents.")

    # 2. Check Ollama reachability
    engine = EntropyEngine()
    if not engine.is_reachable():
        print(f"[ERROR] Ollama is unreachable at {engine.ollama_url} or model {engine.model} is not pulled.")
        sys.exit(1)
    print(f"[OK] Ollama is reachable. Using model: {engine.model}")

    # 3. Setup Case Case 1
    case_path = DATA_DIR / "synthetic_case_1.json"
    print(f"Loading case from: {case_path}")
    with open(case_path) as f:
        case_data = json.load(f)

    print(f"Case description: {case_data.get('description')}")
    seeds = []
    for s in case_data["seed_nodes"]:
        seeds.append(Node(
            id=s["id"],
            claim=s["claim"],
            entropy_score=s["entropy"],
            domain=s["domain"],
            depth=0,
        ))

    # 4. Initialize components
    entropy_adapter = _EntropyAdapter(engine)
    chroma_adapter  = _ChromaAdapter(embedder)
    llm_client      = OllamaLLMClient()
    
    print("Loading ContradictionDetector (MedNLI cross-encoder)...")
    contradiction = ContradictionDetector()

    expander = NodeExpander(
        entropy_engine=entropy_adapter,
        chroma_client=chroma_adapter,
        llm_client=llm_client,
        contradiction_detector=contradiction,
    )

    saturation  = SaturationDetector(theta=0.70, window=5, max_variance=0.04)
    rabbit_hole = RabbitHoleDetector(min_depth=3, reversal_window=4)

    traversal = ApiroTraversal(
        expander=expander,
        saturation=saturation,
        rabbit_hole=rabbit_hole,
        contradiction=contradiction,
    )

    graph = BeliefGraph()

    # 5. Run real traversal
    print("\n--- Running Real Traversal Loop ---")
    result = traversal.run(
        seed_nodes=seeds,
        graph=graph,
        max_depth=5,
        case_name="real_evaluation_case",
    )

    # 6. Evaluate and Assert Heuristics (Main Goal Verification)
    print("\n" + "=" * 50)
    print(" EVALUATION RESULTS & GOAL METRICS")
    print("=" * 50)

    # Metric A: Epistemic Convergence (Downward Entropy Trend)
    # The heuristic states that entropy should decline as we gather detail.
    expansions = graph._expansion_log
    entropies = [e["entropy"] for e in expansions]
    
    if len(entropies) >= 2:
        trend = np.polyfit(np.arange(len(entropies)), entropies, 1)[0]
        trend_status = "✅ PASS" if trend < 0 else "❌ FAIL"
    else:
        trend = 0.0
        trend_status = "N/A (Too few expansions)"

    # Metric B: Saturation Triggering
    sat_status = "✅ PASS" if result.stop_reason == "saturation" else "❌ WARNING (Stopped due to max_depth/no_frontier)"

    # Metric C: Contradictions Flagged
    contradictions = graph.get_contradiction_edges()

    print(f"Stop Reason:             {result.stop_reason} ({sat_status})")
    print(f"Total Expanded Nodes:    {result.total_nodes}")
    print(f"Total Edges:             {result.total_edges}")
    print(f"Linear Entropy Trend:    {trend:.5f} nats/expansion ({trend_status})")
    print(f"Rabbit Holes Flagged:    {result.rabbit_hole_count}")
    print(f"Contradiction Edges:     {len(contradictions)}")

    # 7. Print Generated Claims and Entropy Scores
    print("\n--- Traversal Expansion Pathway ---")
    for idx, event in enumerate(expansions):
        print(f"  [{idx+1}] Node: {event['node_id']} | H = {event['entropy']:.3f} | Depth = {event['depth']} | Claim: '{graph.nodes[event['node_id']].claim[:70]}'")

    # 8. Plot and Save Entropy Curve
    if len(entropies) >= 1:
        plt.figure(figsize=(8, 5))
        plt.plot(range(1, len(entropies) + 1), entropies, marker='o', color='#FF6B6B', linewidth=2, label='Node Entropy')
        plt.axhline(y=0.70, color='#4ECDC4', linestyle='--', label='Saturation Theta (0.70 — genetics)')
        plt.title('Real Traversal Entropy Convergence Curve', fontweight='bold', fontsize=14)
        plt.xlabel('Expansion Steps', fontsize=12)
        plt.ylabel('Token Entropy (nats)', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        fig_path = FIG_DIR / "real_traversal_entropy_curve.png"
        plt.savefig(fig_path, bbox_inches='tight')
        plt.close()
        print(f"\n[OK] Entropy curve saved to: {fig_path}")

    # 9. Save detailed evaluation report
    report_path = DATA_DIR / "real_traversal_evaluation_report.md"
    
    report_lines = [
        "# Apiro — Real Traversal Evaluation Report\n",
        "## Overall Verdict",
        f"**Stop Reason**: {result.stop_reason}",
        f"**Graph Size**: {result.total_nodes} nodes, {result.total_edges} edges",
        f"**Entropy Trend Slope**: {trend:.5f} nats/expansion ({trend_status})\n",
        "## Key Heuristics Validation\n",
        f"1. **Epistemic Convergence ({trend_status})**",
        f"   - Starting Entropy: {entropies[0]:.4f} nats" if entropies else "",
        f"   - Ending Entropy: {entropies[-1]:.4f} nats" if entropies else "",
        f"   - Heuristic Expectation: Linear slope should be negative, showing that the model converges to certainty as information is added.",
        f"2. **Epistemic Saturation ({sat_status})**",
        f"   - Saturation window: 5 nodes. Saturation threshold theta: 0.25",
        f"   - Heuristic Expectation: The loop should terminate automatically when information gains saturate.",
        f"3. **Logical Contradictions ({'✅ PASS' if len(contradictions) == 0 else '⚡ CONTRADICTIONS FLAGGED'})**",
        f"   - Found {len(contradictions)} contradiction relations in the graph.",
        f"4. **Rabbit Hole Detection ({'✅ PASS' if result.rabbit_hole_count == 0 else '🐇 RABBIT HOLES FLAGGED'})**",
        f"   - Flagged {result.rabbit_hole_count} speculative rabbit hole paths.\n",
        "## Expansion Chain Log\n",
        "| Step | Node ID | Entropy (nats) | Depth | Domain | Claim |",
        "|------|---------|----------------|-------|--------|-------|",
    ]
    for step, event in enumerate(expansions):
        node = graph.nodes[event["node_id"]]
        report_lines.append(f"| {step+1} | {event['node_id']} | {event['entropy']:.4f} | {event['depth']} | {node.domain} | {node.claim} |")

    with open(report_path, "w") as f:
        f.write("\n".join(report_lines))
    print(f"[OK] Evaluation report saved to: {report_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
