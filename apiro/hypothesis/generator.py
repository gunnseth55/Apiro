import logging
import requests
import json
from typing import List
from collections import Counter

from apiro.axioms.models import ClinicalAxiom
from .models import Hypothesis

logger = logging.getLogger(__name__)

class HypothesisGenerator:
    def __init__(self, ollama_url="http://localhost:11434", model="llama3.1:8b", contradiction_detector=None):
        self.ollama_url = f"{ollama_url}/api/generate"
        self.model = model
        self.contradiction_detector = contradiction_detector

    def generate(self, axioms: List[ClinicalAxiom], n_samples=10, temperature=0.7) -> List[Hypothesis]:
        logger.info(f"Generating initial hypotheses from {len(axioms)} axioms using repeated sampling...")
        
        # Build prompt from axioms
        prompt = "Based on the following clinical findings, provide the SINGLE most likely acute diagnosis.\n"
        prompt += "Output ONLY the name of the disease, with no extra text or punctuation.\n\n"
        for ax in axioms:
            prefix = "[ABSENT] " if ax.polarity == "negated" else "[HISTORY] " if ax.polarity == "historical" else ""
            prompt += f"- {prefix}{ax.text}\n"
            
        prompt += "\nDiagnosis:"
        
        diagnoses = []
        for i in range(n_samples):
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": 10},
            }
            try:
                res = requests.post(self.ollama_url, json=payload, timeout=30)
                if res.status_code == 200:
                    ans = res.json().get("response", "").strip().lower()
                    # Clean up common LLM artifacts
                    ans = ans.replace("the diagnosis is", "").replace("diagnosis:", "").strip(" .\n*\"\'")
                    if len(ans) > 3:
                        diagnoses.append(ans)
            except Exception as e:
                logger.warning(f"Ollama generation failed on sample {i}: {e}")
                
        if not diagnoses:
            logger.error("Failed to generate any hypotheses.")
            return []
            
        # Calculate frequencies
        counts = Counter(diagnoses)
        total = len(diagnoses)
        
        hypotheses = []
        # Take top 5
        for name, count in counts.most_common(5):
            prob = count / total
            h = Hypothesis(
                id=f"h_{name.replace(' ', '_')}",
                name=name.title(),
                probability=prob,
                initial_probability=prob,
                supporting_axioms=[],
                contradicting_axioms=[],
                is_killed=False
            )
            hypotheses.append(h)
            
        logger.info(f"Generated {len(hypotheses)} hypotheses.")
        
        # THE GAUNTLET: Contradiction Check at Birth
        return self._run_gauntlet(hypotheses, axioms)

    def _run_gauntlet(self, hypotheses: List[Hypothesis], axioms: List[ClinicalAxiom]) -> List[Hypothesis]:
        if not self.contradiction_detector:
            logger.warning("No ContradictionDetector provided. Skipping the Gauntlet.")
            return hypotheses
            
        logger.info("Running the Gauntlet: cross-checking hypotheses against Clinical Axioms...")
        for h in hypotheses:
            fatal_contradictions = 0
            claim_a = f"A patient is diagnosed with {h.name}."
            
            for ax in axioms:
                # We only check affirmed/negated clinical facts, not history for now unless highly weighted
                if ax.polarity == "affirmed":
                    claim_b = f"The patient presents with the clinical finding of {ax.text}."
                elif ax.polarity == "negated":
                    claim_b = f"The patient does NOT present with the clinical finding of {ax.text}."
                else:
                    continue
                    
                result = self.contradiction_detector.check(claim_a, claim_b)
                if result.label == "contradiction" and result.score > 0.90:
                    h.contradicting_axioms.append(ax.id)
                    # Penalize probability heavily based on axiom weight
                    penalty = ax.weight * result.score
                    h.probability = max(0.01, h.probability - penalty)
                    logger.info(f"  [Gauntlet] '{h.name}' contradicts axiom '{ax.text}' (weight {ax.weight}). New prob: {h.probability:.2f}")
                    
                    if ax.weight >= 0.7:
                        fatal_contradictions += 1
                        
            if fatal_contradictions >= 2 or h.probability <= 0.05:
                logger.info(f"  [Gauntlet] Hypothesis '{h.name}' KILLED (too many fatal contradictions).")
                h.is_killed = True
                
        return hypotheses
