import re
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
            logger.error("medspacy not installed. Negation classification will use regex fallback.")
            self.nlp = None

    def classify(self, text: str, axioms: list[ClinicalAxiom]) -> list[ClinicalAxiom]:
        """
        Takes raw axioms and determines if they are negated or historical based on the context.
        """
        if not axioms:
            return axioms
            
        if self.nlp:
            try:
                from medspacy.ner import TargetMatcher, TargetRule
                
                # Extract raw words from the forged sentence structure
                prefix = "The patient presents with the clinical finding of "
                raw_words = []
                for ax in axioms:
                    if ax.text.startswith(prefix):
                        raw_words.append(ax.text[len(prefix):].rstrip("."))
                    else:
                        raw_words.append(ax.text)
                        
                target_matcher = TargetMatcher(self.nlp.vocab)
                rules = [TargetRule(word, "AXIOM") for word in raw_words]
                target_matcher.add(rules)
                
                doc = self.nlp.tokenizer(text)
                target_matcher(doc)
                
                # Now run context
                self.nlp.get_pipe("medspacy_context")(doc)
                
                # Map back results
                ent_map = {}
                for ent in doc.ents:
                    ent_map[ent.text.lower()] = {
                        "negated": ent._.is_negated,
                        "historical": ent._.is_historical
                    }
                    
                for ax, raw_word in zip(axioms, raw_words):
                    info = ent_map.get(raw_word.lower())
                    if info:
                        if info["historical"]:
                            ax.polarity = "historical"
                            ax.text = f"The patient has a history of {raw_word}."
                        elif info["negated"]:
                            ax.polarity = "negated"
                            ax.text = f"The patient denies the clinical finding of {raw_word}."
                        else:
                            ax.polarity = "affirmed"
                return axioms
            except Exception as e:
                logger.error(f"medspacy classification failed: {e}. Falling back to regex.")

        # Fallback to simple rule-based negation and history classifier
        text_lower = text.lower()
        neg_patterns = [
            r"\b(no|not|denies|denied|negative for|rules? out|ruled out|free of|without|absent|absence of|never|unlikely|cannot|does not|no evidence of|no sign of|no history of)\b",
        ]
        history_patterns = [
            r"\b(history of|past medical history|previously|prior episode|prior history|years ago|months ago)\b"
        ]
        
        prefix = "The patient presents with the clinical finding of "
        for ax in axioms:
            if ax.text.startswith(prefix):
                raw_word = ax.text[len(prefix):].rstrip(".")
            else:
                raw_word = ax.text
                
            word_lower = raw_word.lower()
            idx = text_lower.find(word_lower)
            if idx != -1:
                # Check window before the word (up to 45 characters)
                window_start = max(0, idx - 45)
                window_before = text_lower[window_start:idx]
                
                is_negated = any(re.search(pat, window_before) for pat in neg_patterns)
                is_historical = any(re.search(pat, window_before) for pat in history_patterns)
                
                if is_historical:
                    ax.polarity = "historical"
                    ax.text = f"The patient has a history of {raw_word}."
                elif is_negated:
                    ax.polarity = "negated"
                    ax.text = f"The patient denies the clinical finding of {raw_word}."
                else:
                    ax.polarity = "affirmed"
                    
        return axioms
