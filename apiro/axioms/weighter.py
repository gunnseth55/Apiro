import yaml
import os
import logging
from .models import ClinicalAxiom

logger = logging.getLogger(__name__)

class AxiomWeighter:
    def __init__(self, weights_file="data/axiom_weights.yaml"):
        self.weights = {}
        if os.path.exists(weights_file):
            with open(weights_file, 'r') as f:
                try:
                    data = yaml.safe_load(f)
                    if data:
                        # Flatten into a fast lookup dict mapping lowercase text to weight
                        for category in ["high_weight", "medium_weight", "low_weight"]:
                            if category in data:
                                for item in data[category]:
                                    self.weights[item["entity"].lower()] = item["weight"]
                except Exception as e:
                    logger.error(f"Failed to load weights from {weights_file}: {e}")
        else:
            logger.warning(f"Axiom weights file {weights_file} not found. Using default weights.")

    def get_weight(self, axiom: ClinicalAxiom) -> float:
        """
        Lookup the diagnostic specificity weight.
        """
        # If it's a lab value with a number, and it wasn't filtered, it generally has high specificity
        if axiom.domain in ["lab", "vital"] and axiom.value is not None:
            # A real implementation would check threshold values here
            return 0.8
            
        text_lower = axiom.text.lower()
        
        # Exact match
        if text_lower in self.weights:
            return self.weights[text_lower]
            
        # Partial match
        for key, weight in self.weights.items():
            if key in text_lower:
                return weight
                
        # Default fallback weight for unknown entities
        return 0.3
