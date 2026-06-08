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

def classify_domain(text: str) -> str:
    """
    Rule-based domain classification. Returns the domain with the most keyword hits.
    Falls back to 'pathophysiology' as the default medical domain.
    """
    text_lower = text.lower()
    scores = {
        domain: sum(1 for kw in keywords if kw in text_lower)
        for domain, keywords in DOMAIN_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "pathophysiology"


# ── Stub components (for testing without Ollama or ChromaDB) ──────────────────

class StubEntropyEngine:
    """
    Deterministic fake entropy engine for testing.

    SWAP POINT — replace with the real engine:
        from apiro.entropy.engine import EntropyEngine
        entropy_engine = EntropyEngine()
        # Interface: entropy_engine.temperature_corrected_entropy(claim: str) -> Optional[float]

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

HYPOTHESIS_PROMPT_TEMPLATE = """\
You are a clinical reasoning engine.
Parent claim: {claim}
Medical domain: {domain}
Retrieved evidence:
{rag_chunks}

Generate exactly 3 child hypotheses that either:
- Support or refine the parent claim with more specificity
- Represent a competing differential diagnosis
- Identify a complication or comorbidity

Format: one hypothesis per line, no numbering, no preamble.\
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

    def _retrieve_context(self, claim: str, n_results: int = 6) -> list[str]:
        """Query ChromaDB for the top-N most relevant medical text chunks."""
        try:
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
        """Fill the prompt template with node data and retrieved chunks."""
        rag_text = "\n".join(f"- {chunk}" for chunk in chunks) if chunks else "No context retrieved."
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

        # Step 1: RAG retrieval
        chunks = self._retrieve_context(node.claim)

        # Step 2 & 3: Prompt + LLM
        prompt = self._build_prompt(node, chunks)
        raw_output = self._call_llm(prompt)

        # Step 4: Parse
        hypotheses = self._parse_hypotheses(raw_output)
        new_nodes = []

        for i, hypothesis in enumerate(hypotheses):
            # Step 5a: Entropy
            # SWAP POINT: StubEntropyEngine.compute() → EntropyEngine.temperature_corrected_entropy()
            # The stub's interface mirrors the real engine's .compute(claim, chunks) call.
            entropy = self.entropy_engine.compute(hypothesis, chunks)

            # Step 5b: Domain classification
            domain = classify_domain(hypothesis)

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

            # Step 5e: Lightweight contradiction check (full check runs in traversal.py)
            if self.contradiction_detector:
                for existing in list(graph.nodes.values()):
                    result = self.contradiction_detector.check(hypothesis, existing.claim)
                    if result.label == "contradiction" and result.score > 0.85:
                        edge.contradiction_flag = True
                        logger.info(
                            f"[NodeExpander] Contradiction flagged: "
                            f"'{hypothesis[:40]}' vs '{existing.claim[:40]}'"
                        )
                        break

            # Step 5f: Add to graph
            graph.add_node(child_node)
            graph.add_edge(edge)
            new_nodes.append(child_node)
            logger.debug(
                f"  → Child {i}: '{hypothesis[:60]}' "
                f"(entropy={entropy:.3f}, domain={domain})"
            )

        return new_nodes
