# Astar Island — Empirical Game Mechanics Summary

Compiled from analysis of 75 replays across 15 rounds.

## Initialization

### Map
- 40x40 grid with terrain: Ocean (10), Plains (11), Forest (4), Mountain (5)
- Ocean borders the map, fjords cut inland, mountain chains via random walks
- Forest patches clustered, initial settlements placed on land cells spaced apart
- Map seed determines terrain layout (visible, deterministic)

### Initial Settlements
- Stats drawn from uniform distributions (same across all rounds, not hidden):
  - Population: U(0.50, 1.50)
  - Food: U(0.30, 0.80)
  - Wealth: U(0.10, 0.50)
  - Defense: U(0.20, 0.60)
- Each settlement gets a unique owner_id (faction)
- Initial port status: ~60-100% for settlements with 2+ ocean neighbors, ~6% for 1 ocean, 0% for 0

## Per-Step Evolution

Each of the 50 steps consists of several phases. The exact ordering is not fully known,
but the mechanics below have been identified from replay analysis.

### Food Production
- Each Plains and Forest tile adjacent to at least one settlement produces food stochastically
- Food produced by a tile is **shared equally** among all adjacent settlements
- Model: `dfood = alpha_p * sum(1/n_adj for adj plains) + alpha_f * sum(1/n_adj for adj forest) - beta * population`
  - alpha_plains: E=0.016 std=0.011 (hidden parameter)
  - alpha_forest: E=0.022 std=0.015 (hidden parameter)
  - beta (consumption): E=0.024 std=0.040
- Ocean tiles do NOT produce food (ports get no food bonus from water)
- Mountain tiles do NOT produce food
- Food production is stochastic even within the same round (tiles fire independently with some probability)

### Population Growth
- Population growth is a **linear function of population** (dpop ~ pop)
- The observed growth curve shows a kink at population ~1.39: above this threshold,
  the apparent growth rate drops by roughly half. This is NOT because the growth
  rate changes -- it's because settlements above 1.39 start spawning hi-tier children,
  and **spawning a hi-tier child costs the parent ~0.10 population**. This cost is
  masked by the fact that only high-population settlements spawn hi-tier children,
  so their net growth is still positive.
- Lo-tier spawning (on ruins) does NOT cost the parent population
- Population is NOT transferred to children -- child pop is a fixed amount per tier.
  The parent's ~0.10 loss is a spawning cost, not a transfer.

### Settlement Spawning

**Spawn probability** (logistic CDF vs parent population):
```
P(spawn | pop) = 1 / (1 + exp(-(pop - mu) / s))
  mu: E=2.184 std=0.288  (hidden parameter -- population for 50% spawn chance)
  s:  E=0.432 std=0.166
```

**Multi-spawn**: After spawning one child, the parent rolls again with probability p_multi.
Repeats until a roll fails or no available tiles remain (geometric distribution).
```
p_multi: E=0.076 std=0.030  (hidden parameter)
```

**Spawn location** (exponential/geometric in Chebyshev distance from parent):
```
P(dist=d) = exp(-lambda*(d-1)) * (1 - exp(-lambda)),  d=1,2,...
  lambda: E=1.056 std=0.664  (hidden parameter)
  => P(d=1) = 65%, P(d=2) = 23%, P(d=3) = 8%
```
Normalized to available tiles at each distance.

**Child tier is determined by the tile the child spawns on:**
- **Ruin tile -> ALWAYS lo-tier** (100% of ruin spawns are lo-tier)
- **Plains/Forest tile -> mostly hi-tier** (83% hi, 12% mid, 4% lo)

The apparent food/population threshold for tier selection is actually a confound:
parents with more resources expand onto fresh land (hi-tier), while resource-poor
parents only rebuild nearby ruins (lo-tier).

**Tier stats:**
```
+------+-------+-------+----------+--------------+
| Tier |  Pop  |  Def  | Wealth % | Food         |
+------+-------+-------+----------+--------------+
| Lo   | 0.400 | 0.150 |  ~10%    | ~0.15 (const)|
+------+-------+-------+----------+--------------+
| Mid  | 0.425 | 0.160 |  ~20%    | variable     |
+------+-------+-------+----------+--------------+
| Hi   | 0.500 | 0.200 |  ~20%    | 0.15+transfer|
+------+-------+-------+----------+--------------+
```

- Pop and defense are **fixed per tier** (not transferred from parent)
- Wealth is **directly transferred** as a percentage of parent wealth (R2=0.82)
  - Hi: 21.7% +/- 1.3% (constant across rounds)
  - Lo: 9.8% +/- 1.1% (constant across rounds)
- Hi-tier food = ~0.15 baseline + food transfer from parent (hidden param, E=0.092 std=0.077)
- Lo-tier food = ~0.15 (constant, no parent transfer)
- Hi-tier parents lose ~0.22 food; lo-tier parents lose nothing
- Child population is NOT taken from the parent (created from nothing)
- Closer children get priority for hi-tier (sequential resource allocation)
- Wealth is a depleting resource -- destroyed on collapse, not conserved

