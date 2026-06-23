#!/usr/bin/env python3
"""
Apiro Calibration Experiment — Analysis & Reporting Script
===========================================================
Loads raw_results.json and evaluates the 5 pre-registered pass criteria:

  Pass 1 — Separation:              mean(entropy_B) >= 1.5 × mean(entropy_A)
  Pass 2 — Trick group correct:     entropy_C statistically closer to A than B
  Pass 3 — Temperature sensitivity: slope(B) > slope(A) from T=0.3 to T=1.2
  Pass 4 — Cross-model consistency: B > C > A ranking holds for BOTH models
  Pass 5 — Token & semantic agree:  dispersion rankings match entropy rankings

Generates:
  - figures/fig1_distributions.png   — violin/boxplot of entropy by group
  - figures/fig2_temp_slopes.png     — temperature sensitivity lines
  - figures/fig3_correlation.png     — token entropy vs semantic dispersion
  - figures/fig4_heatmap.png         — mean entropy heatmap (model × group × temp)
  - data/report.md                   — pass/fail summary report
"""

import json
import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from scipy import stats

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT      = Path(__file__).parent.parent
DATA_DIR  = ROOT / "data"
FIG_DIR   = ROOT / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

INPUT_FILE  = DATA_DIR / "raw_results.json"
REPORT_FILE = DATA_DIR / "report.md"

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

GROUP_COLORS = {
    "A": "#4ECDC4",   # teal — unambiguous (cool, certain)
    "B": "#FF6B6B",   # red  — genuinely ambiguous (hot, uncertain)
    "C": "#FFD93D",   # gold — trick group
}
GROUP_LABELS = {
    "A": "Group A\n(Unambiguous)",
    "B": "Group B\n(Ambiguous)",
    "C": "Group C\n(Trick)",
}
TEMPS = [0.3, 0.7, 1.2]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 12,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
    "axes.labelsize": 13,
    "axes.titlesize": 14,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
})

# ---------------------------------------------------------------------------
# Load & validate data
# ---------------------------------------------------------------------------

def load_data(path: Path) -> pd.DataFrame:
    with open(path) as f:
        raw = json.load(f)

    records = raw["results"]
    df = pd.DataFrame(records)

    # Drop rows where both metrics are NaN
    df = df.dropna(subset=["token_entropy", "semantic_dispersion"], how="all")

    print(f"Loaded {len(df)} records.")
    print(f"  Groups: {sorted(df['group'].unique())}")
    print(f"  Models: {sorted(df['model'].unique())}")
    print(f"  Temperatures: {sorted(df['temperature'].unique())}")
    return df


# ---------------------------------------------------------------------------
# Pass criteria evaluators
# ---------------------------------------------------------------------------

def pass1_separation(df: pd.DataFrame) -> dict:
    """
    Mean entropy(B) >= 1.5 × mean entropy(A), across BOTH models and ALL temps.
    Evaluated per model × temperature cell, must hold in all cells.
    """
    results = []
    all_pass = True
    for model in sorted(df["model"].unique()):
        for temp in sorted(df["temperature"].unique()):
            sub = df[(df["model"] == model) & (df["temperature"] == temp)]
            mean_a = sub[sub["group"] == "A"]["token_entropy"].mean()
            mean_b = sub[sub["group"] == "B"]["token_entropy"].mean()
            ratio  = mean_b / mean_a if mean_a and not math.isnan(mean_a) else float("nan")
            passed = ratio >= 1.5 if not math.isnan(ratio) else False
            if not passed:
                all_pass = False
            results.append({
                "model": model, "temperature": temp,
                "mean_A": round(mean_a, 4), "mean_B": round(mean_b, 4),
                "ratio_B_over_A": round(ratio, 4), "pass": passed,
            })
    return {"pass": all_pass, "cells": results}


