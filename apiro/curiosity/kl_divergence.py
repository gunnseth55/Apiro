import numpy as np
from scipy.stats import entropy
import logging

logger = logging.getLogger(__name__)

def expected_information_gain(
    prior: list[float],          # Current P(H) for each hypothesis
    likelihood_if_found: list[float],  # P(H | evidence found)
    likelihood_if_not: list[float],    # P(H | evidence not found)
    p_found: float               # Prior probability that evidence exists
) -> float:
    """
    Calculates the Expected Information Gain (EIG) of a potential query.
    EIG is the expected Kullback-Leibler (KL) divergence between the posterior
    distribution (after seeing the evidence) and the prior distribution.
    
    Args:
        prior: Current probabilities of our hypotheses.
        likelihood_if_found: New probabilities if the query returns positive.
        likelihood_if_not: New probabilities if the query returns negative.
        p_found: Probability that the query will return positive.
        
    Returns:
        float: Expected Information Gain (higher = better query).
    """
    # Convert lists to numpy arrays for scipy
    prior_arr = np.array(prior)
    found_arr = np.array(likelihood_if_found)
    not_arr = np.array(likelihood_if_not)
    
    # Avoid div by zero or log(0)
    eps = 1e-10
    prior_arr = np.clip(prior_arr, eps, 1.0)
    found_arr = np.clip(found_arr, eps, 1.0)
    not_arr = np.clip(not_arr, eps, 1.0)
    
    # Normalize
    prior_arr /= prior_arr.sum()
    found_arr /= found_arr.sum()
    not_arr /= not_arr.sum()
    
    # KL divergence D(Posterior || Prior)
    # entropy(pk, qk) calculates sum(pk * log(pk / qk))
    kl_found = entropy(found_arr, prior_arr)
    kl_not = entropy(not_arr, prior_arr)
    
    # EIG = sum_{x in outcomes} P(x) * D(P(H|x) || P(H))
    eig = (p_found * kl_found) + ((1.0 - p_found) * kl_not)
    
    return float(eig)
