#pragma once
#include "infra.h"

// ============================================================
// Monte Carlo cellular automaton simulator
// ============================================================

namespace simulator {

// Parametric transition model — all coefficients tunable by hill climbing.
// Rates are computed as: base * exp(ns_coeff * ns + sr2_coeff * sr2 + ...)
// This replaces hardcoded lookup tables with learnable functions.
struct TuneParams {
    // Empty -> Settlement: base * exp(ns_coeff * ns + ns2_coeff * ns^2 + sr2_coeff * sr2)
    // Replay data: rate ≈ 0.0002 + 0.0083*ns (linear, not exponential)
    double es_base     = 0.003;   // base rate (replay: ~0.002 at ns=0)
    double es_ns_coeff = 0.40;    // linear neighbor effect
    double es_ns2_coeff = 0.0;    // quadratic neighbor effect
    double es_sr2_coeff = 0.10;   // radius-2 density effect

    // Empty -> Ruin ratio (fraction of settle rate)
    double er_ratio    = 0.15;

    // Settlement -> Ruin: base * exp(-support_coeff * ally_support) + raid * enemy_ns
    // Replay data: ruin rate ≈ 7.0% nearly constant across ns (0-5)
    double sr_base     = 0.07;    // replay: ~7% constant
    double sr_support  = 0.02;    // replay: minimal neighbor effect
    double sr_nf_weight = 0.5;    // forest support effect
    double sr_sr2_coeff = 0.001;  // radius-2 raiding (weak)
    double sr_raid     = 0.005;   // raiding (weak per replay data)
    double sr_ruin_coeff = 0.01;  // nearby ruins effect (weak)

    // Settlement -> Port (coastal only)
    // Replay: ~0.3% average
    double sp_base     = 0.03;    // replay: lower than previous
    double sp_ns_coeff = -0.02;

    // Forest -> Settlement: base * exp(ns_coeff * ns + ns2_coeff * ns^2)
    // Replay: rate ≈ 0.001 + 0.010*ns (linear)
    double fs_base     = 0.004;
    double fs_ns_coeff = 0.50;
    double fs_ns2_coeff = 0.0;

    // Forest -> Ruin ratio
    double fr_ratio    = 0.25;

    // Port -> Ruin
    // Replay: ~5% constant
    double pr_base     = 0.05;
    double pr_ns_coeff = -0.01;

    // Ruin transitions (replay data: very consistent across rounds)
    double ruin_settle = 0.48;    // replay: ~48%
    double ruin_empty  = 0.35;    // replay: ~35%
    double ruin_forest = 0.17;    // replay: ~17%
    double ruin_port   = 0.014;   // replay: ~1.4%
    double ruin_ns_coeff = 0.05;

    // Neighbor gating: p_s *= (1 - exp(-es_ns_gate * ns))
    // At ns=0: factor=0 (no spawning). At ns=1,gate=3: factor=0.95. Ramps quickly.
    double es_ns_gate = 0.0;      // 0 = allow spontaneous, >0 = require neighbors

    // Mean-field variance correction: boost = 1 + mf_var_boost * E[ns] * (1 - E[ns]/8)
    // Accounts for Jensen's inequality: E[exp(a*X)] > exp(a*E[X])
    double mf_var_boost = 0.0;    // 0 = no correction, >0 = boost expansion

    // Distance-based settlement spawning decay
    // Applied during mean_field: spawning rate *= exp(-dist_decay * d)
    // where d = BFS distance from initial settlements
    double dist_decay = 0.0;  // 0 = no decay, >0 = exponential decay with distance
};

extern TuneParams tune;

// Regime-specific defaults derived from replay transition rate analysis
// Growth rounds: high birth rate, low death rate (~7% constant)
// Collapse rounds: low birth rate, high death rate (~10-30%, ns-dependent)
inline TuneParams growth_defaults() {
    TuneParams p;
    p.es_base     = 0.004;   // growth: spontaneous births ~0.2%
    p.es_ns_coeff = 0.50;    // growth: strong neighbor boost
    p.sr_base     = 0.065;   // growth: low death ~6.5%
    p.sr_support  = 0.01;    // growth: minimal ns effect on death
    p.sr_raid     = 0.002;
    p.sr_ruin_coeff = 0.005;
    p.fs_base     = 0.005;
    p.fs_ns_coeff = 0.55;
    p.ruin_settle = 0.50;    // growth: ruins recover to settle more
    p.ruin_empty  = 0.32;
    p.ruin_forest = 0.17;
    return p;
}

inline TuneParams collapse_defaults() {
    TuneParams p;
    p.es_base     = 0.0005;  // collapse: very low spontaneous births
    p.es_ns_coeff = 0.30;    // collapse: weaker neighbor boost
    p.sr_base     = 0.12;    // collapse: high base death ~12%
    p.sr_support  = -0.10;   // collapse: more neighbors = MORE death (u-shaped)
    p.sr_raid     = 0.02;    // collapse: significant raiding
    p.sr_ruin_coeff = 0.02;
    p.fs_base     = 0.001;
    p.fs_ns_coeff = 0.25;
    p.ruin_settle = 0.30;    // collapse: ruins less likely to recover
    p.ruin_empty  = 0.45;
    p.ruin_forest = 0.20;
    return p;
}

struct CellContext {
    int terrain_class;
    double n_settle_neighbors;
    double n_forest_neighbors;
    double n_ruin_neighbors;
    double settle_r2;
    bool has_ocean_neighbor;
};

std::array<double, NUM_CLASSES> get_transition_probs(const CellContext& ctx);

std::vector<std::vector<int>> simulate_once(
    const std::vector<std::vector<int>>& initial_grid,
    std::mt19937& rng);

ProbTensor monte_carlo(
    const std::vector<std::vector<int>>& initial_grid,
    int num_simulations,
    std::mt19937& rng);

ProbTensor mean_field(
    const std::vector<std::vector<int>>& initial_grid,
    int num_steps = 50);

// ============================================================
// Agent-based simulation with research-calibrated mechanics
// ============================================================

struct AgentSimParams {
    // Spawn: logistic CDF P(spawn|pop) = 1/(1+exp(-(pop-mu)/s))
    double spawn_mu     = 2.184;   // population for 50% spawn chance
    double spawn_s      = 0.432;   // steepness

    // Spawn distance: geometric P(d) = exp(-lambda*(d-1))*(1-exp(-lambda))
    double spawn_lambda = 1.056;

    // Port formation: if food >= thresh and 2+ ocean neighbors
    double port_thresh  = 0.454;
    double port_rate    = 0.104;

    // Food production: dfood = alpha_p*plains + alpha_f*forest - beta*pop
    double food_alpha_p = 0.016;   // food from adjacent plains
    double food_alpha_f = 0.022;   // food from adjacent forest
    double food_beta    = 0.024;   // food consumed per pop

    // Population growth: pop += pop_growth * food
    double pop_growth   = 0.08;

    // Winter: food -= pop * winter_beta
    double winter_beta  = 0.024;   // same as food_beta by default

    // Child settlement stats (low tier)
    double child_pop    = 0.400;
    double child_def    = 0.150;
    double child_wealth_frac = 0.10;

    // Number of simulation steps
    int num_steps       = 50;
};

extern AgentSimParams agent_params;

ProbTensor agent_monte_carlo(
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<Settlement>& initial_settlements,
    const AgentSimParams& params,
    int num_simulations,
    std::mt19937& rng);

ProbTensor agent_mean_field(
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<Settlement>& initial_settlements,
    const AgentSimParams& params);

}  // namespace simulator
