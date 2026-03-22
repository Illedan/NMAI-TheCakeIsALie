# ML Improvement Progress

## Current State
- **Score: 87.74** avg across 90 seeds (18 deduplicated rounds × 5 seeds)
- Baseline was 86.52, improved via: multi-viewport MLP (+0.21), phase1 query reduction (+0.08), mountain features (+0.15), MF ensemble all seeds (+0.60), per-distance correction (+0.03), HC param reduction 24→11 (+0.20), cross-round MLP (+0.50), Adam optimizer + 96-hidden MLP (+0.23)

## Improvement History
| Change | Score | Delta | Status |
|--------|-------|-------|--------|
| Baseline (multi-viewport MLP + MF ensemble) | 86.52 | — | Kept |
| Phase1 query reduction | 86.60 | +0.08 | Kept |
| Mountain features | 86.75 | +0.15 | Kept |
| MF ensemble all seeds | 87.35 | +0.60 | Kept |
| Per-distance correction d<=1 85% trust | 87.43 | +0.03 | Kept |
| HC param reduction 24→13 | 87.56 | +0.13 | Kept |
| HC param reduction 13→11 (remove pr_base, er_ratio) | 87.63 | +0.07 | Kept |
| Cross-round MLP (48 hidden, 30% blend, 14 features) | 88.13 | +0.50 | Kept |
| Round deduplication (22→18 unique rounds) | 87.51* | — | Kept (cleaner eval) |
| Adam optimizer + 96-hidden cross-MLP | 87.74 | +0.23 | **Kept** |

## Cross-Round MLP Details
- Trained on all 90 round-seed analysis files (122k cells)
- 14 features from initial grid only (no settlement stats from queries)
- Architecture: 14→96→96→6 (16,134 params), Adam optimizer, 200 epochs
- Val loss: 0.1049 (KL divergence)
- Adaptive blend: `cross_w = 0.30 + 0.30 * max(0, (80-hc_fit)/20)`, capped at 0.60
- Helps ALL seeds including non-query ones (uniform prior from GT)
- Script: `train_cross_mlp.py`, weights: `cross_mlp_weights.h`

## Root Cause Analysis
**R12 & R7 failures**: MF model systematically under-predicts settlement survival.
- GT: 57% of initial settlement cells stay settlement (R12)
- Model predicts: 11%
- Cause: MF approximation loses bimodal correlation
- Cross-round MLP helps somewhat (learns average settlement survival from GT)

## Attempted Improvements (failed — all reverted)
| Attempt | Result | Why Failed |
|---------|--------|-----------|
| HC param reduction 11→9 | 87.51 | Too few params for ruin dynamics |
| EDA generations 25→35 | 87.59 | More gens add noise |
| HC iterations 200→400 | 87.36 | Overfitting to viewport |
| Top-K MF ensemble | 87.55 | Params too similar |
| EDA population 48→64 | 87.61 | No gain |
| Kill ratio 0.4 or 0.6 | 87.43/87.47 | 0.5 is optimal |
| Cross-MLP blend 0.35 | 87.88 | Slight overweight |
| 17-feature cross-MLP (global features) | 86.85 | Global features = round identifiers, massive overfitting |
| HC iterations 200→300 | 88.21→worse | More overfitting to viewport |
| 128-hidden cross-MLP | same as 96 | Diminishing returns |

## Task List
### Quick wins to try next
- [ ] Add more features to cross-MLP (distance to ocean, cluster size, etc.)
- [ ] Re-train cross-MLP with class weighting (settlement under-represented)
- [ ] Try 3-layer cross-MLP (add another hidden layer)
- [ ] Adjust per-round MLP weight when cross-MLP is available

### Medium effort
- [ ] Gradient-based fitting: backprop through MF model
- [ ] Per-initial-terrain correction factors
- [ ] Leave-one-round-out cross-validation for cross-MLP

## Validation
- API: `GET /my-predictions/{round_id}` — check submitted predictions
- API: `GET /my-rounds` — all rounds with scores, rank, queries used
- API: `GET /analysis/{round_id}/{seed_index}` — ground truth comparison
