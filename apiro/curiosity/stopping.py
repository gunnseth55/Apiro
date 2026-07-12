import logging
from typing import List, Tuple
from apiro.hypothesis.models import Hypothesis

logger = logging.getLogger(__name__)

class StoppingCondition:
    def __init__(self, confidence_threshold=0.95, eig_threshold=0.01, max_iterations=12):
        self.confidence_threshold = confidence_threshold
        self.eig_threshold = eig_threshold
        self.max_iterations = max_iterations

    def check(self, hypotheses: List[Hypothesis], max_eig: float, iteration: int) -> Tuple[bool, str]:
        """
        Checks if the engine should halt.
        
        Returns:
            Tuple[bool, str]: (should_stop, reason)
        """
        active_hypotheses = [h for h in hypotheses if not h.is_killed]
        
        if not active_hypotheses:
            return True, "All hypotheses killed. Irreducible contradiction."
            
        # 1. Confidence Threshold (Case Solved)
        for h in active_hypotheses:
            if h.probability >= self.confidence_threshold:
                logger.info(f"Stopping Condition Met: '{h.name}' reached {h.probability*100:.1f}% confidence.")
                return True, "Confidence Threshold Reached"
                
        # 2. Information Gain Exhaustion
        if max_eig < self.eig_threshold:
            logger.info(f"Stopping Condition Met: Max Expected Information Gain ({max_eig:.4f}) is below threshold ({self.eig_threshold}).")
            return True, "Information Gain Exhaustion"
            
        # 3. Hard Budget
        if iteration >= self.max_iterations:
            logger.info("Stopping Condition Met: Max iterations reached.")
            return True, "Max Iterations Reached"
            
        return False, ""
