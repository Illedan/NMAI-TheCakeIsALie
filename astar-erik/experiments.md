# Experiment Ideas — Ranked by Potential Impact

Current baseline: **86.47** (with adaptive regularization target)

## Tier 1: Most Promising (likely +1-3 points)

### 1. Posterior Ensemble / Model Averaging
**Idea**: Instead of one HC-tuned parameter set, keep top-K parameter sets from HC restarts and average their mean-field predictions.
**Why promising**: Reduces overfitting to a single parameter set. HC restarts already find different solutions — averaging should smooth variance. Cost: trivial compute (K more MF runs, ~10ms each).
**Status**: Not tried

### 2. Latent Class / Round Personality Detection
**Idea**: Classify each round into 2-3 archetypes (growth/stable/collapse) from initial observations, then use archetype-specific priors. E.g., "harsh winter" rounds have flat settlement distributions vs "expansionist" rounds have concentrated settlements near initial ones.
**Why promising**: We already detect settlement_regime. Adding 1-2 more archetypes could better target the non-growth rounds (R3, R8, R10 which score differently).
**Status**: Partially done (settlement_regime flag). Needs refinement.

### 3. Temperature Scaling / Calibration
**Idea**: Our predicted probabilities may be systematically over/under-confident. Apply a global temperature T to logits: p_c = softmax(log(p_c) / T). Optimize T on historical round data.
**Why promising**: This is free (post-processing only). Even a small calibration improvement helps on high-entropy cells where KL divergence is weighted most.
**Status**: Not tried

### 4. Influence Maximization Querying
**Idea**: Instead of querying where entropy is highest (our current phase 2 strategy), query where observations maximally inform predictions for UNOBSERVED cells. A cell at the settlement frontier informs more cells than one in the middle of a known cluster.
**Why promising**: Current entropy-chasing queries often land in similar areas. Spreading queries to maximize coverage could help.
**Status**: Not tried

### 5. Dirichlet Prior Smoothing
**Idea**: Replace our `obs_counts[c] / n` empirical with Dirichlet-posterior: (obs_counts[c] + alpha * prior[c]) / (n + alpha). The prior could be MF prediction, alpha controls smoothing.
**Why promising**: We currently do a weighted blend of MF and observations. Dirichlet smoothing is the Bayesian-correct way to do this. Could fix edge cases where few observations dominate.
**Status**: We have something similar (mc_w blending), but not properly Bayesian.

## Tier 2: Good Potential (likely +0.5-1.5 points)

### 6. K-NN Patch Transfer
**Idea**: For unobserved patches, find the most similar observed patch (by initial terrain pattern) and transfer its correction factors.
**Why promising**: Our current approach applies the SAME global correction to all unobserved cells. Similar terrain patches should behave similarly.
**Status**: Not tried

### 7. Voronoi / Influence Regions
**Idea**: Partition the map into settlement influence regions. Each region's prediction is shaped by its settlement's neighbors, not just global correction.
**Why promising**: Different parts of the map may have different expansion dynamics. The settlement influence model is physically motivated.
**Status**: We have dist_correction (by BFS distance) which partially captures this.

### 8. Two-Phase Wide-then-Deep
**Idea**: Phase 1: 5 queries spread across different map regions (broad scan). Phase 2: focus remaining queries on regions that showed unexpected behavior.
**Why promising**: Currently we focus all phase-1 queries on one tile. This could miss dynamics in other parts of the map.
**Status**: Not tried. Risk: fewer queries per tile = worse HC.

### 9. Kernel Regression on Features
**Idea**: For each cell, compute features (ns, dist, coast, forest density) and predict class probs by kernel-weighted average of observed cells with similar features.
**Why promising**: More flexible than global correction factors. Could capture nonlinear feature interactions.
**Status**: Not tried

### 10. Confidence Capping / Entropy Floor
**Idea**: Never predict P(class) > 0.95 for any dynamic cell. Force minimum entropy.
**Why promising**: Overconfident predictions are punished heavily by KL divergence. A small entropy floor costs little when correct but saves a lot when wrong.
**Status**: We have PROB_FLOOR=0.0001 but no per-cell confidence cap.

## Tier 3: Worth Trying (likely +0-1 points)

### 11. Monte Carlo Query Planner
Simulate future observation value before choosing next query location.

### 12. Bayesian Optimization for HC
Replace random perturbation HC with BO using a GP surrogate.

### 13. Spatial Smoothing (MRF/CRF)
Post-process predictions with spatial consistency constraints.

### 14. Low-Rank Tensor Prior
Approximate the 40x40x6 prediction tensor with rank-R decomposition.

### 15. Disagreement-Based Querying
Query where multiple model variants disagree most.

## Tier 4: Unlikely to Help

- Graph-based methods (settlement interaction graphs) — too complex, little data
- Topological data analysis — overkill for 40x40 grid
- Fourier/wavelet features — map is small, spatial patterns are simple
- Genetic algorithms for HC — HC with restarts already works well
- NMF/tensor completion — not enough observed data per round
