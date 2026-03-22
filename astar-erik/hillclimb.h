#pragma once
#include "simulator.h"

namespace hillclimb {

// Hill-climb simulator multipliers against observed query data.
// Returns the best TuneParams found.
//
// observations: [query_idx] -> viewport grid (class indices, not terrain codes)
// obs_vx/vy/vw/vh: viewport position and size (same for all queries)
// initial_grid: full map with terrain codes
// iterations: number of HC iterations
// mc_sims: MC simulations per evaluation
// pad: padding around viewport for simulation context
struct HCResult {
    simulator::TuneParams best;
    std::vector<simulator::TuneParams> top_k;  // top-K params for ensemble
    std::vector<double> top_k_scores;
};

HCResult optimize(
    const std::vector<std::vector<std::vector<int>>>& observations,
    int obs_vx, int obs_vy, int obs_vw, int obs_vh,
    const std::vector<std::vector<int>>& initial_grid,
    int iterations,
    int pad,
    std::mt19937& rng,
    const simulator::TuneParams* start_params = nullptr,
    int mc_sims = 0,  // 0 = use mean_field, >0 = use MC(mc_sims)
    double dist_decay = 0.0);  // fixed dist_decay (not HC-tuned)

// Hill-climb agent simulation params against observed query data.
struct AgentHCResult {
    simulator::AgentSimParams params;
    double score;
};
AgentHCResult optimize_agent(
    const std::vector<std::vector<std::vector<int>>>& observations,
    int obs_vx, int obs_vy, int obs_vw, int obs_vh,
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<Settlement>& initial_settlements,
    int iterations,
    int pad,
    std::mt19937& rng);

// Evolutionary EDA optimizer: population-based with truncation selection
// + diagonal Gaussian resampling. Uses replays for realistic evaluation.
HCResult optimize_eda(
    const std::vector<std::vector<std::vector<int>>>& observations,
    int obs_vx, int obs_vy, int obs_vw, int obs_vh,
    const std::vector<std::vector<int>>& initial_grid,
    int population_size,   // e.g. 64
    int generations,       // e.g. 30
    double kill_ratio,     // e.g. 0.5 = kill bottom 50%
    std::mt19937& rng,
    int pad = 3,
    double dist_decay = 0.0,
    const simulator::TuneParams* seed_params = nullptr);

}  // namespace hillclimb
