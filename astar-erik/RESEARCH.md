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
     mu: E=2.184 std=0.288 (population for 50% spawn chance)
     s: E=0.432 std=0.166 (steepness of transition)

     Spawn distance (exponential/geometric):
     P(dist=d) = exp(-lambda*(d-1)) * (1 - exp(-lambda)), d=1,2,...
     lambda: E=1.056 std=0.664
     ()=> P(d=1) = 65%, P(d=2) = 23%, P(d=3) = 8%) then normalized to the available squares.

     Port formation (step function, settlements with 2+ ocean):
     P(port|food) = rate_above if food >= thresh, else ~0
     thresh: E=0.454 std=0.182
     rate_above: E=0.104 std=0.010

     Food production (linear model):
     dfood = alpha_p _ eff_plains + alpha_f _ eff_forest - beta \* pop
     alpha_plains: E=0.016 std=0.011
     alpha_forest: E=0.022 std=0.015
     beta: E=0.024 std=0.040

The children that spawn fall into distinct tiers, and have the same owner_id as their parent. The known _tiers_ are:

┌──────┬───────┬───────┬──────────┬──────────────┬─────────────┐
│ Tier │ Pop   │ Def   │ Wealth % │ Single child │ Multi-child │
├──────┼───────┼───────┼──────────┼──────────────┼─────────────┤
│ Low  │ 0.400 │ 0.150 │ ~10%     │ 73%          │ 27%         │
├──────┼───────┼───────┼──────────┼──────────────┼─────────────┤
│ Mid  │ 0.425 │ 0.160 │ ~20%     │ 94%          │ 6%          │
├──────┼───────┼───────┼──────────┼──────────────┼─────────────┤
│ High │ 0.500 │ 0.200 │ ~20%     │ 94%          │ 6%          │
└──────┴───────┴───────┴──────────┴──────────────┴─────────────┘

- **Wealth %** = percent of parent's wealth inherited by each child
- **Single child** = probability that a spawning parent produces exactly 1 child of this tier
- **Multi-child** = probability that a spawning parent produces 2+ children of this tier
- The mid tier was introduced after the first two; more tiers may arise
- Wealth(T0) >= Wealth(T50): wealth only decreases over time (children drain parent wealth, no wealth generation except small port trade income)

The next part of the Growth phase is that the settlements harvest the area around them. Plains and Forest give food. Ports don't gain food from Water, noone gets food from Mountain. Ports may seem to generate food at first glance, but very little, and likely confounded by generally high food gain in high expansion games. Tiles produce food with some probability, like in Catan, but the food produced is split between all neighbors to the tile.

Having a port in the treade phase gives a small wealth gain of 0.005+-0.005 each step.

Se på distribusjonen for initial food når en settlement oppstår. Se på initial distribution av parametre for settlements.

Population decreases food in winter: food -= population\*beta. If food drops to 0, the settlement becomes ruin.
