#!/usr/bin/env python3
"""
scripts/investigate.py
=======================
The Apiro AI Detective — free-text clinical vignette → differential diagnosis.

USAGE:
  venv/bin/python scripts/investigate.py \\
    --findings "72yo male, chest pain, troponin 2.1, ST elevation V3-V5, diaphoresis"

  Or interactively:
  venv/bin/python scripts/investigate.py

WHAT IT DOES:
  1. Parses your free-text clinical findings into typed seed nodes.
  2. Measures epistemic uncertainty (entropy) for each seed using the real
     EntropyEngine (Ollama required).
  3. Runs the Entropy-First belief-graph traversal, expanding into
     hypothesis space using RAG (ChromaDB 100k corpus) + LLM reasoning.
  4. Synthesises a final top-3 differential diagnosis from the highest-signal
     nodes in the belief graph.
  5. Prints a detailed detective report.

REQUIREMENTS:
  - Ollama running:   `ollama serve`
  - Corpus built:     `python scripts/build_corpus.py`
  - Model pulled:     `ollama pull llama3.1:8b`
"""

import argparse
import logging
import sys
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.WARNING,          # suppress library chatter during interactive use
    format="%(asctime)s  %(levelname)-8s %(name)-20s %(message)s",
    datefmt="%H:%M:%S",
)
# Show INFO only for apiro's own modules
for _mod in ("apiro.graph.traversal", "apiro.graph.expander", "apiro.eval"):
    logging.getLogger(_mod).setLevel(logging.INFO)

logger = logging.getLogger("investigate")
logger.setLevel(logging.INFO)


# ── Finding type heuristics ───────────────────────────────────────────────────
# Maps free-text patterns to clinical finding types so we can assign the right
# heuristic entropy and domain to each seed node.

FINDING_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # (regex pattern, finding_type, domain)
    (re.compile(r"\b(ct|mri|x-ray|ultrasound|echo|scan|imaging|radiograph|pet|angio)\b", re.I),
     "imaging", "imaging"),
    (re.compile(r"\b(troponin|creatinine|bilirubin|alt|ast|wbc|rbc|platelet|sodium|potassium"
                r"|chloride|glucose|hba1c|ferritin|tsh|igG|igM|anca|ana|anti|antibod)\b", re.I),
     "lab", "lab"),
    (re.compile(r"\b(gene|mutation|allele|hereditary|chromosom|genetic|familial)\b", re.I),
     "genetics", "genetics"),
    (re.compile(r"\b(drug|medication|prescribed|dose|mg|contraindicated|antibiotic|statin|aspirin)\b", re.I),
     "pharmacology", "pharmacology"),
    (re.compile(r"\b(surgery|procedure|resect|catheter|stent|bypass|transplant|dialysis)\b", re.I),
     "treatment", "treatment"),
    (re.compile(r"\b(history|hx|pmh|diagnosed|known|prior|previous|past medical)\b", re.I),
     "history", "comorbidity"),
    (re.compile(r"\b(hr|bp|spo2|temp|rr|pulse|pressure|saturation|vital)\b", re.I),
     "vital", "pathophysiology"),
    (re.compile(r"\b(pain|fever|cough|dyspnea|nausea|vomit|weakness|fatigue|confusion|syncope"
                r"|headache|rash|swelling|diarrhea|chest|abdomen|back)\b", re.I),
     "symptom", "pathophysiology"),
]

# Heuristic entropy by finding type (calibrated on llama3.1:8b)
ENTROPY_BY_TYPE: dict[str, float] = {
    "symptom":     0.80,
    "history":     0.72,
    "vital":       0.65,
    "lab":         0.58,
    "imaging":     0.32,
    "genetics":    0.70,
    "pharmacology":0.55,
    "treatment":   0.45,
}
ENTROPY_DEFAULT = 0.693   # ln(2)


def classify_finding(text: str) -> tuple[str, str, float]:
    """
    Classify a free-text clinical finding into (finding_type, domain, entropy).
    Uses regex heuristics — fast and offline.
    """
    for pattern, ftype, domain in FINDING_PATTERNS:
        if pattern.search(text):
            return ftype, domain, ENTROPY_BY_TYPE.get(ftype, ENTROPY_DEFAULT)
    return "symptom", "pathophysiology", ENTROPY_DEFAULT


