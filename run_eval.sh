#!/bin/bash
# Wrapper script to run the HADCE evaluation
echo "Running the Distractor-Resilience Evaluation with HADCE..."
source venv/bin/activate
python scripts/run_pmc_eval.py --real