def pass2_trick_group(df: pd.DataFrame) -> dict:
    """
    Group C entropy statistically closer to A than B.
    Test: |mean_C - mean_A| < |mean_C - mean_B| across both models and all temps.
    Also runs an independent t-test: C vs A and C vs B.
    """
    all_pass = True
    cells = []
    for model in sorted(df["model"].unique()):
        sub_m = df[df["model"] == model]
        ent_a = sub_m[sub_m["group"] == "A"]["token_entropy"].dropna().values
        ent_b = sub_m[sub_m["group"] == "B"]["token_entropy"].dropna().values
        ent_c = sub_m[sub_m["group"] == "C"]["token_entropy"].dropna().values

        mean_a, mean_b, mean_c = np.mean(ent_a), np.mean(ent_b), np.mean(ent_c)
        dist_ca = abs(mean_c - mean_a)
        dist_cb = abs(mean_c - mean_b)
        closer_to_a = dist_ca < dist_cb

        # Welch t-tests
        _, p_ca = stats.ttest_ind(ent_c, ent_a, equal_var=False) if len(ent_c) > 1 else (0, 1.0)
        _, p_cb = stats.ttest_ind(ent_c, ent_b, equal_var=False) if len(ent_c) > 1 else (0, 1.0)

        passed = closer_to_a
        if not passed:
            all_pass = False
        cells.append({
            "model": model,
            "mean_A": round(mean_a, 4), "mean_B": round(mean_b, 4), "mean_C": round(mean_c, 4),
            "dist_C_to_A": round(dist_ca, 4), "dist_C_to_B": round(dist_cb, 4),
            "C_closer_to_A": closer_to_a,
            "p_value_C_vs_A": round(p_ca, 4), "p_value_C_vs_B": round(p_cb, 4),
            "pass": passed,
        })
    return {"pass": all_pass, "cells": cells}


def pass3_temp_sensitivity(df: pd.DataFrame) -> dict:
    """
    Slope of B (entropy at T=1.2 − T=0.3) > slope of A.
    Must hold for both models.
    """
    all_pass = True
    cells = []
    for model in sorted(df["model"].unique()):
        sub_m = df[df["model"] == model]
        def mean_at_temp(group, temp):
            v = sub_m[(sub_m["group"] == group) & (sub_m["temperature"] == temp)]["token_entropy"]
            return v.mean()

        slope_a = mean_at_temp("A", 1.2) - mean_at_temp("A", 0.3)
        slope_b = mean_at_temp("B", 1.2) - mean_at_temp("B", 0.3)
        passed = slope_b > slope_a
        if not passed:
            all_pass = False
        cells.append({
            "model": model,
            "slope_A": round(slope_a, 4), "slope_B": round(slope_b, 4),
            "slope_B_gt_A": passed, "pass": passed,
        })
    return {"pass": all_pass, "cells": cells}


def pass4_cross_model(df: pd.DataFrame) -> dict:
    """
    Group ranking B > C > A on token entropy must hold for BOTH models.
    """
    all_pass = True
    cells = []
    for model in sorted(df["model"].unique()):
        sub_m = df[df["model"] == model]
        means = {g: sub_m[sub_m["group"] == g]["token_entropy"].mean() for g in ["A", "B", "C"]}
        correct_order = means["B"] > means["C"] > means["A"]
        if not correct_order:
            all_pass = False
        cells.append({
            "model": model,
            "mean_A": round(means["A"], 4),
            "mean_B": round(means["B"], 4),
            "mean_C": round(means["C"], 4),
            "order_B_gt_C_gt_A": correct_order, "pass": correct_order,
        })
    return {"pass": all_pass, "cells": cells}


