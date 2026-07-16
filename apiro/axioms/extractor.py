import logging
from dataclasses import dataclass
from typing import Optional

from .ner import NERExtractor
from .negation import NegationClassifier
from .lab_parser import LabParser
from .weighter import AxiomWeighter

logger = logging.getLogger(__name__)

from .models import ClinicalAxiom

class AxiomExtractor:
    """
    Deterministic pipeline that runs rule-based NLP tools over a clinical vignette
    to extract immutable Clinical Axioms.
    """
    def __init__(self):
        self.ner = NERExtractor()
        self.negation = NegationClassifier()
        self.lab_parser = LabParser()
        self.weighter = AxiomWeighter()

    def extract(self, vignette: str) -> list[ClinicalAxiom]:
        logger.info("Extracting Clinical Axioms...")
        axioms = []
        
        # 1. Parse labs and vitals via strict Regex (these are gold-standard facts)
        lab_axioms = self.lab_parser.parse(vignette)
        
        # 2. Extract clinical entities via scispaCy
        ner_entities = self.ner.extract(vignette)
        
        # Filter NER entities that overlap with matched lab values to avoid duplicates
        filtered_ner = self._filter_overlaps(ner_entities, lab_axioms)
        
        # 3. Classify polarity (affirmed/negated) via NegEx
        polar_entities = self.negation.classify(vignette, filtered_ner)
        
        # Merge lab axioms and polar NER entities
        all_raw_axioms = lab_axioms + polar_entities
        
        # 4. Weight each axiom based on its specificity
        for i, raw in enumerate(all_raw_axioms):
            weight = self.weighter.get_weight(raw)
            raw.weight = weight
            raw.id = f"ax_{i}"
            axioms.append(raw)
            
        logger.info(f"Extracted {len(axioms)} deterministic axioms.")
        return axioms

    def _filter_overlaps(self, ner_entities: list, lab_axioms: list) -> list:
        # Prevent duplicates: if an NER entity word is already present inside
        # the match text of a lab/vital axiom, discard the duplicate NER entity.
        filtered = []
        prefix = "The patient presents with the clinical finding of "
        for ner in ner_entities:
            word = ner.text[len(prefix):].rstrip(".").strip().lower() if ner.text.startswith(prefix) else ner.text.lower()
            
            overlap = False
            for lab in lab_axioms:
                if word in lab.text.lower():
                    overlap = True
                    break
            if not overlap:
                filtered.append(ner)
        return filtered
