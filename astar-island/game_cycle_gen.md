# Astar Island — Empirical Game Mechanics Summary

Compiled from analysis of 75 replays across 15 rounds.

## Initialization

### Map
- 40×40 grid with terrain: Ocean (10), Plains (11), Forest (4), Mountain (5)
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
- Food gain per tile: **(0.023 ± 0.004) per food tile** (plains or forest) with ≥1 neighboring
  settlement, shared equally among all adjacent settlements. This is approximately constant
  across rounds (low std), not a strong hidden parameter.
- Ocean tiles do NOT produce food (ports get no food bonus from water)
- Mountain tiles do NOT produce food
- Food production is stochastic even within the same round (tiles fire independently with some probability)

### Defence Growth
 - Defence growth is a **linear function of population** (ddef ∝ def) E=0.083 ± 0.032.
   Defense is clamped to [0.00, 1.00]


### Population Growth
- Population growth is a **linear function of population** (dpop ∝ pop)
- The observed growth curve shows a kink at population ~1.39: above this threshold,
  the apparent growth rate drops by roughly half. This is NOT because the growth
  rate changes — it's because settlements above 1.39 start spawning hi-tier children,
  and **spawning a hi-tier child costs the parent ~0.10 population**. This cost is
  masked by the fact that only high-population settlements spawn hi-tier children,
  so their net growth is still positive.
- Lo-tier spawning (on ruins) does NOT cost the parent population
- Population is NOT transferred to children — child pop is a fixed amount per tier.
  The parent's ~0.10 loss is a spawning cost, not a transfer.

### Settlement Spawning

**Spawn probability** (logistic CDF vs parent population):
```
P(spawn | pop) = 1 / (1 + exp(-(pop - mu) / s))
  mu: E=2.184 std=0.288  (hidden parameter — population for 50% spawn chance)
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
Ruin preference ratio: E=8.0x ± 1.6

When a high-pop parent has both a ruin and fresh tiles at the same distance, each ruin tile is
8x more likely to be chosen than each fresh tile. This is consistent across rounds (range 5.0x
to 10.7x, std=1.6) — it may be a constant rather than a hidden parameter.

**Child tier is determined by the tile the child spawns on:**
- **Ruin tile → ALWAYS lo-tier** (100% of ruin spawns are lo-tier)
- **Plains/Forest tile → hi-tier** (spawning onto fresh land)

**Mid-tier is NOT a real spawning mode** — it's a hi-tier child that got immediately
raided in the same step. Evidence:
- 95% of mid-tier children have enemy settlements within distance 3
- 0% of mid-tier spawn on ruins (all on plains/forest, same as hi-tier)
- Mid-tier wealth ≈ 92% of expected hi-tier wealth (raid barely affects wealth)
- The raid costs: ~0.075 pop, ~0.04 defense, ~0.07 food, ~0.001 wealth
- So mid-tier stats (0.425, 0.16) = hi-tier (0.50, 0.20) minus raid damage

**Tier stats (true spawning tiers only):**
```
┌──────┬───────┬───────┬──────────┬───────────────┬─────────────────────┐
│ Tier │  Pop  │  Def  │ Wealth % │ Food          │ Spawns on           │
├──────┼───────┼───────┼──────────┼───────────────┼─────────────────────┤
│ Lo   │ 0.400 │ 0.150 │  ~10%    │ ~0.15 (const) │ Ruin tiles only     │
├──────┼───────┼───────┼──────────┼───────────────┼─────────────────────┤
│ Hi   │ 0.500 │ 0.200 │  ~20%    │ 0.15+transfer │ Plains/Forest tiles │
└──────┴───────┴───────┴──────────┴───────────────┴─────────────────────┘
```

- Pop and defense are **fixed per tier** (not transferred from parent)
- Wealth is **directly transferred** as a percentage of parent wealth (R²=0.82)
  - Hi: 21.7% ± 1.3% (constant across rounds)
  - Lo: 9.8% ± 1.1% (constant across rounds)
- Hi-tier food = ~0.15 baseline + food transfer from parent (hidden param, E=0.092 std=0.077)
- Lo-tier food = ~0.15 (constant, no parent transfer)
- Hi-tier parents lose ~0.22 food; lo-tier parents lose nothing
- Child population is NOT taken from the parent (created from nothing)
- Closer children get priority for hi-tier (sequential resource allocation)
- Wealth is a depleting resource — destroyed on collapse, not conserved
- **Lo-tier children on ruins inherit NOTHING from the ruined settlement.**
  When a settlement collapses, its resources are destroyed. The child's stats
  come entirely from its parent (10% wealth, ~0.15 food). Same-owner rebuilds
  do not recover the old settlement's resources. (69.6% of ruin rebuilds are
  same-owner, 30.4% are different-owner — no stat difference between them.)
- **Raid damage is proportional to the settlement's current stats** (percentage-based):
  - **Defense: ~20% lost per raid** (mean 20.2%, exact 20.0% from mid-tier, R²=0.75, no other dependencies)
  - **Wealth: ~21% lost per raid** (mean 21.1%, R²=0.63, no strong dependencies on other stats)
  - **Population: ~15% lost per raid** (exact 15.0% from mid-tier; regression gives 12.5% for
    established settlements because pop growth in the same step partially offsets the loss)
  - **Food: hard to isolate** (food production/consumption happens same step; corr with own food = -0.82
    but percentage is confounded — estimated ~6-12% from regression, highly variable)
  - Raid percentage is roughly constant across rounds (not a hidden parameter)
  - The number of nearby enemies does NOT significantly change the per-raid damage percentage —
    it only affects the probability of BEING raided, not the damage per raid
  - Mid-tier frequency varies 1.8%-32.5% per round depending on enemy density

### Port Formation
Settlements with 2+ ocean neighbors can become ports:
```
P(port | food, ocean>=2) = rate_above if food >= thresh, else ~0
  thresh:       E=0.454 std=0.182  (hidden parameter)
  rate_above:   E=0.104 std=0.010  (~constant across rounds)
  wealth_bonus: E=0.005 std=0.005  (small one-time gain)