def pass5_signal_agreement(df: pd.DataFrame) -> dict:
    """
    Semantic dispersion rankings must match token entropy rankings across all 3 groups.
    Evaluated per model: rank order of group means must be identical for both metrics.
    Also computes Spearman correlation between the two signals at record level.
    """
    all_pass = True
    cells = []
    for model in sorted(df["model"].unique()):
        sub_m = df[df["model"] == model].dropna(subset=["token_entropy", "semantic_dispersion"])
        ent_ranks  = {g: sub_m[sub_m["group"] == g]["token_entropy"].mean()    for g in ["A", "B", "C"]}
        disp_ranks = {g: sub_m[sub_m["group"] == g]["semantic_dispersion"].mean() for g in ["A", "B", "C"]}

        ent_order  = sorted(["A", "B", "C"], key=lambda g: ent_ranks[g])
        disp_order = sorted(["A", "B", "C"], key=lambda g: disp_ranks[g])
        ranks_agree = ent_order == disp_order

        # Spearman correlation at record level
        rho, p_val = stats.spearmanr(
            sub_m["token_entropy"], sub_m["semantic_dispersion"]
        ) if len(sub_m) > 2 else (float("nan"), float("nan"))

        passed = ranks_agree
        if not passed:
            all_pass = False
        cells.append({
            "model": model,
            "entropy_order": ent_order, "dispersion_order": disp_order,
            "orders_agree": ranks_agree,
            "spearman_rho": round(rho, 4) if not math.isnan(rho) else "N/A",
            "spearman_p": round(p_val, 4) if not math.isnan(p_val) else "N/A",
            "pass": passed,
        })
    return {"pass": all_pass, "cells": cells}


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_distributions(df: pd.DataFrame):
    """Fig 1 — Violin + box plots of token entropy and semantic dispersion by group."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(
        "Entropy & Semantic Dispersion by Clinical Question Group",
        fontsize=16, fontweight="bold", y=1.02,
    )

    palette = {g: GROUP_COLORS[g] for g in ["A", "B", "C"]}
    order    = ["A", "B", "C"]
    xlabels  = [GROUP_LABELS[g] for g in order]

    for ax, metric, title in [
        (axes[0], "token_entropy",       "Token Entropy (Shannon, nats)"),
        (axes[1], "semantic_dispersion", "Semantic Dispersion (mean cosine dist.)"),
    ]:
        sub = df.dropna(subset=[metric])
        sns.violinplot(
            data=sub, x="group", y=metric, order=order,
            palette=palette, inner=None, ax=ax, alpha=0.6,
        )
        sns.boxplot(
            data=sub, x="group", y=metric, order=order,
            palette=palette, width=0.25, linewidth=1.5,
            flierprops=dict(marker="o", markersize=3, alpha=0.5),
            ax=ax,
        )
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel("Question Group")
        ax.set_ylabel(metric.replace("_", " ").title())
        ax.set_xticklabels(xlabels)
        ax.axhline(
            sub[sub["group"] == "A"][metric].mean(),
            color=GROUP_COLORS["A"], linestyle="--", linewidth=1.2, alpha=0.7, label="Mean A",
        )
        ax.legend(fontsize=9)

    plt.tight_layout()
    path = FIG_DIR / "fig1_distributions.png"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def plot_temp_slopes(df: pd.DataFrame):
    """Fig 2 — Temperature sensitivity: mean entropy by group across T=0.3, 0.7, 1.2."""
    models = sorted(df["model"].unique())
    fig, axes = plt.subplots(1, len(models), figsize=(7 * len(models), 5), sharey=True)
    if len(models) == 1:
        axes = [axes]
    fig.suptitle("Temperature Sensitivity of Token Entropy", fontsize=16, fontweight="bold")

    for ax, model in zip(axes, models):
        sub_m = df[df["model"] == model]
        for group in ["A", "B", "C"]:
            sub_g = sub_m[sub_m["group"] == group]
            means = [
                sub_g[sub_g["temperature"] == t]["token_entropy"].mean()
                for t in TEMPS
            ]
            ax.plot(
                TEMPS, means,
                color=GROUP_COLORS[group],
                marker="o", linewidth=2.5, markersize=8,
                label=GROUP_LABELS[group].replace("\n", " "),
            )
            # shade std error
            stds = [
                sub_g[sub_g["temperature"] == t]["token_entropy"].sem()
                for t in TEMPS
            ]
            ax.fill_between(
                TEMPS,
                [m - s for m, s in zip(means, stds)],
                [m + s for m, s in zip(means, stds)],
                color=GROUP_COLORS[group], alpha=0.15,
            )
        ax.set_title(f"Model: {model}", fontweight="bold")
        ax.set_xlabel("Temperature")
        ax.set_ylabel("Mean Token Entropy (nats)")
        ax.set_xticks(TEMPS)
        ax.legend(fontsize=9)

    plt.tight_layout()
    path = FIG_DIR / "fig2_temp_slopes.png"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def plot_correlation(df: pd.DataFrame):
    """Fig 3 — Scatter plot: token entropy vs semantic dispersion, coloured by group."""
    sub = df.dropna(subset=["token_entropy", "semantic_dispersion"])
    fig, ax = plt.subplots(figsize=(8, 6))
    for group in ["A", "B", "C"]:
        sg = sub[sub["group"] == group]
        ax.scatter(
            sg["token_entropy"], sg["semantic_dispersion"],
            color=GROUP_COLORS[group], label=GROUP_LABELS[group].replace("\n", " "),
            alpha=0.65, s=40, edgecolors="white", linewidths=0.4,
        )
    # Overall Spearman rho
    rho, p = stats.spearmanr(sub["token_entropy"], sub["semantic_dispersion"])
    ax.set_title(
        f"Token Entropy vs Semantic Dispersion\n(Spearman ρ = {rho:.3f}, p = {p:.4f})",
        fontweight="bold",
    )
    ax.set_xlabel("Token Entropy (nats)")
    ax.set_ylabel("Semantic Dispersion (mean cosine dist.)")
    ax.legend(fontsize=10)
    plt.tight_layout()
    path = FIG_DIR / "fig3_correlation.png"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def plot_heatmap(df: pd.DataFrame):
    """Fig 4 — Heatmap of mean token entropy: group × temperature, faceted by model."""
    models = sorted(df["model"].unique())
    fig, axes = plt.subplots(1, len(models), figsize=(7 * len(models), 4))
    if len(models) == 1:
        axes = [axes]
    fig.suptitle("Mean Token Entropy Heatmap (Group × Temperature)", fontsize=15, fontweight="bold")

    for ax, model in zip(axes, models):
        sub_m = df[df["model"] == model]
        pivot = sub_m.pivot_table(
            values="token_entropy", index="group", columns="temperature", aggfunc="mean"
        )
        pivot = pivot.reindex(["A", "B", "C"])
        sns.heatmap(
            pivot, annot=True, fmt=".3f", cmap="RdYlGn_r",
            ax=ax, cbar_kws={"label": "Mean Entropy (nats)"},
            linewidths=0.5, linecolor="white",
        )
        ax.set_title(f"Model: {model}", fontweight="bold")
        ax.set_xlabel("Temperature")
        ax.set_ylabel("Group")
        ax.set_yticklabels(["A (Unambiguous)", "B (Ambiguous)", "C (Trick)"], rotation=0)

    plt.tight_layout()
    path = FIG_DIR / "fig4_heatmap.png"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

PASS_ICON = "✅ PASS"
FAIL_ICON = "❌ FAIL"

def write_report(
    df: pd.DataFrame,
    p1: dict, p2: dict, p3: dict, p4: dict, p5: dict,
):
    overall = all(p["pass"] for p in [p1, p2, p3, p4, p5])
    verdict = "**ALL 5 PASS — PROCEED TO BUILD PHASE**" if overall else "**ONE OR MORE CRITERIA FAILED — SEE FAILURE ANALYSIS BELOW**"

    lines = [
        "# Apiro Calibration Experiment — Results Report\n",
        f"## Overall Verdict: {PASS_ICON if overall else FAIL_ICON}\n",
        f"{verdict}\n",
        "---\n",
        "## Pass Criteria Results\n",

        f"### Pass 1 — Separation: {PASS_ICON if p1['pass'] else FAIL_ICON}",
        "_Mean entropy(B) ≥ 1.5× mean entropy(A) across all model × temperature cells._\n",
        "| Model | Temp | Mean A | Mean B | Ratio B/A | Pass |",
        "|-------|------|--------|--------|-----------|------|",
    ]
    for cell in p1["cells"]:
        icon = "✅" if cell["pass"] else "❌"
        lines.append(
            f"| {cell['model']} | {cell['temperature']} | {cell['mean_A']} | {cell['mean_B']} | {cell['ratio_B_over_A']} | {icon} |"
        )
    lines.append("")

    lines += [
        f"### Pass 2 — Trick Group: {PASS_ICON if p2['pass'] else FAIL_ICON}",
        "_Group C entropy statistically closer to A than B._\n",
        "| Model | Mean A | Mean B | Mean C | Dist C→A | Dist C→B | C closer to A | p (C vs A) | p (C vs B) | Pass |",
        "|-------|--------|--------|--------|----------|----------|---------------|------------|------------|------|",
    ]
    for cell in p2["cells"]:
        icon = "✅" if cell["pass"] else "❌"
        lines.append(
            f"| {cell['model']} | {cell['mean_A']} | {cell['mean_B']} | {cell['mean_C']} | "
            f"{cell['dist_C_to_A']} | {cell['dist_C_to_B']} | {cell['C_closer_to_A']} | "
            f"{cell['p_value_C_vs_A']} | {cell['p_value_C_vs_B']} | {icon} |"
        )
    lines.append("")

    lines += [
        f"### Pass 3 — Temperature Sensitivity: {PASS_ICON if p3['pass'] else FAIL_ICON}",
        "_Slope of entropy from T=0.3 to T=1.2 is steeper for Group B than A._\n",
        "| Model | Slope A | Slope B | B > A | Pass |",
        "|-------|---------|---------|-------|------|",
    ]
    for cell in p3["cells"]:
        icon = "✅" if cell["pass"] else "❌"
        lines.append(
            f"| {cell['model']} | {cell['slope_A']} | {cell['slope_B']} | {cell['slope_B_gt_A']} | {icon} |"
        )
    lines.append("")

    lines += [
        f"### Pass 4 — Cross-Model Consistency: {PASS_ICON if p4['pass'] else FAIL_ICON}",
        "_Group ranking B > C > A holds for both models._\n",
        "| Model | Mean A | Mean B | Mean C | B > C > A | Pass |",
        "|-------|--------|--------|--------|-----------|------|",
    ]
    for cell in p4["cells"]:
        icon = "✅" if cell["pass"] else "❌"
        lines.append(
            f"| {cell['model']} | {cell['mean_A']} | {cell['mean_B']} | {cell['mean_C']} | "
            f"{cell['order_B_gt_C_gt_A']} | {icon} |"
        )
    lines.append("")

    lines += [
        f"### Pass 5 — Signal Agreement: {PASS_ICON if p5['pass'] else FAIL_ICON}",
        "_Semantic dispersion group rankings match token entropy rankings._\n",
        "| Model | Entropy Order | Dispersion Order | Agree | Spearman ρ | p-value | Pass |",
        "|-------|--------------|-----------------|-------|------------|---------|------|",
    ]
    for cell in p5["cells"]:
        icon = "✅" if cell["pass"] else "❌"
        lines.append(
            f"| {cell['model']} | {'>'.join(cell['entropy_order'])} | {'>'.join(cell['dispersion_order'])} | "
            f"{cell['orders_agree']} | {cell['spearman_rho']} | {cell['spearman_p']} | {icon} |"
        )
    lines.append("")

    # Failure guidance
    if not overall:
        lines += [
            "---\n",
            "## Failure Analysis\n",
        ]
        if not p2["pass"] and p1["pass"]:
            lines.append(
                "**Pattern: Groups A and B separate but Group C behaves like B.**\n"
                "→ Entropy signal is measuring *surface complexity*, not genuine uncertainty.\n"
                "→ **Action**: Switch to semantic dispersion as the sole primary signal.\n"
            )
        if not p4["pass"]:
            lines.append(
                "**Pattern: Signal holds for one model but not the other.**\n"
                "→ Signal is model-dependent.\n"
                "→ **Action**: Lock project to the model that shows the pattern. Document the other as a known limitation.\n"
            )
        if not p5["pass"] and p1["pass"]:
            lines.append(
                "**Pattern: Token entropy works but semantic dispersion rankings disagree.**\n"
                "→ Tokenization is not the problem. The token-level signal is actually clean.\n"
                "→ **Action**: Proceed with token entropy only; drop the semantic layer.\n"
            )
        if not p1["pass"]:
            lines.append(
                "**Pattern: No meaningful separation between groups.**\n"
                "→ The entropy premise is wrong for this domain.\n"
                "→ **Action**: Do NOT build the graph engine with entropy-driven traversal.\n"
                "→ Pivot to **confidence-gap traversal**: expand the node where the top-2 "
                "candidate answers have the smallest probability gap between them.\n"
            )

    lines += [
        "---\n",
        "## Figures Generated\n",
        "- `figures/fig1_distributions.png` — Violin + box plots by group",
        "- `figures/fig2_temp_slopes.png`   — Temperature sensitivity slopes",
        "- `figures/fig3_correlation.png`   — Token entropy vs semantic dispersion scatter",
        "- `figures/fig4_heatmap.png`       — Mean entropy heatmap (group × temperature)\n",
    ]

    with open(REPORT_FILE, "w") as f:
        f.write("\n".join(lines))
    print(f"  Report saved: {REPORT_FILE}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print(" Apiro Calibration Experiment — Analysis")
    print("=" * 60)

    if not INPUT_FILE.exists():
        print(f"\n[ERROR] Results file not found: {INPUT_FILE}")
        print("Run run_experiment.py first.")
        return

    df = load_data(INPUT_FILE)

    print("\nEvaluating pass criteria...")
    p1 = pass1_separation(df)
    p2 = pass2_trick_group(df)
    p3 = pass3_temp_sensitivity(df)
    p4 = pass4_cross_model(df)
    p5 = pass5_signal_agreement(df)

    for label, result in [
        ("Pass 1 (Separation)", p1),
        ("Pass 2 (Trick group)", p2),
        ("Pass 3 (Temp sensitivity)", p3),
        ("Pass 4 (Cross-model)", p4),
        ("Pass 5 (Signal agreement)", p5),
    ]:
        icon = PASS_ICON if result["pass"] else FAIL_ICON
        print(f"  {icon}  {label}")

    print("\nGenerating figures...")
    plot_distributions(df)
    plot_temp_slopes(df)
    plot_correlation(df)
    plot_heatmap(df)

    print("\nWriting report...")
    write_report(df, p1, p2, p3, p4, p5)

    overall = all(p["pass"] for p in [p1, p2, p3, p4, p5])
    print("\n" + "=" * 60)
    if overall:
        print(" RESULT: ALL 5 CRITERIA PASS ✅")
        print(" → Entropy signal is valid. Proceed to build the graph engine.")
    else:
        print(" RESULT: ONE OR MORE CRITERIA FAILED ❌")
        print(" → See data/report.md for failure analysis and recommended pivot.")
    print("=" * 60)


if __name__ == "__main__":
    main()
