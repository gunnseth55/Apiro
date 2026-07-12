import logging
from .models import ClinicalAxiom

logger = logging.getLogger(__name__)

class NERExtractor:
    def __init__(self, model_name="d4data/biomedical-ner-all"):
        logger.info(f"Loading Hugging Face NER model: {model_name}...")
        try:
            from transformers import pipeline
            # Use aggregation_strategy="simple" to merge sub-word tokens (B-core, I-core) into full words
            self.nlp = pipeline("ner", model=model_name, aggregation_strategy="simple", device="cpu")
        except Exception as e:
            logger.error(f"Failed to load transformers pipeline. Error: {e}")
            self.nlp = None

    def extract(self, text: str) -> list[ClinicalAxiom]:
        if not self.nlp:
            logger.error("NER pipeline not initialized. Returning empty axioms.")
            return []
            
        try:
            entities = self.nlp(text)
        except Exception as e:
            logger.error(f"NER extraction failed: {e}")
            return []
            
        axioms = []
        merged_axioms = []
        current_word = ""
        current_label = ""
        
        # HuggingFace returns a list of dicts. We manually stitch WordPiece '##' tokens 
        # in case the aggregation_strategy fails.
        for ent in entities:
            label = ent.get("entity_group", ent.get("entity", "finding"))
            word = ent.get("word", "").strip()
            
            if not word:
                continue
                
            if word.startswith("##"):
                current_word += word[2:]
            else:
                if current_word and len(current_word) >= 3:
                    merged_axioms.append((current_word, current_label))
                current_word = word
                current_label = label
                
        if current_word and len(current_word) >= 3:
            merged_axioms.append((current_word, current_label))
            
        axioms = []
        for word, label in merged_axioms:
            ax = ClinicalAxiom(
                id="",
                text=word,
                domain=label,
                polarity="affirmed",
                value=None,
                unit=None,
                weight=0.0,
                snomed_cui=None
            )
            axioms.append(ax)
            
        return axioms

