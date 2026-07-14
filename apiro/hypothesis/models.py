from dataclasses import dataclass

@dataclass
class Hypothesis:
    id: str
    name: str            # e.g. "Pulmonary Embolism"
    probability: float   # Current confidence 0.0-1.0
    initial_probability: float # Starting confidence from sampling
    supporting_axioms: list[str]  # IDs of axioms this hypothesis explains
    contradicting_axioms: list[str]  # IDs of axioms this hypothesis violates
    is_killed: bool = False
