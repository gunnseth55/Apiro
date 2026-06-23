# Apiro Biomedical — Implementation Plan

## Current State (Completed)

| Item | Status |
|---|---|
| Calibration experiment (60 Qs × 2 models × 3 temps × 10 samples) | ✅ Done |
| Token entropy validated as primary signal (B/A ratio 1.6–1.8×) | ✅ Done |
| Semantic dispersion dropped (flat across all groups) | ✅ Decided |
| Temperature sensitivity via logprobs dropped (Ollama returns unnormalized probs) | ✅ Decided |
| `data/raw_results.json`, `data/report.md`, `figures/fig1–4.png` | ✅ Done |

**Starting point for build phase:** Week 1, Phase 1.

---

## Phase 1 — Corpus & Infrastructure
### Weeks 1–6

### Goal
Reproducible corpus pipeline + working ChromaDB instance + verified logprob extraction.

---

### 1.1 — Dependency additions

Add to `requirements.txt`:
```
chromadb>=0.5.0
langchain>=0.2.0
langchain-community>=0.2.0
langchain-chroma>=0.1.0
networkx>=3.3
pyvis>=0.3.2
fastapi>=0.111.0
uvicorn>=0.30.0
pydantic>=2.7.0
biopython>=1.83
requests-cache>=1.2.0
```

---

### 1.2 — Directory structure to create

```
apiro/
├── corpus/
│   ├── scrapers/
│   │   ├── pubmed_scraper.py        # Biopython Entrez → chunks
│   │   ├── omim_scraper.py          # OMIM API → entries
│   │   ├── clinvar_scraper.py       # ClinVar FTP → VCF parse
│   │   └── drugbank_scraper.py      # DrugBank XML → summaries
│   ├── chunker.py                   # sentence splitter + overlap
│   ├── embedder.py                  # all-mpnet-base-v2 → ChromaDB ingest
│   └── build_corpus.py              # orchestrator CLI
├── graph/
│   ├── node.py                      # Node dataclass
│   ├── edge.py                      # Edge dataclass
│   └── belief_graph.py              # BeliefGraph(NetworkX wrapper)
├── entropy/
│   └── engine.py                    # EntropyEngine (logprob → H)
├── api/
│   └── main.py                      # FastAPI app skeleton
├── tests/
│   ├── test_corpus.py
│   └── test_graph.py
└── config.py                        # all constants
```

---

### 1.3 — Corpus pipeline (`corpus/`)

**`corpus/scrapers/pubmed_scraper.py`**
- Use `Bio.Entrez` with search terms per medical domain
- Fetch abstracts in batches of 500 via `efetch`
- Target: 300k–500k abstracts
- Metadata per chunk: `{pmid, title, condition, source_db:"pubmed", medical_domain, evidence_level}`

**`corpus/scrapers/omim_scraper.py`**
- OMIM API key required (free academic): `https://api.omim.org/api/entry`
- Fetch gene-disease associations, phenotype summaries
- Metadata: `{mim_number, gene, phenotype, source_db:"omim"}`

**`corpus/scrapers/clinvar_scraper.py`**
- Download ClinVar XML from NCBI FTP
- Extract pathogenic/likely-pathogenic variants + clinical significance
- Metadata: `{variant_id, gene, condition, significance, source_db:"clinvar"}`

**`corpus/scrapers/drugbank_scraper.py`**
- DrugBank open data XML (free download)
- Extract drug summaries, mechanism, interactions, contraindications
- Metadata: `{drugbank_id, name, mechanism, source_db:"drugbank"}`

**`corpus/chunker.py`**
- Split texts to ~300-token chunks with 50-token overlap (sentence-boundary aware)
- Use `nltk.sent_tokenize` or `spacy`

**`corpus/embedder.py`**
- Load `all-mpnet-base-v2`
- Batch embed (batch_size=256) → insert to ChromaDB collection `apiro_corpus`
- Store full metadata dict alongside each embedding

**`corpus/build_corpus.py`**
- CLI: `python corpus/build_corpus.py --sources pubmed omim clinvar drugbank`
- Runs scrapers → chunker → embedder in sequence
- Outputs progress to `data/corpus_stats.json`

