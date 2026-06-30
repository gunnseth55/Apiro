# Project Status: Apiro Curiosity Engine

This document outlines the exact technical state of the Apiro project as of June 2026. It serves as a status report for developers, collaborators, and clinical advisors to understand what is built, what is functional, and where the active boundaries of development lie.

---

## 🚦 Current Phase Status

| Development Phase | Focus Area | Status | Key Components |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Corpus & Infrastructure | **Complete** | Textbook scraper, ClinVar parser, MedRAG adapters, ChromaDB embeddings. |
| **Phase 2** | Graph/Traversal Engine | **Complete** | `BeliefGraph`, `ApiroTraversal` (Entropy-First), `BreadthFirstTraversal`, NLI Contradiction Detector, Rabbit Hole & Saturation logic. |
| **Phase 3** | Benchmarking & Evaluation | **Complete** | `CaseEvaluator` (LLM-as-a-Judge), 10-case evaluation harness (`run_phase3_eval.py`). Achieved a **50% win rate** on path efficiency over BFS. Fully green test suite (**115/115 passing tests**). |
| **Phase 4** | API & User Interface | **Complete** | Interactive D3.js Graph Visualization UI (`visualize_graph.py`), user-facing free-text CLI (`investigate.py`), and FastAPI web UI backend (`app.py`). |

---

## 🏗️ State of the Architecture (Module-by-Module)

### 1. The Corpus Infrastructure (`apiro/corpus/`)
* **State:** Fully functional.
* **Details:** Built to ingest unstructured medical knowledge (PubMed, textbooks, ClinVar clinical assertions) and store them as vector embeddings in a local **ChromaDB** instance. Contains 100,000 real medical records.
* **Status:** Clean. The vector database successfully supports semantic chunk retrieval during the node expansion phase. Legacy scrapers and metadata repairs are located in `scripts/repair_corpus.py`.

### 2. The Entropy Engine (`apiro/entropy/engine.py`)
* **State:** Fully functional and calibrated.
* **Details:** Computes epistemic uncertainty at clinical decision boundaries. It forces the LLM to output a binary `Yes/No` on whether a claim is clinically supported by retrieved context, extracting token-level log probabilities.
* **Prompting:** Uses the yes/no verification prompt to capture model uncertainty rather than generation diversity.

### 3. The Belief Graph (`apiro/graph/belief_graph.py`, `node.py`, `edge.py`)
* **State:** Fully functional.
* **Details:** Tracks the current state of clinical beliefs during traversal. Supports adding nodes, establishing edges, tracking traversal depth, detecting contradiction loops, and exporting the graph to JSON format.
* **Frontier Sorting:** Implemented **Depth-Aware Frontier Sorting**:
  * At depth 0, the node queue is sorted by lowest entropy (anchoring on certainty).
  * At depth $\ge$ 1, the queue is sorted by highest entropy (chasing uncertainty).

### 4. Traversal Engines (`apiro/graph/traversal.py`, `breadth_first.py`)
* **State:** Fully functional.
* **Details:** Implements two traversal strategies:
  * **ApiroTraversal (Entropy-First):** Guided by depth-aware entropy scores. Features active rabbit-hole detection (halting expansion if a branch has consecutive zero-entropy steps) and saturation detection (halting traversal if the rolling average graph entropy variance drops below a threshold).
  * **Breadth-First baseline (BF):** Explores the graph layer-by-layer without entropy heuristic guidance.
* **Synthesis:** Integrated **Differential Diagnosis Synthesis** at the end of both traversals to compile a top-3 differential diagnosis.

### 5. Contradiction Detector (`apiro/graph/contradiction.py`)
* **State:** Functional.
* **Details:** Uses a MiniLM cross-encoder NLI model. If the cross-encoder flags an NLI contradiction between two active nodes, a contradiction edge is written in the graph and the weaker node is pruned.

### 6. The Evaluator (`apiro/eval/evaluator.py`, `scripts/run_phase3_eval.py`)
* **State:** Fully functional and upgraded.
* **Details:** Compares search efficiency on blind clinical cases from VivaBench and CUPCase.
* **LLM-as-a-Judge:** Uses the LLM client to evaluate whether a synthesized diagnosis matches the ground truth (resolving synonym issues like matching "Lupus Cerebritis" to "NPSLE").
* **Score:** The Entropy-First (EF) traversal achieved a **50% win rate** on node expansion efficiency compared to the Breadth-First search baseline.

### 7. Interactive Visualization & UI (`scripts/visualize_graph.py`, `scripts/app.py`)
* **State:** Fully functional.
* **Details:**
  * **visualize_graph.py:** Generates a self-contained HTML force-directed graph (using D3.js) showing the belief graph topology, entropy heatmaps (color-coded nodes), active vs. pruned paths, and a details sidebar.
  * **app.py:** A FastAPI web UI that lets users input clinical presentations, run traversals in real-time, inspect dynamic graphs inside the browser, and view synthesized differentials.

### 8. User-Facing Detective (`scripts/investigate.py`)
* **State:** Fully functional.
* **Details:** Accepts free-text clinical vignettes from a user (either interactively or via CLI), parses them into typed seed nodes (symptoms, labs, imaging, vitals), runs a stub-free, real-time traversal, and synthesizes a formatted differential report.

### 9. NLP & Model Footprint Optimization
* **State:** De-bloated.
* **Details:** The BART-based zero-shot classifier `domain_classifier.py` (~1.6 GB) was **removed**. Domain classification is now handled by a hybrid keyword-matching and dot-product semantic fallback in `expander.py` (which reuses the already loaded SentenceTransformer embeddings), dropping extra memory overhead to 0 MB. All obsolete mock/calibration scripts have been removed to prune the repository.

---

## 📈 Initial Benchmark Results (Phase 3)

We evaluated both search strategies against 10 clinical cases. The metric compared was **total nodes expanded** to reach a correct synthesis (lower is better, validating search efficiency).

* **Entropy-First (EF) Win Rate:** **50.0%** (5/10 cases)
* **Breadth-First (BF) Win Rate:** **20.0%** (2/10 cases)
* **Ties / Both Miss:** **30.0%** (3/10 cases)

EF shows a dramatic increase in efficiency on successful cases, expanding significantly fewer nodes (mean ~37 nodes) than the BF baseline (which expands up to 200+ nodes and experiences state-explosion due to lack of pruning).

---

## ⚠️ Known Parameters & Tuning Options

1. **RAG Grounding Fallback:**
   * Controlled by `RAG_MIN_CHUNKS_FOR_GROUNDING` in `config.py`. When RAG retrieves sparse context (e.g. on rare diseases like CJD), the engine automatically falls back to parametric reasoning so nodes expand successfully.
2. **Contradiction Sensitivity:**
   * Controlled by `CONTRADICTION_THRESHOLD` (default `0.92`). Adjusting this changes how aggressively the engine prunes conflicting clinical claims.
3. **Saturation Thresholds:**
   * Controlled by `THETA_BY_DOMAIN` in `config.py`. Calibrated for `llama3.1:8b` (confident floor ~0.49 nats; stopping threshold ~0.55 nats).