def parse_findings_to_seeds(raw: str, entropy_engine=None) -> list:
    """
    Split free-text clinical findings into individual seed nodes.

    Two-pass splitting strategy:
      Pass 1 — strong delimiters: newlines, semicolons, EM-dashes, periods.
               These always produce a clean break.
      Pass 2 — comma splitting: any fragment still longer than 60 chars that
               contains commas is further split on commas (handles comma-
               separated vignettes like "45yo male, chest pain, troponin 2.1").
               Short comma-fragments (<15 chars) are merged with their
               predecessor so "HR 104" and "BP 88/60" don't become
               isolated micro-seeds with no clinical context.

    If entropy_engine is provided, compute real epistemic entropy via Ollama
    instead of using the heuristic value (slower but more accurate).
    """
    from apiro.graph.node import Node

    text = raw.strip()

    # ── Pass 1: strong delimiters ─────────────────────────────────────────────
    pass1 = re.split(r"\n|;\s*| \u2014 | - (?=[A-Z])|\. (?=[A-Z0-9])", text)
    pass1 = [f.strip().strip(",").strip() for f in pass1 if f.strip()]

    # ── Pass 2: comma-split long fragments ────────────────────────────────────
    fragments: list[str] = []
    for frag in pass1:
        if len(frag) > 60 and "," in frag:
            parts = [p.strip().strip(",") for p in frag.split(",")]
            # If the first part is demographic info (age/gender), prepend it to the next part
            if len(parts) > 1 and any(
                x in parts[0].lower()
                for x in ["yo", "male", "female", "man", "woman", "years", "old"]
            ):
                parts[1] = parts[0] + ", " + parts[1]
                parts = parts[1:]

            # Merge very short parts (< 15 chars) back into previous
            merged: list[str] = []
            for part in parts:
                if len(part) < 15 and merged:
                    merged[-1] = merged[-1] + ", " + part
                elif part:
                    merged.append(part)
            fragments.extend(merged)
        else:
            fragments.append(frag)

    # ── Filter and deduplicate ────────────────────────────────────────────────
    seen: set[str] = set()
    unique: list[str] = []
    for f in fragments:
        if len(f) >= 10 and f.lower() not in seen:
            unique.append(f)
            seen.add(f.lower())

    if not unique:
        # Last-resort fallback: treat entire input as one seed
        unique = [text]

    # ── Build seed nodes ──────────────────────────────────────────────────────
    seeds = []
    for i, fragment in enumerate(unique):
        ftype, domain, heuristic_entropy = classify_finding(fragment)

        if entropy_engine is not None:
            try:
                entropy = entropy_engine.epistemic_certainty_entropy(
                    fragment, context_chunks=None
                )
                if entropy is None:
                    entropy = heuristic_entropy
                logger.info(
                    f"  Seed [{i}] entropy={entropy:.3f} ({ftype}): {fragment[:60]}"
                )
            except Exception:
                entropy = heuristic_entropy
        else:
            entropy = heuristic_entropy

        seeds.append(Node(
            id=f"seed_{i}",
            claim=f"{fragment} - {ftype}",   # ASCII dash, not EM-dash
            entropy_score=entropy,
            domain=domain,
            depth=0,
        ))

    return seeds


# ── Component builder (mirrors run.py) ────────────────────────────────────────

