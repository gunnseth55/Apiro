import re
import logging
from typing import Optional
from .models import ClinicalAxiom

logger = logging.getLogger(__name__)

# Basic Regex patterns for vitals and common labs
# e.g. "Troponin 5.0 ng/mL", "BP 120/80 mmHg", "Temp 39.5 C"
LAB_PATTERNS = [
    # General pattern: [Name] [Value] [Unit]
    # Name: 1-3 words, Value: float, Unit: word with optional slashes/letters
    re.compile(r'\b([A-Za-z\-]+(?:\s+[A-Za-z\-]+){0,2})\s*[:=]?\s*(\d+(?:\.\d+)?)\s*([a-zA-Z%µ/]+)\b', re.IGNORECASE),
    # Blood pressure: BP 120/80 mmHg
    re.compile(r'\b(BP|Blood pressure)\s*[:=]?\s*(\d{2,3}/\d{2,3})\s*(mmHg)?\b', re.IGNORECASE),
]

class LabParser:
    def __init__(self):
        pass
        
    def parse(self, text: str) -> list[ClinicalAxiom]:
        axioms = []
        
        for pattern in LAB_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group(1).strip()
                val_str = match.group(2)
                unit = match.group(3) if match.lastindex >= 3 else None
                
                # Filter out obvious false positives
                if len(name) < 2 or name.lower() in ["a", "the", "in", "on", "at", "to", "is", "was", "for", "with"]:
                    continue
                    
                # Handle BP specifically
                if "/" in val_str:
                    val = None # Keep as string in 'text'
                else:
                    try:
                        val = float(val_str)
                    except ValueError:
                        val = None
                        
                sentence = f"The patient has a lab result or vital sign showing {match.group(0).strip()}."
                ax = ClinicalAxiom(
                    id="",
                    text=sentence,
                    domain="lab" if name.lower() not in ["bp", "blood pressure", "temp", "temperature", "hr", "heart rate", "rr"] else "vital",
                    polarity="affirmed",
                    value=val,
                    unit=unit,
                    weight=0.0,
                    snomed_cui=None
                )
                axioms.append(ax)
                
        return axioms
