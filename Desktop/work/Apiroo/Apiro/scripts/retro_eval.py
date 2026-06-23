#!/usr/bin/env python3
"""
scripts/retro_eval.py
=====================
Replay existing phase3_results.json through the NEW _check_synthesis_hit logic
WITHOUT re-running traversals.  Lets us validate the threshold change instantly.

Usage:
    python scripts/retro_eval.py [--results data/phase3_results.json]
"""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from apiro.eval.evaluator import _check_synthesis_hit, _determine_winner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="data/phase3_results.json")
    args = parser.parse_args()

    data = json.loads(Path(args.results).read_text())

    print("\n" + "=" * 72)
    print(f"  RETRO EVAL — replaying {args.results} with new hit logic")
    print(f"  (no embedder used — Tier 1 substring + Tier 2 synonym only)")
    print("=" * 72)

    ef_wins = bf_wins = ties = both_miss = 0
    old_ef_wins = old_bf_wins = old_ties = old_both_miss = 0

    for case in data["per_case"]:
        cid = case["case_id"]
        gt = case["ground_truth"]
        ef = case["entropy_first"]
        bf = case["breadth_first"]

        # Old results
        old_winner = case["winner"]
        if old_winner == "entropy_first": old_ef_wins += 1
        elif old_winner == "breadth_first": old_bf_wins += 1
        elif old_winner == "tie": old_ties += 1
        else: old_both_miss += 1

        # New hit checks (no embedder — Tier 1 + Tier 2 only)
        new_ef_hit = _check_synthesis_hit(ef["synthesis"], gt, embedder=None)
        new_bf_hit = _check_synthesis_hit(bf["synthesis"], gt, embedder=None)

        # Rebuild metric dicts for _determine_winner
        new_ef = {**ef, "diagnostic_hit": new_ef_hit}
        new_bf = {**bf, "diagnostic_hit": new_bf_hit}
        new_winner = _determine_winner(new_ef, new_bf)

        # Tally
        if new_winner == "entropy_first": ef_wins += 1
        elif new_winner == "breadth_first": bf_wins += 1
        elif new_winner == "tie": ties += 1
        else: both_miss += 1

        # Report changes
        changed = "  " if old_winner == new_winner else "⚠ CHANGED"
        ef_flag = "✓" if new_ef_hit else "✗"
        bf_flag = "✓" if new_bf_hit else "✗"
        print(
            f"  {changed} [{cid}]\n"
            f"    GT: {gt}\n"
            f"    EF synthesis: {ef['synthesis']}\n"
            f"    BF synthesis: {bf['synthesis']}\n"
            f"    OLD winner: {old_winner:15s}  →  NEW winner: {new_winner}\n"
            f"    EF hit: {ef_flag} | BF hit: {bf_flag}\n"
        )

    n = data["total_cases"]
    print("=" * 72)
    print("  BEFORE (old logic):")
    print(f"    EF={old_ef_wins}  BF={old_bf_wins}  Ties={old_ties}  BothMiss={old_both_miss}  "
          f"EF rate={old_ef_wins/n:.0%}")
    print()
    print("  AFTER (new logic, Tier1+Tier2, no embedder):")
    print(f"    EF={ef_wins}  BF={bf_wins}  Ties={ties}  BothMiss={both_miss}  "
          f"EF rate={ef_wins/n:.0%}")
    print("=" * 72)


if __name__ == "__main__":
    main()
