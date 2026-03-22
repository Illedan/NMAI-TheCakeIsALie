"""Five-phase step logic for the agent-based simulator.

Phases per timestep (in order):
1. Growth   - population/food/defense/wealth update
2. Conflict - raiding between nearby settlements
3. Trade    - port-to-port exchange
4. Winter   - food loss, starvation collapse
5. Environment - expansion, ruin resolution, port conversion
"""

import numpy as np
from .settlement import Settlement
from .world import (World, TERRAIN_RUIN, TERRAIN_SETTLEMENT, TERRAIN_PORT,
                    TERRAIN_EMPTY, TERRAIN_PLAINS, TERRAIN_FOREST)
from .params import AgentParams


def phase_growth(world: World, params: AgentParams, rng: np.random.Generator):
    """Phase 1: Population growth, food dynamics, defense/wealth accumulation."""
    for s in world.alive_settlements():
        # Population growth: scales with food availability + noise
        food_factor = s.food * params.pop_food_factor
        growth = params.pop_growth_rate * s.population * food_factor
        growth += rng.normal(0, 0.05 * s.population)  # stochastic noise
        s.population += growth
        s.population = max(0.1, s.population)

        # Food: mean-revert + drain from population + noise
        food_target = params.food_mean_revert_target
        s.food += params.food_mean_revert_rate * (food_target - s.food)
        s.food -= params.food_pop_drain * s.population
        s.food += rng.normal(0, 0.05)
        s.food = np.clip(s.food, 0.0, 1.0)

        # Defense: grows toward pop-dependent cap + noise
        defense_cap = min(1.0, s.population * params.defense_pop_scale)
        s.defense += params.defense_growth_rate * (defense_cap - s.defense)
        s.defense += rng.normal(0, 0.02)
        s.defense = np.clip(s.defense, 0.0, 1.0)

        # Wealth: slow passive growth
        s.wealth += params.wealth_growth_rate + params.wealth_pop_factor * s.population
        s.wealth = max(0.0, s.wealth)


def phase_conflict(world: World, params: AgentParams, rng: np.random.Generator):
    """Phase 2: Raiding between nearby settlements of different factions."""
    alive = world.alive_settlements()
    # Shuffle to avoid order bias
    rng.shuffle(alive)

    for attacker in alive:
        if not attacker.alive:
            continue

        neighbors = world.neighbors_in_range(attacker, params.raid_range)
        # Filter to different-faction targets
        targets = [t for t in neighbors if t.owner_id != attacker.owner_id and t.alive]
        if not targets:
            continue

        # Desperation: low food increases raid probability
        desperation = max(0, 1.0 - attacker.food) * params.raid_desperation

        for target in targets:
            # Raid probability: base + desperation, penalized by defender defense
            defense_penalty = target.defense * params.raid_defense_weight
            raid_prob = params.raid_prob_base + desperation - defense_penalty
            raid_prob = np.clip(raid_prob, 0.0, 0.8)

            if rng.random() < raid_prob:
                # Raid succeeds
                # Damage to defender
                pop_loss = target.population * params.raid_pop_damage
                target.population -= pop_loss
                target.population = max(0.1, target.population)

                # Loot
                food_loot = target.food * params.raid_loot_frac
                wealth_loot = target.wealth * params.raid_loot_frac
                target.food -= food_loot
                target.wealth -= wealth_loot
                attacker.food += food_loot * 0.5  # Some loot lost in transit
                attacker.wealth += wealth_loot * 0.5

                # Possible conquest (ownership change)
                if rng.random() < params.raid_conquest_prob:
                    target.owner_id = attacker.owner_id
                    # Big pop drop on conquest (observed: mean -1.57 on big drops)
                    target.population *= 0.5
                    target.population = max(0.1, target.population)

                break  # One raid per attacker per step


def phase_trade(world: World, params: AgentParams, rng: np.random.Generator):
    """Phase 3: Port-to-port trade exchanges."""
    ports = [s for s in world.alive_settlements() if s.has_port]

    for port in ports:
        trade_partners = [p for p in ports
                         if p is not port and port.distance_to(p) <= params.trade_range]
        for partner in trade_partners:
            port.food = min(1.0, port.food + params.trade_food_gain)
            port.wealth += params.trade_wealth_gain


def phase_winter(world: World, params: AgentParams, rng: np.random.Generator):
    """Phase 4: Food loss and starvation collapse."""
    for s in world.alive_settlements():
        # Winter food loss
        s.food -= params.winter_food_loss
        s.food = max(0.0, s.food)

        # Starvation collapse check
        if s.food < params.collapse_food_threshold:
            if rng.random() < params.collapse_prob_starve:
                s.population *= (1.0 - params.collapse_pop_loss)
                s.defense *= (1.0 - params.collapse_defense_loss)
                s.population = max(0.1, s.population)
                s.defense = max(0.0, s.defense)

                # If population drops very low, settlement becomes ruin
                if s.population < 0.15:
                    world.remove_settlement(s)