### Port Formation
Settlements with 2+ ocean neighbors can become ports:
```
P(port | food, ocean>=2) = rate_above if food >= thresh, else ~0
  thresh:       E=0.454 std=0.182  (hidden parameter)
  rate_above:   E=0.104 std=0.010  (~constant across rounds)
  wealth_bonus: E=0.005 std=0.005  (small one-time gain)
```
- Essentially a step function in food: below threshold -> ~0%, above -> ~10.4%
- The food threshold is a hidden parameter; the max rate is nearly constant
- Ports gain ~0.003-0.004 wealth per step ongoing (trade)
- Port trade food effects are negligible

### Raiding / Conflict
- Settlements raid enemies; collapse rate increases with nearby enemy count:
  - 0 enemies within dist 3: ~2.4% collapse (baseline -- winter/starvation)
  - 1 enemy: ~3.9%
  - 2 enemies: ~7.4%
  - 3 enemies: ~10.6%
  - 5+ enemies: ~21.0%
- Effective raid range: 1-4 tiles (collapse rate flattens to baseline beyond dist 4)
- **Port enemies extend raid range** by ~1-2 tiles (longships):
  - At dist 3: port enemy -> 12% collapse vs non-port -> 6% (2x)
  - At dist 4-5: ~1.6-1.8x
- Conquest (owner change): ~758 events across 15 rounds; always involves stat loss
  (defense always drops, population always drops)
- Raiders do NOT gain the victim's wealth -- most wealth is destroyed on collapse
- Settlements near enemy ruins collapse more (~8% at 1 ruin neighbor vs ~5% at 0)

### Winter / Collapse
- Collapse probability depends on food/population ratio:
  - Low food/pop -> high collapse probability
  - Settlements can collapse from starvation (low food), raids, or harsh winters
- When a settlement collapses -> becomes a Ruin tile
  - All wealth is destroyed
  - Settlement is removed from the settlements list
- Ruins transition immediately next step (never stay as ruin for >1 step):
  - ~48% -> Settlement (rebuilt by nearby same-faction settlement)
  - ~33% -> Plains (fade to empty)
  - ~18% -> Forest (reclaimed by nature)
  - ~1% -> Port (if coastal, rebuilt as port)

### Environment
- Ruins are reclaimed: see ruin transitions above
- Forest can be cleared for settlement expansion
- Rare transitions: Plains->Ruin (~0.04%), Forest->Ruin (~0.05%)

## Hidden Parameters (vary per round)

These parameters are NOT visible in the initial state and must be estimated from
viewport observations or replay data:

| Parameter | E | std | Description |
|-----------|------|------|-------------|
| mu (spawn pop) | 2.184 | 0.288 | Population for 50% spawn chance |
| s (spawn steepness) | 0.432 | 0.166 | Logistic steepness |
| lambda (spawn dist) | 1.056 | 0.664 | Spawn distance decay |
| p_multi | 0.076 | 0.030 | Multi-spawn probability |
| port_thresh | 0.454 | 0.182 | Food threshold for port formation |
| alpha_plains | 0.016 | 0.011 | Food per effective plains tile |
| alpha_forest | 0.022 | 0.015 | Food per effective forest tile |
| beta | 0.024 | 0.040 | Food consumption per population |
| hi_food_transfer | 0.092 | 0.077 | Extra food hi-tier children get |
| mu_f (tier food) | 0.645 | 0.131 | Food threshold for hi-tier (in 2D logistic) |
| mu_p (tier pop) | 1.386 | 0.017 | Pop threshold for hi-tier (~constant) |

## Constants (same across all rounds)

| Parameter | Value | Description |
|-----------|-------|-------------|
| port_rate_above | 0.104 +/- 0.010 | Max port formation rate |
| hi_wealth_ratio | 21.7% +/- 1.3% | Wealth transfer to hi-tier child |
| lo_wealth_ratio | 9.8% +/- 1.1% | Wealth transfer to lo-tier child |
| lo_food | 0.148 +/- 0.013 | Lo-tier child food (harvest baseline) |
| hi_pop | 0.500 | Hi-tier child population |
| lo_pop | 0.400 | Lo-tier child population |
| hi_def | 0.200 | Hi-tier child defense |
| lo_def | 0.150 | Lo-tier child defense |
| port_wealth_bonus | 0.005 +/- 0.005 | One-time wealth on port formation |
| port_ongoing_wealth | ~0.003-0.004/step | Ongoing wealth from port status |
| ruin on plains -> lo-tier | 100% | Children on ruin tiles are always lo-tier |
| ruin on plains/forest -> hi-tier | ~83% | Children on fresh land are mostly hi-tier |
