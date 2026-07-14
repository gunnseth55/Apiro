"""
apiro/edar/__init__.py
======================
Evidence-Driven Abductive Reasoning (EDAR) package.

The EDAR engine replaces the LLM Oracle hypothesis generator with a
purely algorithmic candidate discovery mechanism, then applies genuine
Bayesian belief revision — updating disease probabilities iteratively
as each piece of evidence is processed.

Architecture:
  Phase 1: CandidateDiscoverer   — corpus-based candidate mining (0 LLM calls)
  Phase 2: EvidenceGraphBuilder  — build confirmed/absent/contradicted evidence per candidate (0 LLM calls)
  Phase 3: BayesianBeliefUpdater — iterative Bayesian posterior updates (0 LLM calls)
  Phase 4: Discriminator         — find the key differentiating finding (0 LLM calls)
  Phase 5: LLM used only for:
            a) parsing raw patient text → PatientContext (1 LLM call, unavoidable)
            b) synthesising the final diagnostic narrative (1 LLM call)
"""
