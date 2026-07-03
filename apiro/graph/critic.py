"""
graph/critic.py
------------------
Global Critic to dynamically halt graph traversal once sufficient diagnostic
evidence has been accumulated.
"""

import logging
from apiro.graph.belief_graph import BeliefGraph

logger = logging.getLogger(__name__)

CRITIC_PROMPT_TEMPLATE = """\
You are an expert clinical diagnostician overseeing an automated diagnostic reasoning engine.
The engine has been generating hypotheses based on the patient's case presentation.

=== PATIENT CLINICAL PRESENTATION ===
{case_context}

=== CURRENT TOP HYPOTHESES ===
{top_nodes}

Your task: Evaluate if there is sufficient evidence to confidently halt the search and declare a primary diagnosis, or if critical diagnostic information is still missing.
Are the current top hypotheses specific and comprehensive enough to explain the patient's presentation without needing further exploration?

Answer YES or NO on the first line.
On the second line, provide a brief 1-sentence reason.
"""

class CriticEngine:
    def __init__(self, llm_client):
        self.llm = llm_client

    def evaluate_halting(self, graph: BeliefGraph, vignette: str = None, top_k: int = 5) -> bool:
        """
        Evaluate if the graph has converged on a diagnosis.
        Returns True if the search should halt, False otherwise.
        """
        if not vignette:
            return False
            
        # Get top confident nodes that are not rabbit holes
        candidates = [n for n in graph.nodes.values() if not n.is_rabbit_hole]
        candidates.sort(key=lambda n: n.entropy_score if n.entropy_score is not None else 0.0, reverse=True)
        top_nodes = candidates[:top_k]
        
        if not top_nodes:
            return False
            
        nodes_text = "\n".join(f"- {n.claim}" for n in top_nodes)
        
        prompt = CRITIC_PROMPT_TEMPLATE.format(
            case_context=vignette,
            top_nodes=nodes_text
        )
        
        try:
            response = self.llm.generate(prompt, max_tokens=100, temperature=0.1)
            first_line = response.strip().split('\n')[0].strip().upper()
            
            if "YES" in first_line:
                logger.info(f"[GlobalCritic] Halting approved. Reason: {response.strip().split(chr(10))[1:]}")
                return True
            else:
                logger.debug(f"[GlobalCritic] Halting rejected. Reason: {response.strip().split(chr(10))[1:]}")
                return False
        except Exception as e:
            logger.error(f"[GlobalCritic] Failed to evaluate halting: {e}")
            return False
