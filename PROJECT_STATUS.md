# Project Status: Apiro Curiosity Engine

This document outlines the exact technical state of the Apiro project as of June 2026. It serves as a status report for developers, collaborators, and clinical advisors to understand what is built, what is functional, and where the active boundaries of development lie.

---

## 🚦 Current Phase Status

| Development Phase | Focus Area | Status | Key Components |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Corpus & Infrastructure | **Complete** | Textbook scraper, ClinVar parser, MedRAG adapters, ChromaDB embeddings. |
| **Phase 2** | Graph/Traversal Engine | **Complete** | `BeliefGraph`, `ApiroTraversal` (Entropy-First), `BreadthFirstTraversal`, NLI Contradiction Detector, Rabbit Hole & Saturation logic. |
| **Phase 3** | Benchmarking & Evaluation | **In Progress** | `CaseEvaluator`, `scripts/run_phase3_eval.py`, SentenceTransformer similarity metric. |
| **Phase 4** | API & User Interface | **Planned** | FastAPI endpoint, interactive graph visualization UI. |

---

## 🏗️ State of the Architecture (Module-by-Module)

### 1. The Corpus Infrastructure (`apiro/corpus/`)
* **State:** Fully functional.
* **Details:** Built to ingest unstructured medical knowledge (PubMed, textbooks, ClinVar clinical assertions) and store them as vector embeddings in a local **ChromaDB** instance.
* **Status:** Clean. The vector database successfully supports semantic chunk retrieval during the node expansion phase.

### 2. The Entropy Engine (`apiro/entropy/engine.py`)
* **State:** Fully functional and calibrated.
* **Details:** Computes epistemic uncertainty at clinical decision boundaries. It forces the LLM to output a binary `Yes/No` on whether a claim is clinically supported by retrieved context, extracting token-level log probabilities.
* **Recent Fix:** Reverted a drift in the prompt. It now strictly queries clinical truth/support rather than "interest" or "relevance," restoring a theoretically sound entropy signal.

### 3. The Belief Graph (`apiro/graph/belief_graph.py`, `node.py`, `edge.py`)
* **State:** Fully functional.
* **Details:** Tracks the current state of clinical beliefs during traversal. Supports adding nodes, establishing edges, tracking traversal depth, detecting contradiction loops, and exporting the graph to JSON format.
* **Recent Optimization:** Implemented **Depth-Aware Frontier Scoring**.
  * At depth 0, the node queue is sorted by lowest entropy (anchoring on certainty).
  * At depth $\ge$ 1, the queue is sorted by highest entropy (chasing uncertainty).

### 4. Traversal Engines (`apiro/graph/traversal.py`, `breadth_first.py`)
* **State:** Fully functional.
* **Details:** Implements two traversal strategies:
  * **ApiroTraversal (Entropy-First):** Guided by depth-aware entropy scores. Features active rabbit-hole detection (halting expansion if a branch has consecutive zero-entropy steps) and saturation detection (halting traversal if the rolling average graph entropy variance drops below a threshold).
  * **Breadth-First baseline (BF):** Explores the graph layer-by-layer without entropy heuristic guidance.
* **Recent Feature:** Integrated **Differential Diagnosis Synthesis** at the end of both traversals to compile a top-3 differential diagnosis.

### 5. Contradiction Detector (`apiro/graph/contradiction.py`)
* **State:** Functional.
* **Details:** Uses a MiniLM cross-encoder NLI model combined with a NegEx (negation detection) layer. If the cross-encoder flags an NLI contradiction between two active nodes and there is no negation difference, a contradiction edge is written in the graph.

### 6. The Evaluator (`apiro/eval/evaluator.py`, `scripts/run_phase3_eval.py`)
* **State:** Recently Upgraded.
* **Details:** Compares Entropy-First (EF) search efficiency against Breadth-First (BF).
* **Recent Upgrade:**
  * Replaced node-level substring matching with **synthesis-level matching**.
  * Integrated a shared `SentenceTransformer` (using `all-mpnet-base-v2`) to compute cosine similarity between the ground truth and the synthesized top-3 differential.
  * Winner metric changed to compare `total_nodes` expanded (assessing search efficiency) rather than raw `path_length`.

---

## 📈 Initial Benchmark Results (n=3 test run)

We evaluated both search strategies against a small subset of 3 clinical cases. The metric compared was **total nodes expanded** to reach a correct synthesis (lower is better, validating search efficiency).

| Case # | Target Diagnosis | EF Total Nodes | BF Total Nodes | Result / Winner | Note |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Case 1** | STEMI | **30 nodes** | 42 nodes | **EF Win** | EF reached target synthesis with 28% fewer nodes. |
| **Case 2** | Pancreatitis | Miss | Miss | Tie (Both Miss) | Neither traversal reached the strict similarity threshold. |
| **Case 3** | NPSLE | Miss | Miss | Tie (Both Miss) | **Evaluator Artifact:** EF synthesized "Systemic Lupus Erythematosus" (SLE), but the ground truth was "Neuropsychiatric SLE" (NPSLE). Similarity scored `0.701` (narrowly missed `0.75` threshold). |

---

## ⚠️ Current Issues & Risks

1. **Rigidity of Semantic Similarity Thresholds:**
   * Cosine similarity of sentence embeddings (e.g., using `all-mpnet-base-v2`) is highly sensitive to phrasing. A threshold of `0.75` causes valid diagnoses (like SLE vs. NPSLE) to be marked as misses, while a lower threshold (e.g., `0.65`) might allow incorrect diagnoses to pass.
2. **NLI Cross-Encoder Latency:**
   * Evaluating all pairs of nodes for contradictions is $O(N^2)$ and introduces computational overhead when the belief graph exceeds 50 nodes.

---

## 🗺️ Next Steps

1. **Phase 3 Benchmark Scale-up:**
   * Run the full 10-case evaluation suite (`python scripts/run_phase3_eval.py --n 10`) to gather statistically significant data.
2. **Evaluate Alternative Evaluator Judges:**
   * Test an **LLM-as-a-judge** component in the evaluator to handle medical nuances (e.g., matching broader/narrower categories).
   - Test a **curated evaluation map** mapping test cases directly to their acceptable parent/child hierarchies.
3. **Phase 4 UI Prototyping:**
   - Establish a simple FastAPI server (`apiro/api/`) and construct a UI visualizer using PyVis or a web interface to show the graph expanding in real-time.