---

### 1.4 — Entropy engine (`entropy/engine.py`)

This already works from `run_experiment.py`. Extract into a reusable class:

```python
class EntropyEngine:
    def __init__(self, model: str, ollama_url: str)
    def first_token_entropy(self, prompt: str, temperature: float) -> float
    def temperature_corrected_entropy(self, prompt: str) -> float
        # Query at T=0.3, 0.7, 1.2
        # H_corrected = 0.6*H(0.3) + 0.3*H(0.7) + 0.1*H(1.2)
        # Highest weight on T=0.3 (least noise, purest signal)
```

> **Note:** Temperature correction is for *weighting certainty*, not for measuring temperature sensitivity (that's broken in the logprob API). It's still valid as a noise-reduction technique.

---

### 1.5 — Belief graph (`graph/`)

**`graph/node.py`**
```python
@dataclass
class Node:
    id: str
    claim: str
    domain: str            # pathophysiology|pharmacology|genetics|imaging|lab|treatment|comorbidity
    entropy_score: float
    resolved: bool = False
    is_rabbit_hole: bool = False
    depth: int = 0
    sources: list[str] = field(default_factory=list)  # pmids
    metadata: dict = field(default_factory=dict)
```

**`graph/edge.py`**
```python
@dataclass
class Edge:
    parent_id: str
    child_id: str
    relation: str          # supports|contradicts|refines|expands
    contradiction_flag: bool = False
    confidence: float = 1.0
```

**`graph/belief_graph.py`**
```python
class BeliefGraph:
    def __init__(self)
    def add_node(self, node: Node) -> None
    def add_edge(self, edge: Edge) -> None
    def get_frontier(self) -> list[Node]      # unresolved nodes, sorted by entropy desc
    def mark_resolved(self, node_id: str) -> None
    def get_entropy_trend(self, window: int = 5) -> float   # slope of last N entropies
    def to_networkx(self) -> nx.DiGraph
    def export_json(self, path: Path) -> None
```

---

### Phase 1 Deliverable checklist
- [ ] `python corpus/build_corpus.py` runs end-to-end for at least PubMed
- [ ] ChromaDB query returns top-6 chunks with metadata for a test medical phrase
- [ ] `EntropyEngine.temperature_corrected_entropy("chest pain radiating to left arm")` returns a float
- [ ] `BeliefGraph` unit tests pass (add/get/frontier/export)

---

## Phase 2 — Core Engine: Entropy + Graph
### Weeks 5–10

### Goal
End-to-end simulation on 3 synthetic patient cases. Entropy curve declines to saturation. At least 1 rabbit hole event fires correctly.

---

### 2.1 — Node expansion pipeline (`graph/expander.py`)

```python
class NodeExpander:
    def __init__(self, entropy_engine, chroma_client, llm_model)

    def expand(self, node: Node, graph: BeliefGraph) -> list[Node]:
        # 1. RAG retrieval: top-6 chunks from ChromaDB for node.claim
        # 2. Build prompt: system + retrieved context + "Generate 3 child hypotheses"
        # 3. LLM call → parse 3 hypotheses
        # 4. For each hypothesis:
        #    a. Compute entropy via EntropyEngine
        #    b. Classify domain via DomainClassifier
        #    c. Run contradiction check vs existing nodes
        #    d. Create Node, create Edge, insert to graph
        # 5. Return list of new nodes
```

**Prompt template for hypothesis generation:**
```
You are a clinical reasoning engine.
Parent claim: {node.claim}
Medical domain: {node.domain}
Retrieved evidence:
{rag_chunks}

Generate exactly 3 child hypotheses that either:
- Support or refine the parent claim with more specificity
- Represent a competing differential diagnosis
- Identify a complication or comorbidity

Format: one hypothesis per line, no numbering, no preamble.
```

---

### 2.2 — Saturation stopping condition (`graph/saturation.py`)

```python
class SaturationDetector:
    def __init__(self, theta: float = 0.25, window: int = 5, max_variance: float = 0.04)

    def is_saturated(self, graph: BeliefGraph) -> bool:
        # Get entropy of last `window` expanded nodes
        # Pass if ALL THREE hold:
        #   avg_entropy < theta
        #   variance < max_variance
        #   trend_coefficient <= 0  (entropy not rising)
        ...

    def get_status(self, graph: BeliefGraph) -> dict
        # Returns {saturated, avg_entropy, variance, trend}
```

Domain-specific theta defaults:
```python
THETA_BY_DOMAIN = {
    "pathophysiology": 0.30,
    "pharmacology":    0.25,
    "genetics":        0.20,   # rare disease — explore more
    "imaging":         0.25,
    "lab":             0.20,
    "treatment":       0.25,
    "comorbidity":     0.35,   # comorbidities are inherently uncertain
}
```

---

### 2.3 — Rabbit hole detector (`graph/rabbit_hole.py`)

```python
class RabbitHoleDetector:
    def __init__(self, min_depth: int = 3, reversal_window: int = 4)

    def check(self, graph: BeliefGraph, current_node: Node) -> bool:
        # Fire if:
        #   current depth >= min_depth
        #   AND entropy trend_coefficient turned POSITIVE after initial decline
        #   (i.e., the last `reversal_window` entropies are rising)
        ...

    def flag_rabbit_hole(self, node: Node, graph: BeliefGraph) -> None
        # Mark node.is_rabbit_hole = True, log path
```

---

### 2.4 — Contradiction detector (`graph/contradiction.py`)

```python
class ContradictionDetector:
    def __init__(self, model_name: str = "cross-encoder/nli-MiniLM2-L6-H768")
    # Fine-tuned on MedNLI available on HuggingFace
    # Full RoBERTa-MNLI is 1.3GB — use MiniLM for speed, swap for paper eval

    def check(self, claim_a: str, claim_b: str) -> dict:
        # Returns {label: entailment|neutral|contradiction, score: float}

    def add_negation_layer(self, text: str) -> str:
        # Pre-process: detect clinical negation (no, without, denies, absent)
        # using NegEx pattern list before NLI check
```

---

### 2.5 — Main traversal loop (`graph/traversal.py`)

```python
class ApiroTraversal:
    def __init__(self, expander, saturation, rabbit_hole, contradiction)

    def run(self, seed_nodes: list[Node], max_depth: int = 8) -> BeliefGraph:
        graph = BeliefGraph()
        for seed in seed_nodes:
            graph.add_node(seed)

        while True:
            if saturation.is_saturated(graph):
                break

            frontier = graph.get_frontier()   # sorted by entropy DESC
            if not frontier:
                break

            node = frontier[0]   # highest entropy node first

            if rabbit_hole.check(graph, node):
                rabbit_hole.flag_rabbit_hole(node, graph)
                node = frontier[1] if len(frontier) > 1 else None
                if not node:
                    break

            new_nodes = expander.expand(node, graph)
            graph.mark_resolved(node.id)

            for new_node in new_nodes:
                # contradiction check vs all existing nodes
                for existing in graph.nodes.values():
                    result = contradiction.check(new_node.claim, existing.claim)
                    if result['label'] == 'contradiction' and result['score'] > 0.85:
                        edge = Edge(..., contradiction_flag=True)

        return graph
```

---

### Phase 2 Deliverable checklist
- [ ] `python -m apiro.run --case synthetic_case_1.json` completes without error
- [ ] `graph.export_json()` produces valid node/edge JSON
- [ ] Entropy values per node logged to `data/traversal_log.jsonl`
- [ ] At least 1 of 3 synthetic cases fires `SaturationDetector`
- [ ] At least 1 of 3 synthetic cases fires `RabbitHoleDetector`
- [ ] Contradiction pair (e.g. "give aspirin" vs "aspirin contraindicated") flags correctly

---

## Phase 3 — Biomedical Adaptation & Evaluation
### Weeks 9–15

### Goal
Evaluate on 10 MIMIC-III cases. Entropy-first outperforms breadth-first in ≥7/10 cases.

---

### 3.1 — Patient finding seed nodes (`corpus/mimic_adapter.py`)

```python
@dataclass
class PatientFinding:
    finding_type: str    # symptom|lab|vital|history|imaging
    value: str
    units: str = ""
    confidence: float = 1.0

def findings_to_seed_nodes(findings: list[PatientFinding]) -> list[Node]:
    # Convert patient findings to initial belief graph nodes
    # Each finding → 1 seed node with entropy computed from it
```

MIMIC-III access: use PhysioNet credentialed access or the public MIMIC-III demo dataset (100 patients, freely available without credentialing).

---

### 3.2 — Domain classifier (`nlp/domain_classifier.py`)

```python
class DomainClassifier:
    # Use zero-shot classification with BioBERT or
    # facebook/bart-large-mnli as a cheap starting point
    DOMAINS = [
        "pathophysiology", "pharmacology", "genetics",
        "imaging", "lab findings", "treatment", "comorbidity"
    ]

    def classify(self, text: str) -> str:
        # Returns the most likely domain label
```

---

### 3.3 — Evaluation harness (`eval/evaluator.py`)

Metrics per case:
1. **Diagnostic hit**: does correct diagnosis appear as a node before saturation? (binary)
2. **Path length**: how many node expansions before correct diagnosis appears?
3. **Entropy curve shape**: is the curve monotonically declining? (AUC of decline)
4. **Rabbit hole rate**: number of rabbit hole events fired
5. **Baseline comparison**: same case run with breadth-first traversal — compare path lengths

```python
class CaseEvaluator:
    def evaluate_case(self, case: dict, graph: BeliefGraph, ground_truth: str) -> dict
    def compare_traversal_orders(self, case: dict) -> dict
        # Run entropy-first vs breadth-first, return path_length comparison
```

---

### 3.4 — Saturation theta tuning

Grid search `theta ∈ [0.15, 0.45]` step 0.05 per domain on the 10 evaluation cases.
Write results to `data/theta_tuning.json`.

---

### Phase 3 Deliverable checklist
- [ ] MIMIC-III demo cases loaded as seed node lists
- [ ] Domain classifier returns correct domain for 10 test phrases
- [ ] `eval/evaluator.py` produces per-case metric dict
- [ ] Entropy-first outperforms breadth-first in ≥7/10 cases on path length
- [ ] Rabbit hole fires correctly on ≥2 comorbidity cases
- [ ] Theta values per domain documented in `data/theta_tuning.json`

---

## Phase 4 — Output, Interface & Paper
### Weeks 14–20

### Goal
Working Streamlit demo. Complete paper draft. Public GitHub repo.

---

### 4.1 — Report generator (`output/report_generator.py`)

```python
class DiagnosticReport:
    def from_graph(self, graph: BeliefGraph, case_metadata: dict) -> dict:
        return {
            "peak_uncertainty_domain": ...,   # domain with highest mean entropy
            "most_generative_finding": ...,   # node that spawned most children
            "unresolved_core_node": ...,       # highest entropy unsaturated node
            "rabbit_hole_paths": [...],
            "differential_diagnosis": [...],   # sorted by entropy desc, with sources
        }

    def to_markdown(self, report: dict) -> str
    def to_pdf(self, report: dict, path: Path) -> None    # use reportlab or weasyprint
```

---

### 4.2 — FastAPI backend (`api/main.py`)

Endpoints:
```
POST /cases/           → submit patient findings → returns case_id
GET  /cases/{id}/graph → returns graph JSON (nodes + edges)
GET  /cases/{id}/status → {state: running|saturated|rabbit_hole, entropy_trend}
GET  /cases/{id}/report → full diagnostic report JSON
WS   /cases/{id}/stream → WebSocket, push node additions in real time
```

---

### 4.3 — Streamlit demo (`ui/app.py`)

Pages:
1. **Upload**: paste/type patient findings → submit → case_id created
2. **Live graph**: PyVis graph renders, nodes added in real time via polling
3. **Entropy curve**: Plotly line chart, updates every 2s
4. **Saturation event**: banner fires when `SaturationDetector` trips
5. **Report**: downloadable PDF diagnostic report

---

### 4.4 — Paper structure

```
1. Introduction — clinical diagnostic uncertainty + motivation
2. Related Work — DR.KNOWS, ArgMed-Agents, entropy in NLP
3. Calibration Experiment — the 3-group entropy validation (Figure 1 = fig1_distributions.png)
4. Architecture — 6-layer stack diagram
5. Novel Contributions:
   5.1 Entropy as traversal heuristic
   5.2 Epistemic saturation stopping condition
   5.3 Rabbit hole detection
6. Evaluation — 10 MIMIC-III cases, comparison table
7. Discussion — Group C finding (graded signal), semantic layer failure, limitations
8. Conclusion
```

---

### Phase 4 Deliverable checklist
- [ ] `output/report_generator.py` produces valid markdown + PDF for a test case
- [ ] FastAPI server starts, all endpoints respond
- [ ] Streamlit demo runs locally: `streamlit run ui/app.py`
- [ ] Live graph updates visible in browser during traversal
- [ ] Paper draft Section 3 (Calibration) complete — uses real figures
- [ ] GitHub repo public with `README.md`, `requirements.txt`, corpus pipeline instructions

---

## Summary: What to do next, in order

| # | Task | File(s) | Week |
|---|---|---|---|
| 1 | Install new dependencies | `requirements.txt` | 1 |
| 2 | Create directory structure | `mkdir -p ...` | 1 |
| 3 | Build PubMed scraper | `corpus/scrapers/pubmed_scraper.py` | 1–2 |
| 4 | Build chunker + embedder | `corpus/chunker.py`, `corpus/embedder.py` | 2 |
| 5 | Stand up ChromaDB | `corpus/embedder.py` | 2 |
| 6 | Extract EntropyEngine from run_experiment.py | `entropy/engine.py` | 2 |
| 7 | Implement BeliefGraph | `graph/node.py`, `graph/edge.py`, `graph/belief_graph.py` | 3 |
| 8 | Write graph unit tests | `tests/test_graph.py` | 3 |
| 9 | Build OMIM/ClinVar/DrugBank scrapers | `corpus/scrapers/` | 3–4 |
| 10 | NodeExpander with RAG + LLM | `graph/expander.py` | 5–6 |
| 11 | SaturationDetector | `graph/saturation.py` | 6 |
| 12 | RabbitHoleDetector | `graph/rabbit_hole.py` | 6–7 |
| 13 | ContradictionDetector | `graph/contradiction.py` | 7 |
| 14 | Main traversal loop | `graph/traversal.py` | 7–8 |
| 15 | Run 3 synthetic cases end-to-end | manual test | 8–9 |
| 16 | MIMIC adapter + domain classifier | `corpus/mimic_adapter.py`, `nlp/domain_classifier.py` | 9–10 |
| 17 | Evaluation harness | `eval/evaluator.py` | 10–12 |
| 18 | Run 10 MIMIC cases, tune theta | `data/theta_tuning.json` | 12–14 |
| 19 | Report generator | `output/report_generator.py` | 14–15 |
| 20 | FastAPI backend | `api/main.py` | 15–16 |
| 21 | Streamlit demo | `ui/app.py` | 16–18 |
| 22 | Paper draft | `paper/apiro_paper.md` | 18–20 |
| 23 | Public GitHub + README | — | 20 |

---

## Key architectural decisions (locked)

| Decision | Rationale |
|---|---|
| Token entropy only (no semantic dispersion) | Experiment showed dispersion flat across all groups |
| Temperature weighting not temperature sensitivity | Logprob API returns unnormalized scores; T-correction still valid for noise reduction |
| MedNLI-tuned MiniLM for contradiction, not full RoBERTa | Speed on CPU; swap for paper evaluation runs |
| MIMIC-III demo dataset first, full MIMIC later | No credentialing required, 100 cases sufficient for evaluation |
| Entropy-first traversal as primary, breadth-first as baseline | This is the core empirical claim to validate |
