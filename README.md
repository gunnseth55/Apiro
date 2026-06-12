# Apiro: A Curiosity Engine for Biomedical Graph Traversal

Apiro is an agentic "AI Detective" designed to navigate biomedical knowledge graphs by chasing epistemic uncertainty (entropy) to diagnose complex clinical cases. Unlike standard RAG systems or black-box LLM chatbots, Apiro provides a verifiable, auditable, and mathematically grounded traversal path through clinical evidence to arrive at a precise differential diagnosis.

---

## 📖 The Core Vision

Imagine a clinician faced with a complex patient presenting with a rash, joint pain, and profound fatigue. Dozens of potential diseases—from common rheumatoid arthritis to rare systemic autoimmune conditions like Lupus—could fit this profile. A human doctor must:
1. **Anchor** on the solid, known clinical facts (the symptoms and lab results).
2. **Explore** the gaps in their knowledge (the differentials, rare conditions, and high-uncertainty claims) to rule out alternatives.
3. **Synthesize** a final diagnosis.

Apiro translates this clinical reasoning process into a graph traversal algorithm driven by **Information Theory**. It acts as an active detective that searches through a biomedical corpus, measuring what it knows and *what it doesn't know*, to map a path to the correct diagnosis.

---

## 📐 Architecture & Key Design Principles

Apiro's traversal strategy is defined by three main pillars:

```mermaid
graph TD
    A[Patient Case / Seeds] --> B[Depth 0: Anchor on Certainty]
    B --> C[Depth >= 1: Chase Uncertainty]
    C --> D[Contradiction & Saturation Check]
    D --> E[Synthesize Final Top-3 Differential]
```

### 1. Epistemic Uncertainty (The Entropy Engine)
Instead of semantic search, Apiro's navigation is guided by **epistemic uncertainty**.
For any claim, we query the model's confidence boundary by forcing its response into a binary `{Yes, No}` vocabulary when asked if the claim is clinically supported by context:
* If the model is certain the claim is true or false: $P(Yes) \to 1$ or $0 \implies H \to 0$ (Low Entropy).
* If the model is genuinely uncertain: $P(Yes) \approx P(No) \approx 0.5 \implies H \to \ln(2) \approx 0.693$ (High Entropy).

### 2. Depth-Aware Frontier Scoring (Anchor vs. Explore)
To prevent the engine from jumping to wild conclusions or getting lost in tangents, we implement a depth-aware scoring heuristic to sort our exploration frontier:
* **Depth 0 (Anchors):** Sort by **lowest entropy** ($1.0 - H$). The engine anchors on solid facts and lab values.
* **Depth $\ge$ 1 (Exploration):** Sort by **highest entropy** ($H$). The engine actively targets uncertainty and unexplored clinical claims.

### 3. Verification & Synthesis
* **Contradiction Detection:** Natural Language Inference (NLI) Cross-Encoders detect conflicting claims in the active belief graph to flag medical anomalies.
* **Saturation:** Traversal terminates when the change in average graph entropy stabilizes, signifying that no new information can be learned.
* **Synthesis:** The gathered evidence in the final belief graph is summarized by a reasoning model to output a ranked top-3 differential diagnosis.

---

## 🎢 Development Ups and Downs (What We Learned)

Building Apiro was not a straight path. Over successive cycles of debugging and evaluation, we hit several conceptual and technical roadblocks:

### ❌ The Tangent Trap (Blind Uncertainty)
* **What went wrong:** Originally, the engine chased uncertainty (highest entropy) immediately from the start. This caused the engine to ignore crucial clinical seed nodes (like positive lab results) and immediately follow highly uncertain, tangential claims, ending up in irrelevant "rabbit holes."
* **How we fixed it:** We introduced **Depth-Aware Frontier Scoring**. By forcing the engine to prioritize certain nodes at Depth 0, we established a firm "anchor" in clinical truth before allowing the curiosity engine to explore the high-entropy differentials.

### ❌ Entropy Semantics Drift
* **What went wrong:** During code changes, the prompt for the entropy engine drifted from measuring clinical support (`"Is this claim clinically supported?"`) to measuring relevance or interest. This destroyed the mathematical validity of the entropy signal, making it a measure of "interest" rather than true epistemic uncertainty.
* **How we fixed it:** We reverted the engine to its original clinically-supported prompt, restoring clean binary entropy boundaries.

### ❌ The Evaluator Metric Trap
* **What went wrong:** Our Phase 3 evaluator checked for a "diagnostic hit" by scanning all raw expanded graph nodes for exact substring matches of the ground truth. This resulted in false negatives (e.g., the engine successfully synthesized "Systemic Lupus Erythematosus", but the ground truth was "Neuropsychiatric systemic lupus erythematosus [NPSLE]", resulting in a FAIL).
* **How we fixed it:** We shifted the evaluation target from intermediate nodes to the final synthesized differential diagnosis. We replaced binary substring matching with a combined metric of substring checks and **SentenceTransformer semantic similarity (cosine similarity with a 0.75 threshold)**, matching clinical intents accurately.

---

## 🚀 Future Roadmap & Strategies

To scale Apiro into a production-grade biomedical tool, we have mapped out three future directions:

### 1. Medical Ontology-Based Evaluation (Deterministic Grading)
To avoid the instability of LLMs or simple semantic embedding thresholding, we can leverage standardized medical ontologies (like **SNOMED CT**, **UMLS**, or the **Disease Ontology [DOID]**):
* Map the engine's output and the ground truth to official Concept IDs.
* Query their ancestral relationships in the ontology tree.
* Award partial credit if the engine predicts a parent class (e.g., predicting `SLE` when the ground truth is `NPSLE`).
* *Implementation Tool:* Using python libraries like `pronto` to parse raw `.obo`/`.owl` ontology files, or querying the official NIH/NLM REST API.

### 2. LLM-as-a-Judge Validation
Implement a secondary, offline LLM evaluator using a reasoning model to act as a "clinical reviewer." The reviewer is presented with the patient case, the ground truth, and Apiro's top-3 differential, and provides structured feedback on clinical alignment.

### 3. Context Window Optimization
Scale the chunk retriever and expander context. Currently, the expander operates on localized contexts to manage token usage. Grouping overlapping context windows during expansion will improve graph connection consistency.

---

## 🛠️ How to Run & Test

### Installation
Ensure you have the dependencies installed:
```bash
pip install -r requirements.txt
pip install -e .
```

### Running the Traversal
To run the traversal on a specific clinical case:
```bash
python -m apiro.run --case data/synthetic_case_1.json --real-entropy
```

### Running the Phase 3 Evaluation Suite
To run the benchmark suite comparing the **Entropy-First (EF)** traversal against the **Breadth-First (BF)** baseline:
```bash
python scripts/run_phase3_eval.py --n 10
```
This script will evaluate the first 10 cases, run both search strategies, compare their efficiency (total nodes expanded to reach synthesis), and save results to `data/phase3_results.json`.
