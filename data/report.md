# Apiro Calibration Experiment — Results Report

## Overall Verdict: ✅ PASS

**ALL 5 PASS — PROCEED TO BUILD PHASE**

---

## Pass Criteria Results

### Pass 1 — Separation: ✅ PASS
_Mean entropy(B) ≥ 1.5× mean entropy(A) across all model × temperature cells._

| Model | Temp | Mean A | Mean B | Ratio B/A | Pass |
|-------|------|--------|--------|-----------|------|
| llama3.1 | 0.3 | 0.4493 | 1.7785 | 3.9581 | ✅ |
| llama3.1 | 0.7 | 0.5579 | 2.1472 | 3.8489 | ✅ |
| llama3.1 | 1.2 | 0.6981 | 2.612 | 3.7417 | ✅ |
| mistral | 0.3 | 0.4529 | 1.8101 | 3.9963 | ✅ |
| mistral | 0.7 | 0.553 | 2.1646 | 3.914 | ✅ |
| mistral | 1.2 | 0.6984 | 2.5937 | 3.7135 | ✅ |

### Pass 2 — Trick Group: ✅ PASS
_Group C entropy statistically closer to A than B._

| Model | Mean A | Mean B | Mean C | Dist C→A | Dist C→B | C closer to A | p (C vs A) | p (C vs B) | Pass |
|-------|--------|--------|--------|----------|----------|---------------|------------|------------|------|
| llama3.1 | 0.5684 | 2.1792 | 0.7375 | 0.1691 | 1.4417 | True | 0.0 | 0.0 | ✅ |
| mistral | 0.5681 | 2.1894 | 0.7352 | 0.167 | 1.4543 | True | 0.0 | 0.0 | ✅ |

### Pass 3 — Temperature Sensitivity: ✅ PASS
_Slope of entropy from T=0.3 to T=1.2 is steeper for Group B than A._

| Model | Slope A | Slope B | B > A | Pass |
|-------|---------|---------|-------|------|
| llama3.1 | 0.2487 | 0.8335 | True | ✅ |
| mistral | 0.2455 | 0.7836 | True | ✅ |

### Pass 4 — Cross-Model Consistency: ✅ PASS
_Group ranking B > C > A holds for both models._

| Model | Mean A | Mean B | Mean C | B > C > A | Pass |
|-------|--------|--------|--------|-----------|------|
| llama3.1 | 0.5684 | 2.1792 | 0.7375 | True | ✅ |
| mistral | 0.5681 | 2.1894 | 0.7352 | True | ✅ |

### Pass 5 — Signal Agreement: ✅ PASS
_Semantic dispersion group rankings match token entropy rankings._

| Model | Entropy Order | Dispersion Order | Agree | Spearman ρ | p-value | Pass |
|-------|--------------|-----------------|-------|------------|---------|------|
| llama3.1 | A>C>B | A>C>B | True | 0.7209 | 0.0 | ✅ |
| mistral | A>C>B | A>C>B | True | 0.7194 | 0.0 | ✅ |

---

## Figures Generated

- `figures/fig1_distributions.png` — Violin + box plots by group
- `figures/fig2_temp_slopes.png`   — Temperature sensitivity slopes
- `figures/fig3_correlation.png`   — Token entropy vs semantic dispersion scatter
- `figures/fig4_heatmap.png`       — Mean entropy heatmap (group × temperature)
