# Agent-Based Simulator for Astar Island

## Status: Initial implementation complete, baseline testing in progress

### Current Results (2026-03-21)

**Default params (no hill-climbing), 50 Monte Carlo sims:**

| Round | Agent Sim | Submitted (Markov) |
|-------|-----------|-------------------|
| 71451d74 | 35.6 | 22.7 |
| 76909e29 | 30.7 | 81.4 |
| f1dac9a9 | 2.3 | 34.9 |
| 8e839974 | 39.9 | 87.8 |
| fd3c92ff | 27.4 | 82.5 |
| ae78003a | 18.8 | 72.6 |
| 36e581f1 | 13.5 | 60.2 |
| c5cdf100 | 24.7 | 86.9 |
| 2a341ace | 40.9 | 87.8 |
| 795bfb1f | 9.6 | 17.7 |
| **Avg** | **25.8** | **63.4** |

Agent sim with default params scores ~26 avg vs Markov's ~63.
However: Markov scores include hill-climbing + query data, agent sim is raw defaults.
Hill-climbing in progress — should close the gap significantly.

**Speed:** 74-170ms/sim (Python). 50 sims takes 2-11s per seed.

### Key Insights from Replay Analysis

- 19,607 settlement observations across 12 rounds
- Settlements NEVER die (alive=false never observed) — they change ownership
- 45.5% of transitions involve owner change (very frequent raiding)
- Population: mean=1.1, std=0.76, right-skewed
- Food: mean=0.69, left-skewed (clusters high)
- Defense: bimodal — cluster at 0.1-0.3 and spike at 1.0
- Wealth: near zero (mean=0.01)
- Round-to-round parameters vary WILDLY:
  - Some rounds: mass die-off (37 initial → 3 expected)
  - Some rounds: explosive growth (0 initial → 189 expected)
  - Most rounds: 2-7x growth

### Files

```
astar-erik/agent_sim/
    __init__.py          # Package init
    params.py            # 46 tunable float params + AgentParams dataclass
    settlement.py        # Settlement entity with sample_initial()
    world.py             # World: grid + settlements + spatial queries
    phases.py            # 5-phase step: Growth, Conflict, Trade, Winter, Environment
    simulator.py         # simulate_once() + monte_carlo() + save_prediction()
    calibrate.py         # compute_score(), hill_climb(), cross_validate()
    test_vs_replays.py   # CLI: test all rounds or hill-climb single round
```

### How to Test

```bash
cd astar-erik

# Run all rounds with default params (quick sanity check)
python3 agent_sim/test_vs_replays.py

# Hill-climb on first available round
python3 agent_sim/test_vs_replays.py --hill-climb
```

### Next Steps

1. **Hill-climbing**: Run hill_climb on each round individually to see max achievable score
2. **Speed**: Consider Cython/numba for inner loops if 500+ sims needed
3. **Integration with online.py**: Replace C++ simulator call with agent_sim.monte_carlo
4. **Per-round param learning**: Use query observations to tune params during competition
5. **Better initial stats**: Use replay data to learn owner_id clustering patterns

### Key Files to Check

- `astar-erik/agent_sim/phases.py` — Core simulation logic, most impactful to tune
- `astar-erik/agent_sim/params.py` — All 46 parameters with defaults
- `astar-erik/agent_sim/calibrate.py` — Hill-climbing + scoring
- `astar-erik/online.py` — Current submission pipeline (needs integration)
- `astar-island/analysis/` — Ground truth files for validation
- `astar-island/initial_states/` — Input maps per round
- `astar-island/simulations/` — Replay data with settlement stats

### Architecture

The simulator models settlements as entities with (pop, food, defense, wealth, owner_id).
Each timestep runs 5 phases:
1. **Growth**: pop grows proportional to food, food mean-reverts, defense tracks pop
2. **Conflict**: nearby different-faction settlements raid each other
3. **Trade**: ports within range exchange food/wealth
4. **Winter**: food loss, starvation can collapse low-pop settlements to ruins
5. **Environment**: high-pop settlements expand, ruins resolve, ports convert

Monte Carlo: run N independent simulations (each with random initial stats),
count final cell classes → probability tensor [40][40][6].