```
- Essentially a step function in food: below threshold → ~0%, above → ~10.4%
- The food threshold is a hidden parameter; the max rate is nearly constant
- Ports gain ~0.003-0.004 wealth per step ongoing (trade)
- Port trade food effects are negligible

### Raiding / Conflict
  Raid success = raid leads to the victim losing wealth:
  Per-round rates range from 52.9% to 70.4%, with low variation (mu=60.5%) (std=4.8%).
  On a successful raid:
  - Victim loses ~40% of their wealth (E=0.401 ± 0.056)
  - Raider gains ~23% of the victim's wealth (E=0.227 ± 0.045)
  - Transfer efficiency ~57% — the raider gets about 57% of what the victim lost, the other 43% is
   destroyed
  ┌──────────────────────────────────────────┬───────┬──────┐
  │                  Metric                  │   E   │ std  │
  ├──────────────────────────────────────────┼───────┼──────┤
  │ P(raider loses wealth | failed raid)     │ 17.4% │ 4.4% │
  ├──────────────────────────────────────────┼───────┼──────┤
  │ Raider % wealth lost (when they do lose) │ ~20%  │ ~5%  │
  └──────────────────────────────────────────┴───────┴──────┘

  So the full raid wealth model:
  - 60% of raids succeed: victim loses ~40% wealth, raider gains ~23% of victim's wealth
  - 40% of raids fail: 17% chance raider loses ~20% of their own wealth, otherwise no wealth
  change

  Raid model: P(raid from dist d) = p_raid × exp(-d²/(2σ²))

  ┌────────────────────────────┬─────────────────┬─────────────────┐
  │         Parameter          │    Non-port     │      Port       │
  ├────────────────────────────┼─────────────────┼─────────────────┤
  │ p_raid (base probability)  │ E=0.126 ± 0.063 │ E=0.139 ± 0.092 │
  ├────────────────────────────┼─────────────────┼─────────────────┤
  │ sigma (range, half-normal) │ E=1.67 ± 0.10   │ E=2.52 ± 0.51   │
  └────────────────────────────┴─────────────────┴─────────────────┘

  Key findings:
  - Port and non-port raiders have similar base raid probability (~13% per step)
  - Ports have ~50% larger sigma (2.5 vs 1.7) — confirming they raid at greater range
  - At dist 1: both ~13% raid chance. At dist 3: non-port ~4%, port ~7%. At dist 5: non-port ~0.3%, port ~1.5%
  - p_raid varies significantly per round (hidden parameter), sigma is more stable

- Conquest (owner change): P(owner change | successful raid) = 23.0% ± 16.1%

### Winter / Collapse
- Food consumption per step: **(0.083 ± 0.015) × population**
  - Estimated from isolated settlements (no enemies, no spawning) across all 15 rounds
  - food_new = food_old + food_production - 0.083 × population
  - If food drops below 0 → the settlement collapses (starvation)
- Settlements can also collapse from low defence:
    P(collapse | defense) = sigmoid(-defense / s)
    where s is the per-round hidden parameter (E=0.158, std=0.038)
- When a settlement collapses → becomes a Ruin tile
  - All wealth is destroyed
  - Settlement is removed from the settlements list
- Ruins transition immediately next step (never stay as ruin for >1 step):
  - If a same-faction settlement is within range → rebuilt as Settlement or Port
  - If NOT rebuilt by a settlement, the ruin becomes forest or plains at a
    **fixed ratio independent of neighboring tiles** (not affected by adjacency):
    - **32.4% → Forest** (E=0.324, std=0.026 across 15 rounds)
    - **67.6% → Plains** (E=0.676, std=0.026 across 15 rounds)
  - This is a constant, not a hidden parameter (very low per-round variance)

### Environment
- Forest does **NOT** spread onto plains (0% across 2M+ observations)
- Rare transitions: Plains→Ruin (~0.04%), Forest→Ruin (~0.05%)

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
| port_rate_above | 0.104 ± 0.010 | Max port formation rate |
| hi_wealth_ratio | 21.7% ± 1.3% | Wealth transfer to hi-tier child |
| lo_wealth_ratio | 9.8% ± 1.1% | Wealth transfer to lo-tier child |
| lo_food | 0.148 ± 0.013 | Lo-tier child food (harvest baseline) |
| hi_pop | 0.500 | Hi-tier child population |
| lo_pop | 0.400 | Lo-tier child population |
| hi_def | 0.200 | Hi-tier child defense |
| lo_def | 0.150 | Lo-tier child defense |
| port_wealth_bonus | 0.005 ± 0.005 | One-time wealth on port formation |
| port_ongoing_wealth | ~0.003-0.004/step | Ongoing wealth from port status |
| hi_spawn_pop_cost | ~0.10 | Population cost to parent for hi-tier spawn |
| lo_spawn_pop_cost | ~0 | No population cost for lo-tier (ruin rebuild) |
| raid_pop_damage | ~0.075 | Pop lost when newborn is immediately raided |
| raid_def_damage | ~0.04 | Defense lost when newborn is immediately raided |
| raid_food_damage | ~0.07 | Food lost when newborn is immediately raided |
| ruin → forest (no settle) | 32.4% ± 2.6% | Fraction of non-rebuilt ruins becoming forest |
| ruin → plains (no settle) | 67.6% ± 2.6% | Fraction of non-rebuilt ruins becoming plains |
| ruin → lo-tier | 100% | Children on ruin tiles are always lo-tier |
| plains/forest → hi-tier | 100% (83% survive unraided) | Fresh land = hi-tier, but 12% get immediately raided to mid-tier stats |

## Per-Round Hidden Parameter Values (15 rounds)

```
round_id   mu_spawn  s_spawn  lambda  p_multi  port_th  alpha_p  alpha_f  hi_food_xfer
────────   ────────  ───────  ──────  ───────  ───────  ───────  ───────  ────────────
2a341ace     3.000    0.846   0.495    0.101    0.432    0.010    0.055      +0.011
324fde07     1.881    0.280   0.619    0.068    0.723    0.017   -0.008      +0.151
36e581f1     1.893    0.294   2.623    0.051    0.430    0.023   -0.004      +0.091
71451d74     1.997    0.318   0.575    0.067    0.506   -0.008    0.077      +0.047
75e625c3     2.259    0.488   1.620    0.049    0.591    0.031    0.060      +0.250
76909e29     2.647    0.657   0.464    0.067    0.834    0.013   -0.001      +0.069
795bfb1f     1.609    0.111   2.515    0.019    0.348    0.007    0.028      +0.103
7b4bda99     2.350    0.529   0.808    0.136    0.756    0.011    0.042      +0.030
8e839974     2.304    0.487   0.607    0.060    0.691    0.002    0.056      +0.118
ae78003a     2.407    0.560   0.603    0.072    0.336    0.000    0.048      -0.002
c5cdf100     2.290    0.431   0.582    0.110    0.741    0.007    0.121      +0.129
cc5442dd     1.851    0.248   0.491    0.084    0.468    0.001    0.058      +0.201
d0a2c894     1.774    0.217   1.371    0.052    0.351    0.000    0.072      +0.152
f1dac9a9     2.681    0.612   1.700    0.126    0.480    0.021    0.099      -0.054
fd3c92ff     1.897    0.298   1.206    0.076    0.270    0.017    0.019      +0.078
────────   ────────  ───────  ──────  ───────  ───────  ───────  ───────  ────────────
E            2.189    0.425   1.085    0.076    0.531    0.010    0.048      +0.092
std          0.378    0.190   0.708    0.030    0.171    0.010    0.038       0.077
```
