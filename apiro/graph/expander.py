"""
graph/expander.py
-----------------
Given a node (a clinical hypothesis), generates 3 child hypotheses using:
  1. RAG — retrieve relevant medical context from ChromaDB
  2. LLM — generate child hypotheses conditioned on that context

THE PIPELINE (per the spec's NodeExpander.expand()):
  1. Query ChromaDB for top-6 relevant chunks for this node's claim
  2. Build a prompt: system message + retrieved context + parent claim
  3. Call the LLM → parse exactly 3 hypotheses (one per line)
  4. For each hypothesis:
     a. Compute entropy  (via EntropyEngine from Phase 1)
     b. Classify domain  (via DomainClassifier — simple keyword mapping here)
     c. Run contradiction check vs ALL existing nodes
     d. Create Node + Edge, add to graph
  5. Return list of new nodes

INTEGRATION NOTES:
  - EntropyEngine and BeliefGraph come from Phase 1 (this package)
  - ChromaDB client is passed in — we don't own its lifecycle
  - LLM client is passed in — allows easy swap (OpenAI ↔ Anthropic ↔ local)
  - DomainClassifier is inline here (simple keyword rules) — can be extracted later

STUB FALLBACKS:
  We provide StubEntropyEngine and StubChromaClient so this module is testable
  WITHOUT an Ollama instance. The real objects have the same interface.
"""

import re
import logging
from typing import Optional

from apiro.graph.node import Node
from apiro.graph.edge import Edge
from apiro.config import (
    RAG_DOMAIN_FILTER,
    N_CHILD_HYPOTHESES,
    CONTRADICTION_THRESHOLD,
    RAG_TOP_K,
)

logger = logging.getLogger(__name__)



# ── Domain classifier ─────────────────────────────────────────────────────────
# Simple keyword-based domain tagger. Good enough for Phase 2.
# Can be replaced with a classifier model later with zero interface changes.

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "genetics":        ["gene", "genetic", "mutation", "allele", "chromosom", "hereditary", "inherited"],
    "pharmacology":    ["drug", "medication", "dose", "prescribe", "administer", "mg", "contraindicated", "antibiotic", "statin"],
    "imaging":         ["ct", "mri", "x-ray", "ultrasound", "scan", "radiograph", "echo", "echocardiogram"],
    "lab":             ["blood", "serum", "plasma", "troponin", "creatinine", "bilirubin", "wbc", "rbc", "platelet", "culture"],
    "pathophysiology": ["mechanism", "pathway", "cascade", "ischemia", "inflammation", "necrosis", "apoptosis", "fibrosis"],
    "treatment":       ["surgery", "procedure", "therapy", "treatment", "intervention", "resect", "catheter", "stent"],
    "comorbidity":     ["comorbid", "concurrent", "coexisting", "secondary", "complication", "alongside"],
}

# Prototype sentences for semantic fallback classification.
# One representative sentence per domain, embedded at first call.
_DOMAIN_PROTOTYPES: dict[str, str] = {
    "genetics":        "Gene mutation and chromosomal inheritance pattern in hereditary disease.",
    "pharmacology":    "Drug dose, medication administration, contraindication and antibiotic treatment.",
    "imaging":         "CT scan, MRI, ultrasound and radiographic imaging findings.",
    "lab":             "Blood serum levels, troponin, creatinine, electrolytes and lab measurements.",
    "pathophysiology": "Disease mechanism, inflammatory cascade, ischemia and cellular necrosis pathway.",
    "treatment":       "Surgical intervention, procedure, therapy and catheter stent placement.",
    "comorbidity":     "Concurrent complication, secondary condition and coexisting disease.",
}

_domain_prototype_embeddings: dict | None = None   # lazy-loaded


