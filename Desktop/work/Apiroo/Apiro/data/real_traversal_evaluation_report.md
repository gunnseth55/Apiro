# Apiro — Real Traversal Evaluation Report

## Overall Verdict
**Stop Reason**: saturation
**Graph Size**: 20 nodes, 18 edges
**Entropy Trend Slope**: -0.02893 nats/expansion (✅ PASS)

## Key Heuristics Validation

1. **Epistemic Convergence (✅ PASS)**
   - Starting Entropy: 0.7500 nats
   - Ending Entropy: 0.5579 nats
   - Heuristic Expectation: Linear slope should be negative, showing that the model converges to certainty as information is added.
2. **Epistemic Saturation (✅ PASS)**
   - Saturation window: 5 nodes. Saturation threshold theta: 0.25
   - Heuristic Expectation: The loop should terminate automatically when information gains saturate.
3. **Logical Contradictions (⚡ CONTRADICTIONS FLAGGED)**
   - Found 5 contradiction relations in the graph.
4. **Rabbit Hole Detection (✅ PASS)**
   - Flagged 0 speculative rabbit hole paths.

## Expansion Chain Log

| Step | Node ID | Entropy (nats) | Depth | Domain | Claim |
|------|---------|----------------|-------|--------|-------|
| 1 | node_0 | 0.7500 | 0 | pathophysiology | Acute myocardial infarction (STEMI) |
| 2 | node_1 | 0.7000 | 0 | pathophysiology | Coronary artery disease with acute plaque rupture |
| 3 | node_0_c0 | 0.6941 | 1 | genetics | The BAG3 gene variant NM_004281.4(BAG3):c.626C>T (p.Pro209Leu) may contribute to the pathogenesis of acute myocardial infarction through disrupted sarcomere function. |
| 4 | node_0_c2 | 0.6906 | 1 | genetics | The presence of multiple BAG3 gene variants, including NM_004281.4(BAG3):c.626C>T (p.Pro209Leu), may indicate a genetic predisposition to dilated cardiomyopathy 1HH and myofibrillar myopathy 6 in patients with acute myocardial infarction. |
| 5 | node_1_c2 | 0.6838 | 1 | imaging | PRKAG2 variant NM_016203.4(PRKAG2):c.471C>T or c.1098A>G could lead to aberrant AMP-activated protein kinase activity, exacerbating atherosclerotic plaque formation and instability. |
| 6 | node_0_c2_c0 | 0.5579 | 2 | imaging | The presence of NM_004281.4(BAG3):c.626C>T (p.Pro209Leu) may indicate a higher risk of myofibrillar myopathy 6 in patients with acute myocardial infarction. |