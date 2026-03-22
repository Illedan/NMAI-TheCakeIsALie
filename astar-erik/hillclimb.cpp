#include "hillclimb.h"

namespace hillclimb {

static std::vector<std::vector<std::array<double, NUM_CLASSES>>>
build_empirical(const std::vector<std::vector<std::vector<int>>>& observations,
                int vx, int vy, int vw, int vh,
                int H, int W) {
    std::vector<std::vector<std::array<double, NUM_CLASSES>>> emp(
        vh, std::vector<std::array<double, NUM_CLASSES>>(vw, {0,0,0,0,0,0}));

    int n = (int)observations.size();
    if (n == 0) return emp;

    double inv_n = 1.0 / n;
    for (auto& obs : observations) {
        for (int y = 0; y < (int)obs.size() && y < vh; y++)
            for (int x = 0; x < (int)obs[y].size() && x < vw; x++) {
                int gy = vy + y, gx = vx + x;
                if (gy >= H || gx >= W) continue;
                int c = obs[y][x];
                if (c >= 0 && c < NUM_CLASSES)
                    emp[y][x][c] += inv_n;
            }
    }
    return emp;
}

static double score_vs_empirical(
    const ProbTensor& mc,
    const std::vector<std::vector<std::array<double, NUM_CLASSES>>>& emp,
    const std::vector<std::vector<int>>& sub_grid,
    int tile_lx, int tile_ly, int tile_w, int tile_h,
    double /*obs_avg_settle_count*/,
    double reg_penalty = 0.0) {

    double total_kl = 0, total_w = 0;

    for (int ty = 0; ty < tile_h; ty++) {
        for (int tx = 0; tx < tile_w; tx++) {
            int ly = tile_ly + ty, lx = tile_lx + tx;
            if (ly < 0 || ly >= (int)mc.size() || lx < 0 || lx >= (int)mc[0].size())
                continue;

            int t = sub_grid[ly][lx];
            if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;

            auto& p = emp[ty][tx];
            auto& q = mc[ly][lx];

            double h = 0;
            for (int c = 0; c < NUM_CLASSES; c++) {
                double pi = std::max(p[c], 0.001);
                h -= pi * std::log(pi);
            }
            double w = std::max(h, 0.01);

            double kl = 0;
            for (int c = 0; c < NUM_CLASSES; c++) {
                double pi = std::max(p[c], 0.01);
                double qi = std::max(q[c], 0.01);
                kl += pi * std::log(pi / qi);
            }

            total_kl += w * kl;
            total_w += w;
        }
    }

    if (total_w == 0) return 0;

    double kl_score = 100.0 * std::exp(-3.0 * total_kl / total_w);

    return kl_score - reg_penalty;
}

static ProbTensor run_with_params(
    const std::vector<std::vector<int>>& sub_grid,
    const simulator::TuneParams& params,
    int mc_sims = 0,
    std::mt19937* rng = nullptr) {

    auto old = simulator::tune;
    simulator::tune = params;
    ProbTensor result;
    if (mc_sims > 0 && rng) {
        result = simulator::monte_carlo(sub_grid, mc_sims, *rng);
    } else {
        result = simulator::mean_field(sub_grid);
    }
    simulator::tune = old;
    return result;
}

// All tunable parameter pointers + their step scale
struct ParamDef {
    double simulator::TuneParams::*ptr;
    double lo, hi;     // valid range
    double step_scale; // relative step size (bigger = more volatile param)
};

static const ParamDef PARAM_DEFS[] = {
    // Core expansion params (most impactful)
    {&simulator::TuneParams::es_base,      0.0005, 0.15,  1.0},
    {&simulator::TuneParams::es_ns_coeff,  0.01,   1.5,   1.0},
    {&simulator::TuneParams::sr_base,      0.003,  0.25,  1.0},
    {&simulator::TuneParams::sr_support,   0.01,   0.50,  1.0},
    {&simulator::TuneParams::sp_base,      0.02,   0.25,  0.8},
    {&simulator::TuneParams::fs_base,      0.0005, 0.08,  1.0},
    {&simulator::TuneParams::fs_ns_coeff,  0.01,   1.5,   0.8},
    // Ruin dynamics
    {&simulator::TuneParams::ruin_settle,  0.1,    0.8,   1.0},
    {&simulator::TuneParams::ruin_empty,   0.1,    0.7,   1.0},
    {&simulator::TuneParams::ruin_forest,  0.02,   0.5,   0.7},
    // MF correction
    {&simulator::TuneParams::mf_var_boost, 0.0,    2.0,   0.8},
};
static constexpr int N_PARAMS = sizeof(PARAM_DEFS) / sizeof(PARAM_DEFS[0]);

HCResult optimize(
    const std::vector<std::vector<std::vector<int>>>& observations,
    int obs_vx, int obs_vy, int obs_vw, int obs_vh,
    const std::vector<std::vector<int>>& initial_grid,
    int iterations,
    int pad,
    std::mt19937& rng,
    const simulator::TuneParams* start_params,
    int mc_sims,
    double dist_decay) {

    int H = (int)initial_grid.size();
    int W = H > 0 ? (int)initial_grid[0].size() : 0;

    int px = std::max(0, obs_vx - pad);
    int py = std::max(0, obs_vy - pad);
    int pw = std::min(W, obs_vx + obs_vw + pad) - px;
    int ph = std::min(H, obs_vy + obs_vh + pad) - py;

    std::vector<std::vector<int>> sub_grid(ph, std::vector<int>(pw));
    for (int y = 0; y < ph; y++)
        for (int x = 0; x < pw; x++)
            sub_grid[y][x] = initial_grid[py + y][px + x];

    int tile_lx = obs_vx - px;
    int tile_ly = obs_vy - py;

    auto emp = build_empirical(observations, obs_vx, obs_vy, obs_vw, obs_vh, H, W);

    // Compute average settlement+port count per observation
    double obs_avg_settle = 0;
    for (auto& obs : observations) {
        int count = 0;
        for (int y = 0; y < (int)obs.size() && y < obs_vh; y++)
            for (int x = 0; x < (int)obs[y].size() && x < obs_vw; x++) {
                int c = obs[y][x];
                if (c == CLASS_SETTLEMENT || c == CLASS_PORT) count++;
            }
        obs_avg_settle += count;
    }
    if (!observations.empty()) obs_avg_settle /= observations.size();

    // Run restarts, track top-K for ensemble
    int n_restarts = 3;
    constexpr int TOP_K = 3;
    simulator::TuneParams global_best;
    double global_best_score = -1;
    std::vector<std::pair<double, simulator::TuneParams>> all_results;

    std::uniform_int_distribution<int> param_dist(0, N_PARAMS - 1);
    std::uniform_real_distribution<double> delta_dist(-1.0, 1.0);
    std::uniform_int_distribution<int> coin(0, 3);

    // Detect growth regime: compare settlement fraction in observations vs initial grid
    // If settlements grew (obs > initial), it's a growth regime
    double obs_settle_frac = 0, init_settle_frac = 0;
    {
        int obs_settle = 0, obs_land = 0;
        int init_settle = 0, init_land = 0;
        for (int y = 0; y < obs_vh; y++)
            for (int x = 0; x < obs_vw; x++) {
                int gy = obs_vy + y, gx = obs_vx + x;
                if (gy >= H || gx >= W) continue;
                int t = initial_grid[gy][gx];
                if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
                init_land++;
                int ic = terrain_to_class(t);
                if (ic == CLASS_SETTLEMENT || ic == CLASS_PORT) init_settle++;
            }
        for (auto& obs : observations) {
            for (int y = 0; y < (int)obs.size() && y < obs_vh; y++)
                for (int x = 0; x < (int)obs[y].size() && x < obs_vw; x++) {
                    int gy = obs_vy + y, gx = obs_vx + x;
                    if (gy >= H || gx >= W) continue;
                    int t = initial_grid[gy][gx];
                    if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
                    obs_land++;
                    int c = obs[y][x];
                    if (c == CLASS_SETTLEMENT || c == CLASS_PORT) obs_settle++;
                }
        }
        if (init_land > 0) init_settle_frac = (double)init_settle / init_land;
        if (obs_land > 0) obs_settle_frac = (double)obs_settle / obs_land;
    }
    // Growth ratio: how much did settlements increase from initial to observed?
    double settle_growth_ratio = (init_settle_frac > 0.01)
        ? obs_settle_frac / init_settle_frac
        : (obs_settle_frac > 0.05 ? 5.0 : 1.0);

    // Preset: "settlement growth" — calibrated from empirical replay data
    // Empirical best-fit: es_base=0.003, es_ns_coeff=0.62, fs_base=0.003, fs_ns_coeff=0.64
    // Growth preset shifts toward higher expansion from empirical baseline
    simulator::TuneParams settle_growth;
    settle_growth.es_base = 0.008;
    settle_growth.es_ns_coeff = 0.70;
    settle_growth.es_ns2_coeff = 0.05;
    settle_growth.es_sr2_coeff = 0.18;
    settle_growth.sr_base = 0.040;
    settle_growth.sr_support = 0.20;
    settle_growth.sr_raid = 0.015;
    settle_growth.sr_ruin_coeff = 0.03;
    settle_growth.fs_base = 0.008;
    settle_growth.fs_ns_coeff = 0.70;
    settle_growth.fs_ns2_coeff = 0.05;
    settle_growth.sp_base = 0.06;
    settle_growth.ruin_settle = 0.55;
    settle_growth.ruin_empty = 0.28;
    settle_growth.ruin_ns_coeff = 0.08;
    settle_growth.mf_var_boost = 0.5;

    // Growth regime: settlements grew significantly from initial state
    // ratio > 1.5 means settlements expanded 50%+ from initial
    bool settlement_regime = (settle_growth_ratio > 1.5);
    int iters_actual = iterations / n_restarts;

    for (int restart = 0; restart < n_restarts; restart++) {
        simulator::TuneParams current;
        if (start_params && restart == 0) {
            current = *start_params;
        } else if (restart == 1 && settlement_regime) {
            current = settle_growth;
        }
        current.dist_decay = dist_decay;

        // Jittered restart
        if (restart == 2) {
            simulator::TuneParams def;
            simulator::TuneParams& base = settlement_regime ? settle_growth : def;
            for (int i = 0; i < N_PARAMS; i++) {
                double& val = current.*(PARAM_DEFS[i].ptr);
                double def_val = def.*(PARAM_DEFS[i].ptr);
                double base_val = base.*(PARAM_DEFS[i].ptr);
                val = 0.5 * (def_val + base_val);
            }
            std::uniform_real_distribution<double> jitter(0.7, 1.3);
            for (int i = 0; i < N_PARAMS; i++) {
                double& val = current.*(PARAM_DEFS[i].ptr);
                val *= jitter(rng);
                val = std::max(PARAM_DEFS[i].lo, std::min(PARAM_DEFS[i].hi, val));
            }
        }

        // Regularization: penalize deviation from prior
        // Use growth preset as regularization target in growth regime
        simulator::TuneParams defaults;
        simulator::TuneParams& reg_target = settlement_regime ? settle_growth : defaults;
        double reg_lambda = 0.3;  // regularization strength

        auto compute_reg = [&](const simulator::TuneParams& p) -> double {
            double penalty = 0;
            for (int i = 0; i < N_PARAMS; i++) {
                double val = p.*(PARAM_DEFS[i].ptr);
                double def_val = reg_target.*(PARAM_DEFS[i].ptr);
                double range = PARAM_DEFS[i].hi - PARAM_DEFS[i].lo;
                if (range > 0) {
                    double normed = (val - def_val) / range;
                    penalty += normed * normed;
                }
            }
            return reg_lambda * penalty;
        };

        ProbTensor mc = run_with_params(sub_grid, current, mc_sims, &rng);
        double best_score = score_vs_empirical(mc, emp, sub_grid, tile_lx, tile_ly, obs_vw, obs_vh, obs_avg_settle, compute_reg(current));
        simulator::TuneParams best = current;

        double step_size = 0.15;
        int no_improve = 0;

        for (int it = 0; it < iters_actual; it++) {
            simulator::TuneParams trial = best;

            // Perturb 1 or 2 params
            int n_perturb = (coin(rng) == 0) ? 2 : 1;
            for (int p = 0; p < n_perturb; p++) {
                int pi = param_dist(rng);
                auto& def = PARAM_DEFS[pi];
                double range = def.hi - def.lo;
                double delta = delta_dist(rng) * step_size * range * def.step_scale;
                double& val = trial.*(def.ptr);
                val = std::max(def.lo, std::min(def.hi, val + delta));
            }

            mc = run_with_params(sub_grid, trial, mc_sims, &rng);
            double score = score_vs_empirical(mc, emp, sub_grid, tile_lx, tile_ly, obs_vw, obs_vh, obs_avg_settle, compute_reg(trial));

            if (score > best_score) {
                best_score = score;
                best = trial;
                no_improve = 0;
            } else {
                no_improve++;
                if (no_improve >= 12) {
                    step_size = std::max(0.02, step_size * 0.80);
                    no_improve = 0;
                }
            }
        }

        all_results.push_back({best_score, best});
        if (best_score > global_best_score) {
            global_best_score = best_score;
            global_best = best;
        }
    }

    // Build top-K result
    std::sort(all_results.begin(), all_results.end(),
              [](auto& a, auto& b) { return a.first > b.first; });
    HCResult result;
    result.best = global_best;
    for (int i = 0; i < std::min(TOP_K, (int)all_results.size()); i++) {
        result.top_k.push_back(all_results[i].second);
        result.top_k_scores.push_back(all_results[i].first);
    }
    return result;
}

// ============================================================
// EDA: Estimation of Distribution Algorithm
// Population-based evolutionary optimization with:
//   1. Evaluate fitness of each individual
//   2. Truncation selection (kill bottom p%)
//   3. Fit diagonal Gaussian to survivors
//   4. Resample to fill population
// ============================================================

HCResult optimize_eda(
    const std::vector<std::vector<std::vector<int>>>& observations,
    int obs_vx, int obs_vy, int obs_vw, int obs_vh,
    const std::vector<std::vector<int>>& initial_grid,
    int population_size,
    int generations,
    double kill_ratio,
    std::mt19937& rng,
    int pad,
    double dist_decay,
    const simulator::TuneParams* seed_params) {

    int H = (int)initial_grid.size();
    int W = H > 0 ? (int)initial_grid[0].size() : 0;

    // Build padded sub-grid (same as optimize)
    int px = std::max(0, obs_vx - pad);
    int py = std::max(0, obs_vy - pad);
    int pw = std::min(W, obs_vx + obs_vw + pad) - px;
    int ph = std::min(H, obs_vy + obs_vh + pad) - py;

    std::vector<std::vector<int>> sub_grid(ph, std::vector<int>(pw));
    for (int y = 0; y < ph; y++)
        for (int x = 0; x < pw; x++)
            sub_grid[y][x] = initial_grid[py + y][px + x];

    int tile_lx = obs_vx - px;
    int tile_ly = obs_vy - py;

    auto emp = build_empirical(observations, obs_vx, obs_vy, obs_vw, obs_vh, H, W);

    // Compute observed settlement count for scoring
    double obs_avg_settle = 0;
    for (auto& obs : observations) {
        int count = 0;
        for (int y = 0; y < (int)obs.size() && y < obs_vh; y++)
            for (int x = 0; x < (int)obs[y].size() && x < obs_vw; x++) {
                int c = obs[y][x];
                if (c == CLASS_SETTLEMENT || c == CLASS_PORT) count++;
            }
        obs_avg_settle += count;
    }
    if (!observations.empty()) obs_avg_settle /= observations.size();

    // Encode/decode TuneParams as double array for the EDA
    auto encode = [](const simulator::TuneParams& p) -> std::vector<double> {
        std::vector<double> v(N_PARAMS);
        for (int i = 0; i < N_PARAMS; i++)
            v[i] = p.*(PARAM_DEFS[i].ptr);
        return v;
    };

    auto decode = [&](const std::vector<double>& v) -> simulator::TuneParams {
        simulator::TuneParams p;
        p.dist_decay = dist_decay;
        for (int i = 0; i < N_PARAMS; i++) {
            p.*(PARAM_DEFS[i].ptr) = std::max(PARAM_DEFS[i].lo,
                                     std::min(PARAM_DEFS[i].hi, v[i]));
        }
        return p;
    };

    auto evaluate = [&](const simulator::TuneParams& p) -> double {
        ProbTensor mc = run_with_params(sub_grid, p);
        return score_vs_empirical(mc, emp, sub_grid, tile_lx, tile_ly,
                                  obs_vw, obs_vh, obs_avg_settle);
    };

    // Initialize population: defaults + growth preset + random samples
    int n_survive = std::max(2, (int)(population_size * (1.0 - kill_ratio)));

    struct Individual {
        std::vector<double> genes;
        double fitness;
    };
    std::vector<Individual> pop(population_size);

    // Seed population: defaults + growth preset + Gaussian noise around both
    std::uniform_real_distribution<double> uni01(0.0, 1.0);
    std::normal_distribution<double> init_noise(0.0, 1.0);

    // Two seed presets (use seed_params as primary if provided)
    simulator::TuneParams preset_default;
    preset_default.dist_decay = dist_decay;
    if (seed_params) preset_default = *seed_params;

    simulator::TuneParams preset_growth;
    preset_growth.dist_decay = dist_decay;
    preset_growth.es_base = 0.008; preset_growth.es_ns_coeff = 0.70;
    preset_growth.es_ns2_coeff = 0.05; preset_growth.es_sr2_coeff = 0.18;
    preset_growth.sr_base = 0.040; preset_growth.sr_support = 0.20;
    preset_growth.sr_raid = 0.015; preset_growth.sr_ruin_coeff = 0.03;
    preset_growth.fs_base = 0.008; preset_growth.fs_ns_coeff = 0.70;
    preset_growth.fs_ns2_coeff = 0.05; preset_growth.sp_base = 0.06;
    preset_growth.ruin_settle = 0.55; preset_growth.ruin_empty = 0.28;
    preset_growth.ruin_ns_coeff = 0.08; preset_growth.mf_var_boost = 0.5;

    auto encoded_default = encode(preset_default);
    auto encoded_growth = encode(preset_growth);

    for (int i = 0; i < population_size; i++) {
        // Alternate between perturbing defaults and growth preset
        // First two are exact copies, rest get Gaussian noise
        const auto& base = (i % 2 == 0) ? encoded_default : encoded_growth;
        pop[i].genes.resize(N_PARAMS);

        double noise_scale = (i < 2) ? 0.0 : 0.15;  // exact copies for i=0,1
        for (int j = 0; j < N_PARAMS; j++) {
            double range = PARAM_DEFS[j].hi - PARAM_DEFS[j].lo;
            double val = base[j] + noise_scale * range * init_noise(rng);
            pop[i].genes[j] = std::max(PARAM_DEFS[j].lo, std::min(PARAM_DEFS[j].hi, val));
        }
        pop[i].fitness = evaluate(decode(pop[i].genes));
    }

    // Track global best
    simulator::TuneParams global_best;
    double global_best_fitness = -1;

    for (int gen = 0; gen < generations; gen++) {
        // Sort by fitness (descending)
        std::sort(pop.begin(), pop.end(),
                  [](const Individual& a, const Individual& b) {
                      return a.fitness > b.fitness;
                  });

        // Track global best
        if (pop[0].fitness > global_best_fitness) {
            global_best_fitness = pop[0].fitness;
            global_best = decode(pop[0].genes);
        }

        // Compute mean + variance of survivors (diagonal Gaussian)
        std::vector<double> mu(N_PARAMS, 0.0);
        std::vector<double> sigma(N_PARAMS, 0.0);

        for (int i = 0; i < n_survive; i++)
            for (int j = 0; j < N_PARAMS; j++)
                mu[j] += pop[i].genes[j];
        for (int j = 0; j < N_PARAMS; j++)
            mu[j] /= n_survive;

        for (int i = 0; i < n_survive; i++)
            for (int j = 0; j < N_PARAMS; j++) {
                double d = pop[i].genes[j] - mu[j];
                sigma[j] += d * d;
            }
        for (int j = 0; j < N_PARAMS; j++) {
            sigma[j] = std::sqrt(sigma[j] / std::max(1, n_survive - 1));
            // Floor: at least 1% of param range to prevent premature convergence
            double range = PARAM_DEFS[j].hi - PARAM_DEFS[j].lo;
            sigma[j] = std::max(sigma[j], 0.01 * range);
        }

        // Keep survivors, resample the rest from N(mu, sigma^2)
        std::normal_distribution<double> norm(0.0, 1.0);
        for (int i = n_survive; i < population_size; i++) {
            for (int j = 0; j < N_PARAMS; j++) {
                double val = mu[j] + sigma[j] * norm(rng);
                val = std::max(PARAM_DEFS[j].lo, std::min(PARAM_DEFS[j].hi, val));
                pop[i].genes[j] = val;
            }
            pop[i].fitness = evaluate(decode(pop[i].genes));
        }

        // Also re-evaluate a few survivors with slight perturbation (exploration)
        for (int i = 1; i < std::min(3, n_survive); i++) {
            Individual mutant;
            mutant.genes = pop[i].genes;
            for (int j = 0; j < N_PARAMS; j++) {
                if (uni01(rng) < 0.3) {
                    mutant.genes[j] += sigma[j] * 0.5 * norm(rng);
                    mutant.genes[j] = std::max(PARAM_DEFS[j].lo,
                                     std::min(PARAM_DEFS[j].hi, mutant.genes[j]));
                }
            }
            mutant.fitness = evaluate(decode(mutant.genes));
            if (mutant.fitness > pop[i].fitness)
                pop[i] = mutant;
        }
    }

    // Final sort
    std::sort(pop.begin(), pop.end(),
              [](const Individual& a, const Individual& b) {
                  return a.fitness > b.fitness;
              });
    if (pop[0].fitness > global_best_fitness) {
        global_best_fitness = pop[0].fitness;
        global_best = decode(pop[0].genes);
    }

    std::cerr << "EDA: best=" << global_best_fitness
              << " pop=" << population_size
              << " gen=" << generations << "\n";

    // Build HCResult
    HCResult result;
    result.best = global_best;
    constexpr int TOP_K = 3;
    for (int i = 0; i < std::min(TOP_K, population_size); i++) {
        result.top_k.push_back(decode(pop[i].genes));
        result.top_k_scores.push_back(pop[i].fitness);
    }
    return result;
}

// ============================================================
// Agent simulation HC
// ============================================================

struct AgentParamDef {
    double simulator::AgentSimParams::*ptr;
    double lo, hi;
    double step_scale;
};

static const AgentParamDef AGENT_PARAM_DEFS[] = {
    {&simulator::AgentSimParams::spawn_mu,     0.5,  5.0,   1.0},
    {&simulator::AgentSimParams::spawn_s,      0.05, 2.0,   1.0},
    {&simulator::AgentSimParams::spawn_lambda,  0.1, 3.0,   0.8},
    {&simulator::AgentSimParams::port_thresh,  0.1,  1.5,   0.6},
    {&simulator::AgentSimParams::port_rate,    0.01, 0.4,   0.6},
    {&simulator::AgentSimParams::food_alpha_p, 0.001, 0.1,  0.8},
    {&simulator::AgentSimParams::food_alpha_f, 0.001, 0.1,  0.8},
    {&simulator::AgentSimParams::food_beta,    0.001, 0.15, 0.8},
    {&simulator::AgentSimParams::pop_growth,   0.01, 0.3,   0.8},
    {&simulator::AgentSimParams::winter_beta,  0.001, 0.15, 0.8},
};
static constexpr int N_AGENT_PARAMS = sizeof(AGENT_PARAM_DEFS) / sizeof(AGENT_PARAM_DEFS[0]);

AgentHCResult optimize_agent(
    const std::vector<std::vector<std::vector<int>>>& observations,
    int obs_vx, int obs_vy, int obs_vw, int obs_vh,
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<Settlement>& initial_settlements,
    int iterations,
    int pad,
    std::mt19937& rng) {

    int H = (int)initial_grid.size();
    int W = H > 0 ? (int)initial_grid[0].size() : 0;

    // Build padded sub-grid
    int px = std::max(0, obs_vx - pad);
    int py = std::max(0, obs_vy - pad);
    int pw = std::min(W, obs_vx + obs_vw + pad) - px;
    int ph = std::min(H, obs_vy + obs_vh + pad) - py;

    std::vector<std::vector<int>> sub_grid(ph, std::vector<int>(pw));
    for (int y = 0; y < ph; y++)
        for (int x = 0; x < pw; x++)
            sub_grid[y][x] = initial_grid[py + y][px + x];

    // Extract sub-settlements
    std::vector<Settlement> sub_settlements;
    for (auto& s : initial_settlements) {
        if (s.x >= px && s.x < px + pw && s.y >= py && s.y < py + ph) {
            Settlement ns = s;
            ns.x -= px; ns.y -= py;
            sub_settlements.push_back(ns);
        }
    }

    int tile_lx = obs_vx - px;
    int tile_ly = obs_vy - py;

    auto emp = build_empirical(observations, obs_vx, obs_vy, obs_vw, obs_vh, H, W);

    // Compute avg observed settlement count
    double obs_avg_settle = 0;
    for (auto& obs : observations) {
        int count = 0;
        for (int y = 0; y < (int)obs.size() && y < obs_vh; y++)
            for (int x = 0; x < (int)obs[y].size() && x < obs_vw; x++) {
                int c = obs[y][x];
                if (c == CLASS_SETTLEMENT || c == CLASS_PORT) count++;
            }
        obs_avg_settle += count;
    }
    if (!observations.empty()) obs_avg_settle /= observations.size();

    // Run agent MC with candidate params and score
    auto eval_agent = [&](const simulator::AgentSimParams& ap) -> double {
        ProbTensor mf = simulator::agent_mean_field(sub_grid, sub_settlements, ap);
        return score_vs_empirical(mf, emp, sub_grid, tile_lx, tile_ly, obs_vw, obs_vh, obs_avg_settle);
    };

    int n_restarts = 2;
    int iters_per = iterations / n_restarts;

    simulator::AgentSimParams global_best;
    double global_best_score = -1;

    std::uniform_int_distribution<int> param_dist(0, N_AGENT_PARAMS - 1);
    std::uniform_real_distribution<double> delta_dist(-1.0, 1.0);
    std::uniform_int_distribution<int> coin(0, 3);

    for (int restart = 0; restart < n_restarts; restart++) {
        simulator::AgentSimParams current;
        if (restart == 1) {
            // Jittered restart
            std::uniform_real_distribution<double> jitter(0.7, 1.3);
            for (int i = 0; i < N_AGENT_PARAMS; i++) {
                double& val = current.*(AGENT_PARAM_DEFS[i].ptr);
                val *= jitter(rng);
                val = std::max(AGENT_PARAM_DEFS[i].lo, std::min(AGENT_PARAM_DEFS[i].hi, val));
            }
        }

        double best_score = eval_agent(current);
        simulator::AgentSimParams best = current;

        double step_size = 0.15;
        int no_improve = 0;

        for (int it = 0; it < iters_per; it++) {
            simulator::AgentSimParams trial = best;
            int n_perturb = (coin(rng) == 0) ? 2 : 1;
            for (int pp = 0; pp < n_perturb; pp++) {
                int pi = param_dist(rng);
                auto& def = AGENT_PARAM_DEFS[pi];
                double range = def.hi - def.lo;
                double delta = delta_dist(rng) * step_size * range * def.step_scale;
                double& val = trial.*(def.ptr);
                val = std::max(def.lo, std::min(def.hi, val + delta));
            }

            double score = eval_agent(trial);
            if (score > best_score) {
                best_score = score;
                best = trial;
                no_improve = 0;
            } else {
                no_improve++;
                if (no_improve >= 12) {
                    step_size = std::max(0.02, step_size * 0.80);
                    no_improve = 0;
                }
            }
        }

        if (best_score > global_best_score) {
            global_best_score = best_score;
            global_best = best;
        }
    }

    std::cerr << "AgentHC: mu=" << global_best.spawn_mu
              << " s=" << global_best.spawn_s
              << " lam=" << global_best.spawn_lambda
              << " ap=" << global_best.food_alpha_p
              << " af=" << global_best.food_alpha_f
              << " pg=" << global_best.pop_growth
              << " wb=" << global_best.winter_beta
              << " score=" << global_best_score << "\n";

    return {global_best, global_best_score};
}

}  // namespace hillclimb
