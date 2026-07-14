import logging
import json
from typing import List
import numpy as np

from apiro.axioms.models import ClinicalAxiom
from apiro.hypothesis.models import Hypothesis
from .kl_divergence import expected_information_gain
from .stopping import StoppingCondition

logger = logging.getLogger(__name__)

class HADCEngine:
    """
    Hypothesis-Driven Directed Curiosity Engine (HADCE)
    """
    def __init__(self, embedder, llm_client, contradiction, rabbit_hole):
        self.embedder = embedder
        self.llm = llm_client
        self.contradiction = contradiction
        self.rabbit_hole = rabbit_hole
        self.stopping = StoppingCondition()

    def run(self, axioms: List[ClinicalAxiom], hypotheses: List[Hypothesis], max_iterations=12):
        logger.info("Starting HADCE Traversal Loop...")
        
        iteration = 0
        while True:
            iteration += 1
            logger.info(f"\n--- HADCE Iteration {iteration} ---")
            
            active = [h for h in hypotheses if not h.is_killed]
            
            # Formulate potential queries for the top hypotheses
            queries = self._formulate_queries(active)
            
            # Calculate EIG for each query
            prior = [h.probability for h in active]
            best_query = None
            max_eig = 0.0
            
            for q in queries:
                eig = self._estimate_eig(q, active, prior)
                if eig > max_eig:
                    max_eig = eig
                    best_query = q
            
            # Check stopping conditions
            stop, reason = self.stopping.check(hypotheses, max_eig, iteration)
            if stop:
                logger.info(f"Engine halted. Reason: {reason}")
                break
                
            if not best_query:
                logger.info("No viable queries generated. Halting.")
                break
                
            logger.info(f"Executing Top EIG Query (EIG={max_eig:.4f}): '{best_query}'")
            
            # Execute query and update
            self._execute_and_update(best_query, active, axioms)
            
            # Normalize probabilities
            self._normalize(active)
            
            # Print current standings
            for h in sorted(active, key=lambda x: x.probability, reverse=True):
                logger.info(f"  {h.name}: {h.probability*100:.1f}%")
                
        return sorted([h for h in hypotheses if not h.is_killed], key=lambda x: x.probability, reverse=True)

    def _formulate_queries(self, active: List[Hypothesis]) -> List[str]:
        # Simple heuristic: formulate one query per active hypothesis asking for differential evidence
        queries = []
        for h in active[:3]:
            # Ask the LLM what evidence would confirm this hypothesis
            prompt = f"What single specific lab test, vital sign, or physical exam finding would most strongly confirm a diagnosis of {h.name}? Reply with just the name of the test or finding."
            ans = self.llm.generate(prompt).strip()
            if ans and len(ans) > 3:
                queries.append(ans)
        return list(set(queries))

    def _estimate_eig(self, query: str, active: List[Hypothesis], prior: List[float]) -> float:
        # Simplified EIG estimation using the LLM to guess the likelihoods
        # In a full system, this would query a medical ontology
        prompt = f"Does the finding '{query}' strongly support the following diagnoses? Reply YES or NO for each, separated by commas.\n"
        for h in active:
            prompt += f"- {h.name}\n"
            
        ans = self.llm.generate(prompt).lower()
        
        # Parse YES/NO to build likelihood distributions
        p_found = 0.5 # Assume 50% chance we find it
        likelihood_if_found = []
        likelihood_if_not = []
        
        for i, h in enumerate(active):
            name_lower = h.name.lower()
            # Crude parsing for the prototype
            if "yes" in ans.split(',')[i] if i < len(ans.split(',')) else "yes":
                likelihood_if_found.append(prior[i] * 1.5)
                likelihood_if_not.append(prior[i] * 0.5)
            else:
                likelihood_if_found.append(prior[i] * 0.2)
                likelihood_if_not.append(prior[i] * 1.2)
                
        return expected_information_gain(prior, likelihood_if_found, likelihood_if_not, p_found)

    def _execute_and_update(self, query: str, active: List[Hypothesis], axioms: List[ClinicalAxiom]):
        # RAG query
        logger.info(f"  Querying RAG for: {query}")
        try:
            results = self.embedder.query(query, n_results=5)
            context = "\n".join([r["text"] for r in results])
        except Exception:
            context = ""
            
        # Method C: Evidence Weighting
        for h in active:
            prompt = f"Based on this medical text:\n{context}\n\nDoes it confirm {h.name}? Reply YES, NO, or NEUTRAL."
            ans = self.llm.generate(prompt).strip().upper()
            
            if "YES" in ans:
                h.probability *= 1.2
            elif "NO" in ans:
                h.probability *= 0.5
                
            # Cap at 0.99
            h.probability = min(0.99, h.probability)

    def _normalize(self, active: List[Hypothesis]):
        total = sum(h.probability for h in active)
        if total > 0:
            for h in active:
                h.probability /= total