def classify_domain(text: str, embedder=None) -> str:
    """
    Hybrid domain classification:
      Pass 1 — fast keyword matching (covers obvious cases).
      Pass 2 — if no keyword hits, use sentence-transformer cosine similarity
               against prototype sentences (handles edge cases like 'electrolyte
               imbalance' → 'lab' instead of defaulting to 'pathophysiology').
    """
    global _domain_prototype_embeddings

    text_lower = text.lower()
    scores = {
        domain: sum(1 for kw in keywords if kw in text_lower)
        for domain, keywords in DOMAIN_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best

    # ── Semantic fallback ─────────────────────────────────────────────────────
    if embedder is not None:
        try:
            if _domain_prototype_embeddings is None:
                protos = list(_DOMAIN_PROTOTYPES.values())
                keys   = list(_DOMAIN_PROTOTYPES.keys())
                embs   = embedder._model.encode(protos, normalize_embeddings=True)
                _domain_prototype_embeddings = {k: e for k, e in zip(keys, embs)}

            text_emb = embedder._model.encode([text], normalize_embeddings=True)[0]
            sims = {
                domain: float(text_emb @ emb)
                for domain, emb in _domain_prototype_embeddings.items()
            }
            return max(sims, key=sims.get)
        except Exception:
            pass  # fall through to default

    return "pathophysiology"


# ── Stub components (for testing without Ollama or ChromaDB) ──────────────────

class StubEntropyEngine:
    """
    Deterministic fake entropy engine for testing.

    SWAP POINT — replace with the real engine adapter:
        from apiro.entropy.engine import EntropyEngine

        class RealEntropyAdapter:
            def __init__(self):
                self._engine = EntropyEngine()
            def compute(self, claim: str, context_chunks=None) -> float:
                result = self._engine.epistemic_certainty_entropy(claim, context_chunks)
                return result if result is not None else 0.5

    The stub returns a value that slowly declines with each call to mimic
    realistic saturation behaviour in test runs.
    """

    def __init__(self, start: float = 0.85, step: float = 0.06):
        self._value = start
        self._step = step

    def compute(self, claim: str, context_chunks: list[str] | None = None) -> float:
        """
        Returns a slowly declining entropy. Each call to compute() decreases
        the value by `step` to simulate convergence, bottoming out at 0.05.
        """
        val = max(0.05, self._value)
        self._value = max(0.05, self._value - self._step)
        return round(val, 4)

    def epistemic_certainty_entropy(self, claim: str, context_chunks: list[str] | None = None) -> float:
        """Alias to compute() for compatibility with real EntropyEngine interface."""
        return self.compute(claim, context_chunks)



class StubChromaClient:
    """
    Fake ChromaDB client. Returns fixed medical context chunks.

    SWAP POINT — replace with a real ChromaDB client:
        import chromadb
        chroma_client = chromadb.Client()
        # or: chromadb.HttpClient(host="localhost", port=8000)
    """

    def query(
        self,
        collection_name: str,
        query_texts: list[str],
        n_results: int = 6,
    ) -> dict:
        """Returns stub context chunks that look like real ChromaDB output."""
        stub_docs = [
            "Troponin elevation above 99th percentile indicates myocardial injury.",
            "ST-elevation on ECG in V1-V4 leads suggests anterior STEMI.",
            "Aspirin 300mg loading dose is first-line in ACS management.",
            "Primary PCI within 90 minutes is the gold standard for STEMI.",
            "Beta-blockers reduce mortality in post-MI patients without contraindications.",
            "ACE inhibitors are indicated post-MI with reduced ejection fraction.",
        ][:n_results]
        return {"documents": [stub_docs]}


# ── LLM prompt template ───────────────────────────────────────────────────────
# Design rationale:
#   The prompt must be domain-anchored and evidence-constrained to prevent
#   topic drift (e.g. STEMI → calyceal arteritis). Three hard rules are
#   enforced explicitly in the prompt text:
#     1. Stay within the parent domain or one directly adjacent domain.
#     2. Every hypothesis must be grounded in the retrieved evidence — do not
#        introduce organ systems, conditions, or drugs not mentioned above.
#     3. Output exactly 3 short, specific, single-sentence clinical claims.
#   These rules are verbose by design: LLMs follow explicit constraints more
#   reliably than implicit style guidance.

HYPOTHESIS_PROMPT_TEMPLATE = """\
You are Apiro, a precise clinical differential-diagnosis engine.

Your task: given a parent clinical claim and retrieved medical evidence, generate
exactly 3 child hypotheses that deepen the diagnostic reasoning.

=== PARENT CLAIM ===
{claim}

=== MEDICAL DOMAIN ===
{domain}

=== RETRIEVED EVIDENCE (use ONLY what is stated here) ===
{rag_chunks}

=== STRICT RULES ===
1. DOMAIN LOCK: Every hypothesis MUST remain within the "{domain}" domain or one
   directly clinically adjacent domain (e.g. pathophysiology ↔ lab findings).
   Do NOT introduce unrelated organ systems, rare syndromes, or diseases not
   mentioned in the evidence above.
2. EVIDENCE GROUNDED: Every hypothesis must be directly derivable from the
   evidence above. Do not speculate beyond what the evidence supports.
3. CLINICAL SPECIFICITY: Each hypothesis must be a specific, testable clinical
   claim — not a vague statement. Include mechanism, finding, or intervention.
4. FORMAT: Output exactly 3 hypotheses, one per line, no numbering, no preamble,
   no explanation. Each hypothesis is a single sentence under 25 words.

=== OUTPUT (3 lines only) ===\
"""


# ── NodeExpander ──────────────────────────────────────────────────────────────

class NodeExpander:
    """
    Expands a single node into 3 child hypothesis nodes.

    Args:
        entropy_engine:        EntropyEngine (Phase 1) or StubEntropyEngine for testing.
                               Must have a .compute(claim, chunks) -> float method.
                               SWAP POINT: replace StubEntropyEngine with EntropyEngine.
        chroma_client:         ChromaDB client or StubChromaClient for testing.
        llm_client:            LLM client — must have a .chat(prompt: str) -> str method.
        collection_name:       ChromaDB collection to query (default: "medical_knowledge").
        contradiction_detector: Optional, used to flag contradictions inline.
    """

    def __init__(
        self,
        entropy_engine,
        chroma_client,
        llm_client,
        collection_name: str = "medical_knowledge",
        contradiction_detector=None,
    ):
        self.entropy_engine = entropy_engine
        self.chroma_client = chroma_client
        self.llm_client = llm_client
        self.collection_name = collection_name
        self.contradiction_detector = contradiction_detector
        self._node_counter = 0

    def _generate_node_id(self, parent_id: str, index: int) -> str:
        """Deterministic child ID: {parent_id}_c{index}"""
        self._node_counter += 1
        return f"{parent_id}_c{index}"

    def _retrieve_context(self, claim: str, domain: str = "", n_results: int = RAG_TOP_K) -> list[str]:
        """
        Query ChromaDB for the top-N most relevant medical text chunks.

        When RAG_DOMAIN_FILTER=True (config default) the query is scoped to
        chunks whose medical_domain matches `domain`. This prevents the LLM
        from generating hypotheses grounded in unrelated PubMed papers.
        """
        # Build optional metadata filter
        where: dict | None = None
        if RAG_DOMAIN_FILTER and domain:
            # Normalise domain name to match corpus metadata
            # (corpus uses 'lab' not 'lab findings'; both map cleanly)
            db_domain = domain.replace(" findings", "").lower()
            where = {"medical_domain": db_domain}

        try:
            try:
                # Embedder._collection-backed adapter: accepts where kwarg
                result = self.chroma_client.query(
                    query_texts=[claim],
                    n_results=n_results,
                    where=where,
                )
            except TypeError:
                # Stub / legacy client without where support — fall back
                result = self.chroma_client.query(
                    collection_name=self.collection_name,
                    query_texts=[claim],
                    n_results=n_results,
                )
            docs = result.get("documents", [[]])
            return docs[0] if docs else []
        except Exception as e:
            logger.warning(f"[NodeExpander] ChromaDB query failed: {e}. Continuing without context.")
            return []


    def _build_prompt(self, node: Node, chunks: list[str]) -> str:
        """
        Build the hypothesis-generation prompt.

        The prompt explicitly passes the domain and enforces evidence-only
        grounding to prevent the LLM from drifting off-topic across hops.
        An empty chunk list is an honest signal — the evidence block will
        say "No context retrieved" and the model will stay conservative.
        """
        if chunks:
            rag_text = "\n".join(f"  [{i+1}] {chunk.strip()}" for i, chunk in enumerate(chunks))
        else:
            rag_text = "  [No context retrieved — be conservative, stay close to parent claim.]"
        return HYPOTHESIS_PROMPT_TEMPLATE.format(
            claim=node.claim,
            domain=node.domain,
            rag_chunks=rag_text,
        )

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM and return raw text response."""
        try:
            return self.llm_client.chat(prompt)
        except Exception as e:
            logger.error(f"[NodeExpander] LLM call failed: {e}")
            return ""

    def _parse_hypotheses(self, llm_output: str) -> list[str]:
        """
        Parse the LLM's output into exactly 3 hypothesis strings.
        Defensive: strips numbering, drops empty lines, pads if fewer than 3 returned.
        """
        lines = llm_output.strip().split("\n")
        hypotheses = []
        for line in lines:
            clean = re.sub(r"^[\d]+[\.)] \s*|^[-*•]\s*", "", line.strip())
            if clean:
                hypotheses.append(clean)

        if len(hypotheses) > 3:
            hypotheses = hypotheses[:3]

        while len(hypotheses) < 3:
            hypotheses.append(
                f"[Expansion failed for: {hypotheses[0][:40] if hypotheses else 'unknown'}]"
            )

        return hypotheses

    def expand(self, node: Node, graph) -> list[Node]:
        """
        Main expansion method — called by traversal.py for each frontier node.

        Steps:
          1. Retrieve RAG context
          2. Build prompt
          3. Call LLM
          4. Parse hypotheses
          5. For each hypothesis: compute entropy, classify domain,
             check contradictions, create Node + Edge, add to graph
          6. Return list of 3 new nodes
        """
        logger.info(f"[NodeExpander] Expanding: '{node.claim[:60]}'")

        # Step 1: RAG retrieval — scoped to node.domain when RAG_DOMAIN_FILTER=True
        chunks = self._retrieve_context(node.claim, domain=node.domain)


        # Step 2 & 3: Prompt + LLM
        prompt = self._build_prompt(node, chunks)
        raw_output = self._call_llm(prompt)

        # Step 4: Parse
        hypotheses = self._parse_hypotheses(raw_output)
        new_nodes = []

        for i, hypothesis in enumerate(hypotheses):
            # Step 5a: Epistemic certainty entropy.
            # Measures uncertainty at the clinical decision boundary:
            # "Given the RAG evidence, is this hypothesis clinically supported?"
            # First-token Shannon entropy over Yes/No — the core Apiro signal.
            entropy = self.entropy_engine.epistemic_certainty_entropy(hypothesis, chunks)
            # Guard: epistemic_certainty_entropy returns None on Ollama timeout.
            # Fall back to ln(2) = 0.693 (max binary uncertainty) so the node
            # stays high-priority in the frontier and Node.__post_init__ doesn't crash.
            if entropy is None:
                entropy = 0.693

            domain = classify_domain(hypothesis, embedder=getattr(self.chroma_client, '_emb', None))

            # Step 5c: Create the node (uses main's full Node dataclass)
            child_id = self._generate_node_id(node.id, i)
            child_node = Node(
                id=child_id,
                claim=hypothesis,
                entropy_score=entropy,
                domain=domain,
                depth=node.depth + 1,
                parent_id=node.id,
            )

            # Step 5d: Create the edge
            edge = Edge(parent_id=node.id, child_id=child_id)

            if self.contradiction_detector:
                for existing in list(graph.nodes.values()):
                    if not self.contradiction_detector.should_check(hypothesis, existing.claim):
                        continue
                    result = self.contradiction_detector.check(hypothesis, existing.claim)
                    if result.label == "contradiction" and result.score > CONTRADICTION_THRESHOLD:
                        edge.contradiction_flag = True
                        logger.info(
                            f"[NodeExpander] Contradiction flagged: "
                            f"'{hypothesis[:40]}' vs '{existing.claim[:40]}'"
                        )
                        break


            # Step 5f: Add to graph
            # add_node() may silently drop the node if it exceeds max_depth or
            # max_nodes budget. Only add the edge if the node was actually accepted.
            graph.add_node(child_node)
            if child_id in graph.nodes:
                graph.add_edge(edge)
            else:
                logger.debug(
                    f"[NodeExpander] Node '{child_id}' dropped by graph "
                    f"(depth={child_node.depth} or budget exceeded) — skipping edge."
                )
            new_nodes.append(child_node)
            logger.debug(
                f"  → Child {i}: '{hypothesis[:60]}' "
                f"(entropy={entropy:.3f}, domain={domain})"
            )

        return new_nodes

    def synthesize_differential(self, graph, top_k: int = 15) -> list[str]:
        """
        Synthesize a final differential diagnosis from the belief graph.

        Only high-signal nodes are passed to the LLM:
          - Rabbit-hole nodes are excluded (they are known dead-ends).
          - Contradiction-flagged nodes are excluded (actively disputed claims).
          - The remaining nodes are sorted by entropy descending and capped at
            top_k (default 15) so the synthesizer sees the most informationally
            rich, unresolved claims — not a dump of every node including noise.

        Args:
            graph:  The BeliefGraph containing gathered evidence.
            top_k:  Max number of high-entropy clean nodes to pass to the LLM.

        Returns:
            A list of the top 3 most likely specific clinical diagnoses.
        """
        logger.info("[NodeExpander] Synthesizing final differential diagnosis...")

        # Identify contradiction-flagged node IDs so we can exclude them.
        contradiction_ids: set[str] = set()
        for edge in graph.edges:
            if getattr(edge, 'contradiction_flag', False):
                contradiction_ids.add(edge.child_id)
                contradiction_ids.add(edge.parent_id)

        # Collect only clean, high-signal nodes.
        clean_nodes = [
            n for n in graph.nodes.values()
            if not n.is_rabbit_hole
            and n.id not in contradiction_ids
        ]

        # Sort by entropy descending — highest uncertainty = most diagnostically
        # interesting — and cap at top_k.
        clean_nodes.sort(key=lambda n: n.entropy_score or 0.0, reverse=True)
        top_nodes = clean_nodes[:top_k]

        logger.info(
            f"[NodeExpander] Synthesis using {len(top_nodes)}/{graph.node_count()} nodes "
            f"(excluded {graph.node_count() - len(top_nodes)} rabbit-holes/contradictions)."
        )

        if not top_nodes:
            logger.warning("[NodeExpander] No clean nodes available for synthesis — using all nodes.")
            top_nodes = list(graph.nodes.values())[:top_k]

        # Remove duplicate claims while preserving entropy-rank order.
        seen: set[str] = set()
        unique_claims: list[str] = []
        for n in top_nodes:
            if n.claim not in seen:
                unique_claims.append(n.claim)
                seen.add(n.claim)

        evidence_text = "\n".join(f"  - {claim}" for claim in unique_claims)

        prompt = (
            "You are Apiro, a precise clinical differential-diagnosis engine.\n\n"
            "Your task: given the following high-signal clinical evidence (pre-filtered to remove"
            " known dead-ends and contradictions), generate the top 3 most likely specific"
            " clinical diagnoses.\n\n"
            "=== HIGH-SIGNAL GATHERED EVIDENCE ===\n"
            f"{evidence_text}\n\n"
            "=== STRICT RULES ===\n"
            "1. Output exactly 3 diagnoses, one per line.\n"
            "2. Provide only the specific disease name (e.g., 'Type 1 autoimmune pancreatitis')."
            " Do not include preamble, numbering, explanations, or mechanism.\n"
            "3. Rank them from most likely to least likely.\n\n"
            "=== OUTPUT (3 lines only) ==="
        )

        raw_output = self._call_llm(prompt)
        diagnoses = self._parse_hypotheses(raw_output)

        logger.info(f"[NodeExpander] Synthesis complete: {diagnoses}")
        return diagnoses
