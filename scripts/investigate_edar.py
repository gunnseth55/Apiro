#!/usr/bin/env python3
"""
scripts/investigate_edar.py
============================
CLI runner for Apiro EDAR — Oracle shortlisting + Bayesian evidence-graph scoring.

Usage:
  python scripts/investigate_edar.py --findings "23yo neck abscess lymphadenopathy AFB positive"
"""
import argparse
import functools
import sys
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("investigate_edar")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def build_edar():
    import requests
    from apiro.config import OLLAMA_BASE_URL, PRIMARY_MODEL
    from apiro.corpus.embedder import Embedder
    from apiro.edar.candidate_discoverer import CandidateDiscoverer
    from apiro.edar.evidence_graph import EvidenceGraphBuilder
    from apiro.edar.belief_updater import BayesianBeliefUpdater
    from apiro.edar.discriminator import Discriminator
    from apiro.graph.edar_traversal import EdarTraversal

    try:
        requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5).raise_for_status()
    except Exception as e:
        print(f"\n❌  Ollama not reachable: {e}")
        sys.exit(1)

    embedder = Embedder()
    if embedder.count == 0:
        print("\n❌  ChromaDB corpus is empty. Build it first.")
        sys.exit(1)

    import chromadb
    client = chromadb.PersistentClient(path="data/chroma_db")
    try:
        disease_coll = client.get_collection("disease_profiles")
    except ValueError:
        disease_coll = None
        print("\n⚠️  No disease_profiles collection found. Run scripts/build_disease_index.py first.")
        
    oracle   = CandidateDiscoverer(embedder=embedder, disease_profile_collection=disease_coll)
    builder  = EvidenceGraphBuilder(embedder=embedder, n_results=10)
    updater  = BayesianBeliefUpdater()
    discrim  = Discriminator(embedder=embedder)

    traversal = EdarTraversal(
        oracle=oracle,
        graph_builder=builder,
        belief_updater=updater,
        discriminator=discrim,
        use_discriminator=True,
    )
    return traversal, embedder.count


def print_report(result, elapsed: float) -> None:
    print("\n+" + "-" * 62 + "+")
    print("|" + "  APIRO EDAR — DIAGNOSTIC REPORT".center(62) + "|")
    print("+" + "-" * 62 + "+")
    print(f"\n  Time:             {elapsed:.1f}s")
    print(f"  Stop reason:      {result.stop_reason}")
    print(f"  Candidates:       {result.n_candidates}")
    print(f"\n  [ PATIENT ]\n  {result.patient_context}")
    print(f"\n  [ TOP DIFFERENTIAL — Bayesian Evidence Scoring ]")
    for i, dx in enumerate(result.synthesis, 1):
        print(f"  {i}. {dx}")
    print(f"\n  [ EVIDENCE GRAPH ]")
    print(f"  {'Disease':50s} | Posterior | ✅ Confirmed | ❌ Absent | ⚡ Contradicted")
    print(f"  {'-'*100}")
    for disease, posterior, node in result.ranked[:5]:
        bar = "█" * min(int(posterior * 50), 50)
        print(f"  {disease[:50]:50s} | {posterior:.4f}    | {len(node.confirmed):11} | {len(node.absent):8} | {len(node.contradicted)}")
    print("\n+" + "-" * 62 + "+\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--findings", "-f", type=str, default=None)
    args = parser.parse_args()

    raw = args.findings
    if not raw:
        print("\nEnter clinical findings. Press Enter twice when done.\n")
        lines = []
        try:
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
        except EOFError:
            pass
        raw = "\n".join(lines)

    if not raw.strip():
        print("[-] No findings provided.")
        sys.exit(1)

    print("\n[*] Initialising EDAR components...")
    traversal, n_docs = build_edar()
    print(f"[+] Ready. Corpus: {n_docs:,} documents.\n")
    print("[*] Investigating with Oracle + Bayesian evidence graph...")

    t0 = time.time()
    result = traversal.run(vignette=raw, case_name="investigate_edar")
    elapsed = time.time() - t0
    print_report(result, elapsed)


if __name__ == "__main__":
    main()