def phase_environment(world: World, params: AgentParams, rng: np.random.Generator):
    """Phase 5: Expansion from high-pop settlements, ruin resolution, port conversion."""
    # Expansion: high-pop settlements can spawn new ones
    alive = list(world.alive_settlements())  # snapshot
    for s in alive:
        if not s.alive:
            continue
        if s.population < params.expand_pop_threshold:
            continue

        excess = s.population - params.expand_pop_threshold
        expand_prob = params.expand_prob_base + params.expand_pop_factor * excess
        if rng.random() < expand_prob:
            candidates = world.valid_expansion_cells(s, params.expand_radius)
            if candidates:
                nx, ny = candidates[rng.integers(len(candidates))]
                is_coastal = world.ocean_adj[ny, nx]
                new_s = Settlement(
                    x=nx, y=ny,
                    population=params.new_settlement_pop,
                    food=params.new_settlement_food,
                    defense=params.new_settlement_defense,
                    wealth=0.0,
                    owner_id=s.owner_id,
                    has_port=is_coastal and rng.random() < params.port_conversion_prob * 5,
                )
                world.add_settlement(new_s)
                # Parent loses some population
                s.population -= params.new_settlement_pop * 0.5

    # Ruin resolution
    # Build a settlement presence grid for fast neighbor lookup
    settle_presence = np.zeros((world.height, world.width), dtype=bool)
    alive_list = world.alive_settlements()
    for s in alive_list:
        settle_presence[s.y, s.x] = True

    for y in range(world.height):
        for x in range(world.width):
            if world.grid[y, x] != TERRAIN_RUIN:
                continue

            # Count nearby settlements using presence grid
            n_nearby = 0
            for dy2 in range(-2, 3):
                for dx2 in range(-2, 3):
                    ny2, nx2 = y + dy2, x + dx2
                    if 0 <= ny2 < world.height and 0 <= nx2 < world.width:
                        if settle_presence[ny2, nx2]:
                            n_nearby += 1

            r = rng.random()
            rebuild_bonus = 0.01 * n_nearby
            if r < params.ruin_rebuild_prob + rebuild_bonus:
                nearest_owner = 0
                min_dist = 999
                for s in alive_list:
                    d = max(abs(s.x - x), abs(s.y - y))
                    if d < min_dist:
                        min_dist = d
                        nearest_owner = s.owner_id

                is_coastal = world.ocean_adj[y, x]
                new_s = Settlement(
                    x=x, y=y,
                    population=params.new_settlement_pop,
                    food=params.new_settlement_food,
                    defense=params.new_settlement_defense,
                    wealth=0.0,
                    owner_id=nearest_owner,
                    has_port=is_coastal and rng.random() < 0.1,
                )
                world.add_settlement(new_s)
            elif r < params.ruin_rebuild_prob + rebuild_bonus + params.ruin_to_empty_prob:
                world.grid[y, x] = TERRAIN_PLAINS
            elif r < (params.ruin_rebuild_prob + rebuild_bonus +
                      params.ruin_to_empty_prob + params.ruin_to_forest_prob):
                world.grid[y, x] = TERRAIN_FOREST

    # Spontaneous settlement generation: each settlement has a small chance
    # to spawn a neighbor (separate from expansion, which requires high pop)
    alive_snap = list(world.alive_settlements())
    for s in alive_snap:
        if not s.alive:
            continue
        if rng.random() >= params.spontaneous_settle_prob:
            continue
        # Pick a random cell in range
        r = int(params.spontaneous_settle_range)
        dx = rng.integers(-r, r + 1)
        dy = rng.integers(-r, r + 1)
        if dx == 0 and dy == 0:
            continue
        nx, ny = s.x + dx, s.y + dy
        if not (0 <= ny < world.height and 0 <= nx < world.width):
            continue
        t = world.grid[ny, nx]
        if t not in (TERRAIN_EMPTY, TERRAIN_PLAINS, TERRAIN_FOREST):
            continue
        if world.settlement_at(nx, ny) is not None:
            continue
        is_coastal = world.ocean_adj[ny, nx]
        new_s = Settlement(
            x=nx, y=ny,
            population=params.new_settlement_pop,
            food=params.new_settlement_food,
            defense=params.new_settlement_defense,
            wealth=0.0,
            owner_id=s.owner_id,
            has_port=is_coastal and rng.random() < 0.1,
        )
        world.add_settlement(new_s)

    # Port conversion: coastal settlements may become ports
    for s in world.alive_settlements():
        if s.has_port:
            continue
        if world.ocean_adj[s.y, s.x]:
            if rng.random() < params.port_conversion_prob:
                s.has_port = True
                world.grid[s.y, s.x] = TERRAIN_PORT


def step(world: World, params: AgentParams, rng: np.random.Generator):
    """Execute one full timestep (all 5 phases)."""
    phase_growth(world, params, rng)
    phase_conflict(world, params, rng)
    phase_trade(world, params, rng)
    phase_winter(world, params, rng)
    phase_environment(world, params, rng)
