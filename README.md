# 🩺 Apiro · AI Clinical Detective

> **Apiro** is an entropy-first AI clinical reasoning engine. Instead of relying on brute-force RAG or simple zero-shot prompting, Apiro dynamically builds and traverses a **Belief Graph** of clinical claims, actively chasing **Shannon Entropy** (epistemic uncertainty) to navigate toward highly accurate differential diagnoses.

---

## 🚀 The Core Vision

When faced with a complex patient, a clinical expert does not simply recall facts. They reason through a structured cognitive loop:
1. **Anchor on Certainty:** Establish the ground truth from solid clinical data (e.g., severe lab values, physical signs).
2. **Chase Uncertainty:** Formulate competing differentials and actively seek out information that splits the decision boundaries, ruling out alternative diagnoses.
3. **Prune Contradictions:** Resolve conflicting data points and eliminate clinical tangents.
4. **Synthesize:** Compile a targeted differential diagnosis.

Apiro translates this exact human reasoning flow into a mathematical graph traversal algorithm guided by **Information Theory**.

```
                [ Patient Vignette ]
                         │
                         ▼
           ┌───────────────────────────┐
           │ Axiom Extraction (System) │
           └─────────────┬─────────────┘
                         │
                         ▼
        ┌─────────────────────────────────┐
        │  Depth 0: Anchor on Certainty   │  ◄── Low Entropy First
        │   (Add Lab/Symptom Seed Nodes)  │
        └────────────────┬────────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │ Depth >= 1: Chase Uncertainty │  ◄── High Entropy First
         │  (Retrieve RAG & Expand Graph)│
         └───────────────┬───────────────┘
                         │
                         ▼
        ┌─────────────────────────────────┐
        │  Contradiction & Soft-Pruning   │  ◄── NLI Cross-Encoder Gauntlet
        │   (Isolate & Penalize Tangents) │
        └────────────────┬────────────────┘
                         │
                         ▼
           ┌───────────────────────────┐
           │ Saturation & Stop Check   │
           └─────────────┬─────────────┘
                         │
                         ▼
        ┌─────────────────────────────────┐
        │   Final Differential Synthesis   │
        └─────────────────────────────────┘
```

---

## 🧠 Core Concepts & Traversal Logic

### 1. Epistemic Uncertainty (The Entropy Engine)
For any clinical claim, Apiro queries the model's confidence boundary. We force the LLM to output a binary `{Yes, No}` on whether a claim is clinically supported by retrieved RAG context, and extract token-level log probabilities:

$$P(\text{Yes}) + P(\text{No}) = 1.0$$

We calculate the **Shannon Entropy** ($H$) over these token probabilities:

$$H = -P(\text{Yes})\log_2 P(\text{Yes}) - P(\text{No})\log_2 P(\text{No})$$

* **Low Entropy ($H \to 0$):** The model is certain the claim is true or false ($P(\text{Yes}) \to 1$ or $0$).
* **High Entropy ($H \to 1.0$):** The model is highly uncertain ($P(\text{Yes}) \approx P(\text{No}) \approx 0.5$). 

Apiro targets these high-entropy decision boundaries to gather information where clinical opinions or guidelines diverge.

### 2. Depth-Aware Frontier Scoring
To keep the engine anchored in clinical truth and avoid wild tangents, Apiro's frontier queue is sorted dynamically:
* **Depth 0 (Anchors):** Sorted by **lowest entropy** ($1.0 - H$). Establish the clinical foundation first.
* **Depth $\ge$ 1 (Exploration):** Sorted by **highest entropy** ($H$). Actively resolve the most uncertain clinical nodes.

### 3. Traversal Control Logic
* **Contradiction Detection:** Uses a MiniLM cross-encoder NLI model. When two active claims contradict, the weaker node receives a `CONTRADICTION_PENALTY` (default `0.8`), pushing it to the bottom of the traversal queue.
* **Rabbit Hole Prevention:** Stops expanding a path if the engine hits consecutive zero-entropy steps (signaling a loop of trivial, low-information facts).
* **Saturation Stopping:** Halts the entire traversal when rolling average entropy variance drops below a set threshold, indicating the engine has learned all it can.

