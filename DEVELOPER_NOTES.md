# Developer Notes: Project Files Map & Run Instructions

This document is a developer reference to help incoming contributors distinguish between core production assets, legacy utility scripts, and temporary debug artifacts.

---

## 🗺️ File Classification Map

To keep the repository clean, avoid editing legacy scripts or committing temporary outputs. Use the guide below to understand what is what.

### 1. Core Production Assets (Do NOT Delete)
These are the essential building blocks of the Apiro platform:
* **`apiro/`**: The core package directory containing all source code (entropy calculation, graph schemas, NLI detection, search traversals).
* **`tests/`**: The unit test suite. Run this regularly via `pytest tests/`.
* **`scripts/run_phase3_eval.py`**: The current active benchmark suite entry point.
* **`requirements.txt` & `pyproject.toml`**: Package dependencies and distribution configurations.

### 2. Temporary / Debug Outputs (Safe to Delete / Ignore)
These files are generated dynamically when running experiments or traversals and should typically be excluded from commits:
* **`data/logs/`**: Directory containing raw console logs.
* **`data/traversal_log_*.jsonl`**: Step-by-step logs of search traversals (e.g. `traversal_log_ef_eval.jsonl`, `traversal_log_synthetic_case_1.jsonl`).
* **`data/graph_*.json`**: Exported raw belief graph node and edge dumps.
* **`data/report.md` & `data/real_traversal_evaluation_report.md`**: Ad-hoc markdown logs generated during prior test executions.

### 3. Legacy & Diagnostic Utility Scripts (Use with Caution)
These scripts were written for specific diagnostics or setup phases. They are not part of the live runtime:
* **`scripts/repair_corpus.py`**: A one-time utility used to fix double-encoding bugs inside the vector database.
* **`scripts/inspect_metadata.py`**: A diagnostic script used to print metadata fields from the local ChromaDB database.
* **`scripts/dry_run.py`**: Early prototype testing script for verifying basic LLM connectivity.
* **`scripts/run_experiment.py` & `scripts/evaluate_real_traversal.py`**: Early benchmarking scripts superseded by the Phase 3 framework.

---

## 🗄️ Ingesting and Building the Medical Corpus

The built database (`data/chroma_db/`) and downloaded clinical corpora (`data/corpus/`) contain large datasets and vectors. They are **excluded from the git repository** via `.gitignore` to prevent bloating version control. 

When setting up the project for the first time, you must run the build script to fetch raw records, split them into overlapping text chunks, generate embeddings, and populate your local vector database. **To ensure a statistically viable and rich corpus, you should load at least 50k to 100k records:**

```bash
# Ingest clinical textbooks (requires sufficient volume for graph paths)
python -m apiro.corpus.build_corpus --sources textbooks --max-records 50000

# Ingest multiple medical sources (MedRAG/PubMed, HPO, ClinVar, OpenFDA) with full record volume
python -m apiro.corpus.build_corpus --sources medrag hpo clinvar openfda --max-records 100000

# Rebuild the database from scratch (deletes existing collection first)
python -m apiro.corpus.build_corpus --sources textbooks medrag --clear --max-records 100000
```

* **Valid Sources:** `textbooks`, `medrag` (HuggingFace MedRAG/PubMed), `hpo` (Human Phenotype Ontology), `clinvar` (pathogenic variants), `openfda` (drug labels).
* **API Keys:** None of the default scrapers require API keys or registration.

---

## 🧹 Repository Cleanup

To clean up temporary logs, belief graph exports, and caches from your local working directory, you can run:

```bash
# Clean up temporary JSONL traversal logs and graph exports
rm -f data/traversal_log_*.jsonl
rm -f data/graph_*.json
rm -f data/*.md

# Clean up Python cache files
find . -type d -name "__pycache__" -exec rm -r {} +
find . -type d -name ".pytest_cache" -exec rm -r {} +
```

---

## 🚀 How to Run the Project Properly

### A. Run a Single Case Traversal (Visual Output)
To execute the curiosity engine on a single clinical case and view the path logs:
```bash
python -m apiro.run --case data/synthetic_case_1.json --real-entropy
```
* Use `--real-entropy` to make live API calls. Omitting it runs the traversal in deterministic Mock mode using the stub client.

### B. Run the Active Evaluation Suite
To execute the benchmark comparing the Entropy-First engine against the Breadth-First baseline:
```bash
# Run evaluation on first 10 cases
python scripts/run_phase3_eval.py --n 10
```
* The results are written to `data/phase3_results.json` and a traversal log is generated at `data/traversal_log_ef_eval.jsonl`.
