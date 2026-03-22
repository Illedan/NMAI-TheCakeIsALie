"""Quick test of the evolve loop."""
from true_simulate import *
import json

with open("replays/round_1_replay_seed_0_71451d74-be9f-471f-aacd-a41f3b68a9cd.json") as f:
    data = json.load(f)

state = GameState.from_replay_frame(data["frames"][0])
print("Initial:", state)

rng = RNG(42)
params = RoundParams(rng)
print("Params:", params)

rng2 = RNG(123)
for step in range(10):
    evolve(state, params, rng2)
    alive = sum(1 for s in state.settlements if s.alive)
    total_pop = sum(s.population for s in state.settlements if s.alive)
    n_sett = len(state.settlements)
    print(f"Step {step+1:2d}: {alive:3d} alive ({n_sett} total), pop={total_pop:.1f}")

print()
for s in state.alive_settlements()[:5]:
    print(f"  {s}")