### 4. Deterministic Clinical Anchoring (Axiom & NER Extraction)
Before the dynamic graph traversal begins, Apiro anchors itself in the patient's ground truth through a deterministic parsing pipeline (`AxiomExtractor`):
* **Named Entity Recognition (NER):** Uses the Hugging Face transformer model `d4data/biomedical-ner-all` to extract clinically significant medical concepts (symptoms, signs, diseases).
* **Laboratory Value Parsing:** Utilizes the `LabParser` regex rules to match numeric lab results (e.g. "Hemoglobin 9.5 g/dL") and flag abnormal bounds.
* **Negation Classification:** Filters and classifies findings as `affirmed` or `negated` (e.g., "no chest pain") to ensure only confirmed clinical facts are seeded at Depth 0.

---

## 📂 Codebase Architecture

```
.
├── apiro/
│   ├── axioms/             # Clinical text parsers and NER extractors
│   ├── corpus/             # ChromaDB vector store builders and scrapers
│   ├── entropy/            # Epistemic certainty and Shannon Entropy engine
│   ├── eval/               # Case evaluation judges and metrics
│   ├── graph/              # BeliefGraph, Node/Edge schemas, and Traversals
│   │   ├── belief_graph.py
│   │   ├── contradiction.py
│   │   ├── expander.py
│   │   ├── rabbit_hole.py
│   │   ├── saturation.py
│   │   └── traversal.py    # Main Entropy-First traversal algorithm
│   ├── config.py           # Global tuning params (Theta, Entropy temps, etc.)
│   └── run.py              # Engine runner CLI entry point
├── data/                   # Ontologies, case datasets, and local logs
├── scripts/
│   ├── app.py              # FastAPI Web UI server with live SSE streaming
│   ├── investigate.py      # Free-text clinical CLI detective
│   └── run_pmc_eval.py     # Distractor-resilience evaluation script
└── tests/                  # Pytest verification suites
```

---

## 🛠️ Onboarding & Setup

### 1. Installation
Ensure you are using Python 3.10+ in a clean virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2. Seeding the Medical Corpus
Apiro retrieves context from a local vector store to evaluate claims. The database (`data/chroma_db/`) is gitignored. Rebuild your local corpus by running:
```bash
# Ingest textbooks and medical knowledge sources
python -m apiro.corpus.build_corpus --sources textbooks medrag hpo clinvar openfda --max-records 100000
```

> [!IMPORTANT]
> To run the evaluation suite, download the **PMC-Patients-V2** dataset (`PMC-Patients-V2.json` ~837MB) from [HuggingFace Datasets](https://huggingface.co/datasets/zhaofangqi/PMC-Patients) and place it in the `data/` directory.

---

## 🚀 Running Apiro

### FastAPI Web Interface (With Live Visualizer)
Apiro includes a premium web interface featuring a live, interactive 3-column UI:
* **Left:** Clinical input form and real-time execution statistics.
* **Center:** Thought log showing clinical steps slide in as the model reasons.
* **Right:** A dynamically built D3 force-directed belief graph.

Start the FastAPI development server:
```bash
uvicorn scripts.app:app --host 127.0.0.1 --port 8000
```
Open `http://localhost:8000` in your browser.

### Free-Text CLI Investigator
Input any raw clinical scenario or patient chart dump directly into the terminal:
```bash
python scripts/investigate.py
```
Or pass the clinical vignette directly:
```bash
python scripts/investigate.py -f "45-year-old male with sudden substernal chest pain radiating to the left arm, sweating, and elevated Troponin."
```

### Run Distractor-Resilience Evaluation
Evaluate Apiro's performance against standard zero-shot LLMs and RAG baselines on real-world cases:
```bash
python scripts/run_pmc_eval.py --real
```
