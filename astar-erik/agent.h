#pragma once
#include "infra.h"
#include <set>

// ============================================================
// Agent-based simulator: faithful to competition simulation
// Settlements are entities with population, food, defense, wealth
// Five phases per year: Growth, Conflict, Trade, Winter, Environment
// ============================================================

namespace agent {

struct AgentParams {
    // Growth
    double pop_growth_rate = 0.08;
    double pop_food_factor = 1.0;
    double food_mean_revert_target = 0.7;
    double food_mean_revert_rate = 0.3;
    double food_pop_drain = 0.04;
    double defense_growth_rate = 0.05;
    double defense_pop_scale = 0.4;
    double wealth_growth_rate = 0.002;
    double wealth_pop_factor = 0.005;

    // Conflict
    double raid_range = 3.0;
    double raid_prob_base = 0.15;
    double raid_defense_weight = 2.0;
    double raid_desperation = 0.5;
    double raid_pop_damage = 0.3;
    double raid_loot_frac = 0.2;
    double raid_conquest_prob = 0.3;

    // Trade
    double trade_range = 4.0;
    double trade_food_gain = 0.05;
    double trade_wealth_gain = 0.01;

    // Winter
    double winter_food_loss = 0.05;
    double collapse_food_threshold = 0.05;
    double collapse_prob_starve = 0.1;
    double collapse_pop_loss = 0.5;
    double collapse_defense_loss = 0.3;

    // Expansion
    double expand_pop_threshold = 1.5;
    double expand_prob_base = 0.03;
    double expand_pop_factor = 0.02;
    double expand_radius = 3.0;
    double new_settlement_pop = 0.45;
    double new_settlement_food = 0.5;
    double new_settlement_defense = 0.1;

    // Environment
    double ruin_rebuild_prob = 0.02;
    double ruin_to_empty_prob = 0.03;
    double ruin_to_forest_prob = 0.01;
    double port_conversion_prob = 0.01;
    double spontaneous_settle_prob = 0.005;
    double spontaneous_settle_range = 3.0;
    double forest_settle_prob = 0.003;

    // Initial stat distributions
    double init_pop_mean = 1.1;
    double init_pop_std = 0.76;
    double init_food_mean = 0.69;
    double init_food_std = 0.27;
    double init_defense_mean = 0.46;
    double init_defense_std = 0.31;
    double init_wealth_mean = 0.01;
    double init_wealth_std = 0.03;

    // Simulation
    int num_steps = 50;

    // Get all tunable parameter pointers for hill climbing
    static constexpr int NUM_FLOAT_PARAMS = 46;

    struct ParamDef {
        double AgentParams::*ptr;
        double lo, hi;
    };
    static const ParamDef PARAM_DEFS[];
};

// Run Monte Carlo simulations and return probability tensor
ProbTensor monte_carlo(
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<Settlement>& initial_settlements,
    const AgentParams& params,
    int n_sims,
    std::mt19937& rng);

// Hill-climb agent params against observations
AgentParams hill_climb(
    const std::vector<std::vector<std::vector<int>>>& observations,
    int obs_vx, int obs_vy, int obs_vw, int obs_vh,
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<Settlement>& initial_settlements,
    const AgentParams& start_params,
    int iterations,
    int n_sims_per_eval,
    std::mt19937& rng);

}  // namespace agent
