"""
apiro.graph — belief graph data model and Phase 2 orchestration components.

Phase 1 (data model):
  BeliefGraph, Node, Edge

Phase 2 (orchestration):
  HypothesisTestingTraversal
  ContradictionDetector (import directly: from apiro.graph.contradiction import ContradictionDetector)

Stubs (for testing without Ollama/ChromaDB/model download):
  StubLLMClient, CyclingStubLLMClient
"""

from apiro.graph.node import Node
from apiro.graph.edge import Edge
from apiro.graph.belief_graph import BeliefGraph
from apiro.graph.traversal import HypothesisTestingTraversal, TraversalResult
from apiro.graph.stub_llm import StubLLMClient, CyclingStubLLMClient

# NOTE: ContradictionDetector is NOT imported here because it pulls in
# torch + transformers at import time (heavy dependencies, ~330MB model download).
# Import it directly when needed:
#   from apiro.graph.contradiction import ContradictionDetector

__all__ = [
    # Data model
    "Node",
    "Edge",
    "BeliefGraph",
    # Orchestration
    "HypothesisTestingTraversal",
    "TraversalResult",
    # Stubs
    "StubLLMClient",
    "CyclingStubLLMClient",
]
