import logging
from .models import ClinicalAxiom

logger = logging.getLogger(__name__)

class NegationClassifier:
    def __init__(self):
        try:
            import medspacy
            # We just need the ConText component for negation and historicity
            self.nlp = medspacy.load(enable=["medspacy_context"])
            logger.info("Loaded medspacy context for negation classification.")
        except ImportError:
            logger.error("medspacy not installed. Negation classification will pass through.")
            self.nlp = None

    def classify(self, text: str, axioms: list[ClinicalAxiom]) -> list[ClinicalAxiom]:
        """
        Takes raw axioms and determines if they are negated or historical based on the context.
        """
        if not self.nlp or not axioms:
            return axioms
            
        doc = self.nlp(text)
        
        # Medspacy's context works on entities. We need to map our extracted axioms back to entities
        # in the medspacy doc, or just run medspacy target matcher.
        # For a simplified approach, we will just use a basic custom check using medspacy doc if possible,
        # but since we already extracted entities with scispaCy, we can just feed them as targets to context.
        
        from medspacy.ner import TargetMatcher, TargetRule
        
        # Create rules for each axiom text
        target_matcher = TargetMatcher(self.nlp.vocab)
        rules = [TargetRule(ax.text, "AXIOM") for ax in axioms]
        target_matcher.add(rules)
        
        doc = self.nlp.tokenizer(text)
        target_matcher(doc)
        
        # Now run context
        self.nlp.get_pipe("medspacy_context")(doc)
        
        # Now map back results
        # We index the doc ents by text
        ent_map = {}
        for ent in doc.ents:
            # context adds attributes: is_negated, is_historical
            ent_map[ent.text] = {
                "negated": ent._.is_negated,
                "historical": ent._.is_historical
            }
            
        for ax in axioms:
            # If we matched it
            info = ent_map.get(ax.text)
            if info:
                if info["historical"]:
                    ax.polarity = "historical"
                elif info["negated"]:
                    ax.polarity = "negated"
                else:
                    ax.polarity = "affirmed"
                    
        return axioms