def build_components():
    import requests
    from apiro.graph.expander      import NodeExpander
    from apiro.graph.saturation    import SaturationDetector
    from apiro.graph.rabbit_hole   import RabbitHoleDetector
    from apiro.graph.contradiction import ContradictionDetector
    from apiro.entropy.engine      import EntropyEngine
    from apiro.corpus.embedder     import Embedder
    from apiro.graph.traversal     import ApiroTraversal
    from apiro.config import (
        OLLAMA_BASE_URL, PRIMARY_MODEL,
        DEFAULT_THETA, SATURATION_WINDOW, SATURATION_MAX_VARIANCE,
        RABBIT_HOLE_MIN_DEPTH, RABBIT_HOLE_REVERSAL_WINDOW,
    )

    # ── Ollama check ──────────────────────────────────────────────────────────
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        r.raise_for_status()
    except Exception as e:
        print(f"\n❌  Ollama not reachable at {OLLAMA_BASE_URL}: {e}")
        print("    Start it with:  ollama serve")
        sys.exit(1)

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    embedder  = Embedder()
    doc_count = embedder.count
    if doc_count == 0:
        print("\n❌  ChromaDB corpus is empty.")
        print("    Build it with:  python scripts/build_corpus.py")
        sys.exit(1)

    class _ChromaAdapter:
        def __init__(self, emb): self._emb = emb
        def query(self, collection_name="", query_texts=None,
                  n_results=6, where=None) -> dict:
            text = (query_texts or [""])[0]
            docs = [r["text"] for r in self._emb.query(text, n_results=n_results, where=where)]
            return {"documents": [docs]}

    class _OllamaLLMClient:
        def __init__(self, url, model):
            self.url, self.model = url, model
        def generate(self, prompt):
            import requests as req
            resp = req.post(
                f"{self.url}/api/generate",
                json={"model": self.model, "prompt": prompt,
                      "stream": False, "options": {"temperature": 0.2, "num_predict": 180}},
                timeout=90,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        def generate_with_logprobs(self, prompt):
            import requests as req
            resp = req.post(
                f"{self.url}/api/generate",
                json={"model": self.model, "prompt": prompt,
                      "stream": False, "options": {"temperature": 0.2, "num_predict": 180},
                      "logprobs": True},
                timeout=90,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", ""), data.get("logprobs", [])
        def chat(self, prompt): return self.generate(prompt)

    chroma     = _ChromaAdapter(embedder)
    entropy_e  = EntropyEngine(model=PRIMARY_MODEL, ollama_url=OLLAMA_BASE_URL)
    llm        = _OllamaLLMClient(OLLAMA_BASE_URL, PRIMARY_MODEL)
    contra     = ContradictionDetector()

    expander = NodeExpander(
        entropy_engine=entropy_e,
        chroma_client=chroma,
        llm_client=llm,
        contradiction_detector=contra,
    )
    sat  = SaturationDetector(theta=DEFAULT_THETA, window=SATURATION_WINDOW,
                               max_variance=SATURATION_MAX_VARIANCE)
    rh   = RabbitHoleDetector(min_depth=RABBIT_HOLE_MIN_DEPTH,
                               reversal_window=RABBIT_HOLE_REVERSAL_WINDOW)
    trav = ApiroTraversal(expander=expander, saturation=sat,
                          rabbit_hole=rh, contradiction=contra)

    return trav, expander, entropy_e, doc_count


def print_report(result, seed_count: int, elapsed: float) -> None:
    print("\n+" + "-" * 58 + "+")
    print("|" + "    APIRO DIFFERENTIAL DIAGNOSIS REPORT".center(58) + "|")
    print("+" + "-" * 58 + "+")

    print(f"\n  Seed findings parsed:   {seed_count}")
    print(f"  Graph nodes expanded:   {result.total_nodes}")
    print(f"  Rabbit holes pruned:    {result.rabbit_hole_count}")
    print(f"  Contradictions flagged: {result.contradiction_count}")
    print(f"  Stopped because:        {result.stop_reason}")
    print(f"  Total time:             {elapsed:.1f}s")

    print("\n" + "-" * 60)
    print("  TOP 3 DIFFERENTIAL DIAGNOSES")
    print("-" * 60)
    for i, dx in enumerate(result.synthesis or ["(no synthesis available)"], 1):
        print(f"  [{i}] {dx}")

    print("\n" + "-" * 60)
    print("  HOW TO INTERPRET THIS:")
    print("  * #1 is the most likely diagnosis given available evidence.")
    print("  * The engine explored uncertainty -> high-entropy paths first.")
    print("  * Rabbit holes were contradictions/tangents pruned from the graph.")
    print("-" * 60 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Apiro AI Detective — free-text clinical findings → differential diagnosis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--findings", "-f",
        type=str,
        default=None,
        help="Free-text clinical findings (comma/newline/semicolon separated). "
             "If omitted, enters interactive mode.",
    )
    parser.add_argument(
        "--max-depth", type=int, default=5,
        help="Max traversal depth (default: 5). Increase for complex cases.",
    )
    parser.add_argument(
        "--real-entropy", action="store_true",
        help="Compute real epistemic entropy for seed nodes via Ollama "
             "(slower but more accurate seeds). Default: use heuristic entropy.",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Optional path to write the belief graph JSON.",
    )
    args = parser.parse_args()

    # ── Get findings ──────────────────────────────────────────────────────────
    if args.findings:
        raw_findings = args.findings
    else:
        print("\n" + "=" * 60)
        print("    APIRO -- AI DIAGNOSTIC DETECTIVE")
        print("=" * 60)
        print("  Enter clinical findings (symptoms, labs, vitals, history).")
        print("  Separate with commas, newlines, or semicolons.")
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
    traversal, expander, entropy_engine, doc_count = build_components()
    print(f"[+] Components ready. Corpus: {doc_count:,} documents.\n")

    # ── Parse findings into seed nodes ────────────────────────────────────────
    ee = entropy_engine if args.real_entropy else None
    if args.real_entropy:
        print("[*] Computing real seed entropy (this calls Ollama once per finding)...")

    seeds = parse_findings_to_seeds(raw_findings, entropy_engine=ee)

    if not seeds:
        print("[-] Could not parse any findings from the provided text.")
        sys.exit(1)

    print(f"[*] Parsed {len(seeds)} seed findings:")
    for s in seeds:
        # replace the unicode EM-dash \u2014 with standard -
        claim_clean = s.claim.replace("\u2014", "-")
        print(f"    [{s.domain:15s}] H={s.entropy_score:.3f}  {claim_clean[:70]}")

    # ── Run traversal ─────────────────────────────────────────────────────────
    from apiro.graph.belief_graph import BeliefGraph
    print(f"\n[*] Apiro is investigating... (max_depth={args.max_depth})")
    print("    (This takes 1-5 minutes depending on case complexity)\n")

    t0    = time.time()
    graph = BeliefGraph()
    result = traversal.run(
        seed_nodes=seeds,
        graph=graph,
        max_depth=args.max_depth,
        case_name="investigate",
    )
    elapsed = time.time() - t0

    # ── Optional graph export ─────────────────────────────────────────────────
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        graph.export_json(path=args.output)
        print(f"\n[+] Belief graph written to: {args.output}")

    # ── Print report ──────────────────────────────────────────────────────────
    print_report(result, len(seeds), elapsed)


if __name__ == "__main__":
    main()
