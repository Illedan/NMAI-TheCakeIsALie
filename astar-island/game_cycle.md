# astar-island game cycle
Each simulation of astar-island starts with an initial state, before it evolves over N cycles, each of which has five distinct steps.

## initialization of settlement parameters
All four stats are consistent with uniform distributions. Only 1 out of 28 per-round tests
failed at p=0.05 (food for round 36e581f1 at p=0.047, likely a false positive). The combined
test across all rounds also passes for all stats.

The initial settlement stats are drawn from:
- Population: Uniform(0.50, 1.50)
- Food: Uniform(0.30, 0.80)
- Wealth: Uniform(0.10, 0.50)
- Defense: Uniform(0.20, 0.60)

These ranges are identical across all rounds — they're not hidden parameters. The initial
conditions are fully deterministic given the map seed.

## Evolution
The map evolves stochastically over N cycles, each of which has five consecutive steps:
  - 1. Growth: Settlements grow according to these rules:

        Settlement spawn probability (logistic CDF vs parent population):
        P(spawn|pop) = 1 / (1 + exp(-(pop - mu) / s))
          mu:  E=2.184  std=0.288    (population for 50% spawn chance)
          s:   E=0.432  std=0.166    (steepness of transition)

        P(multi_spawn|spawn & nearby fields)
          mu : 

        Spawn distance (exponential/geometric):
        P(dist=d) = exp(-lambda*(d-1)) * (1 - exp(-lambda)),  d=1,2,...
          lambda: E=1.056  std=0.664
          ()=> P(d=1) = 65%, P(d=2) = 23%, P(d=3) = 8%) then normalized to the available squares.

        Port formation (step function, settlements with 2+ ocean):
        P(port|food) = rate_above if food >= thresh, else ~0
          thresh:     E=0.454  std=0.182
          rate_above: E=0.104  std=0.010

        Food production (linear model):
        dfood = alpha_p * eff_plains + alpha_f * eff_forest - beta * pop
          alpha_plains: E=0.016  std=0.011
          alpha_forest: E=0.022  std=0.015
          beta:         E=0.024  std=0.040

 The children that spawn fall into distinct tiers, and have the same owner_id as their parent. The known *tiers* are:
 When a child is spawed the parent has some probability of spawning that child in the low or the high tier. If the parent has less than the FOOD_TRANSFER hidden variable food it spawns a lo-tier child. Else the probability of spawning a hi-tier child is given by the child_tier_distribution function. Depending on if the child is hi or lo tier t gets the following stats, and the following amount of wealth in percent of the parent wealth and food is transfered to the child:
  ┌──────┬───────┬───────┬──────────┬──────────────┐
  │ Tier │  Pop  │  Def  │ Wealth % │Food transfer │
  ├──────┼───────┼───────┼──────────┼──────────────┤
  │ Low  │ 0.400 │ 0.150 │ ~10%     │0             │
  ├──────┼───────┼───────┼──────────┼──────────────┤
  │ High │ 0.500 │ 0.200 │ ~20%     │FOOD_TRANSFER │
  └──────┴───────┴───────┴──────────┴──────────────┘
  The mid tier was introduced after the first two, and more tiers may arise. The next part of the Growth phase is that the settlements harvest the area around them. Plains and Forest give food. Ports don't gain food from Water, noone gets food from Mountain. Ports may seem to generate food at first glance, but very little, and likely confounded by generally high food gain in high expansion games. Tiles produce food with some probability, like in Catan, but the food produced is split between all neighbors to the tile.

  Having a port in the trade phase gives a small wealth gain of 0.005+-0.005 each step.




Population decreases food in winter: food -= population*beta. If food drops to 0, the settlement becomes ruin.



  Per-tier child starting stats (15 rounds):

  ┌──────────────┬─────────────────┬─────────────────┐
  │              │   Hi tier (A)   │   Lo tier (C)   │
  ├──────────────┼─────────────────┼─────────────────┤
  │ Child food   │ E=0.239 ± 0.085 │ E=0.148 ± 0.013 │
  ├──────────────┼─────────────────┼─────────────────┤
  │ Wealth ratio │ E=21.7% ± 1.3%  │ E=9.8% ± 1.1%   │
  └──────────────┴─────────────────┴─────────────────┘

  Key findings:
  - Lo tier food is stable across rounds (0.148 ± 0.013) — essentially a constant ~0.15
  - Hi tier food varies enormously (0.239 ± 0.085, range 0.09-0.40) — it's a hidden parameter,
  likely correlated with overall food production rates
  - Wealth ratios are very stable: hi gets ~22% of parent wealth, lo gets ~10%, consistent across
  all rounds (std ~1%)
  - Pop (0.50/0.40) and defense (0.20/0.15) remain fixed per tier as before


Striking difference:

  Hi-tier parents lose a lot of food, lo-tier parents don't:
  - Hi-tier parent dfood: -0.219 (loses ~0.22 food)
  - Lo-tier parent dfood: +0.028 (actually gains food!)
  - Difference: -0.235 ± 0.093 — consistent across ALL 15 rounds (0/15 positive)

  Hi-tier parents also lose much more wealth:
  - Hi-tier parent dwealth: -0.040
  - Lo-tier parent dwealth: -0.005

  And the parent food loss tracks the child food almost exactly per round:
  - R10 (75e625c3): parent loses 0.370, child gets 0.406
  - R11 (324fde07): parent loses 0.285, child gets 0.297
  - R3 (f1dac9a9): parent loses 0.050, child gets 0.088

  So the hi-tier model is: parent directly transfers food to the child (parent loses ~0.22, child
  gets ~0.24 — the small excess is from first-step harvest). For lo-tier, the parent doesn't
  transfer food at all — the child's 0.15 food comes from its initial harvest, and the parent
  actually gains food that step (normal harvesting continues).

  This cleanly explains why hi-tier child food varies per round (it depends on parent food levels)
   while lo-tier is constant (it's just harvest).

  The wealth transfer percentages are essentially constants (not hidden parameters), while the
  hi-tier child food varies with the round's food economy.
