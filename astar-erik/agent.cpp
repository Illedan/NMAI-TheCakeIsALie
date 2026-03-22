#include "agent.h"

namespace agent {

// ============================================================
// Agent parameter definitions for hill climbing
// ============================================================

const AgentParams::ParamDef AgentParams::PARAM_DEFS[] = {
    {&AgentParams::pop_growth_rate,       0.01,  0.3},
    {&AgentParams::pop_food_factor,       0.2,   3.0},
    {&AgentParams::food_mean_revert_target, 0.3, 0.95},
    {&AgentParams::food_mean_revert_rate, 0.05,  0.8},
    {&AgentParams::food_pop_drain,        0.005, 0.15},
    {&AgentParams::defense_growth_rate,   0.01,  0.2},
    {&AgentParams::defense_pop_scale,     0.1,   1.0},
    {&AgentParams::raid_range,            1.0,   6.0},
    {&AgentParams::raid_prob_base,        0.02,  0.5},
    {&AgentParams::raid_defense_weight,   0.5,   5.0},
    {&AgentParams::raid_desperation,      0.1,   1.5},
    {&AgentParams::raid_pop_damage,       0.05,  0.7},
    {&AgentParams::raid_loot_frac,        0.05,  0.5},
    {&AgentParams::raid_conquest_prob,    0.05,  0.7},
    {&AgentParams::trade_range,           2.0,   8.0},
    {&AgentParams::trade_food_gain,       0.01,  0.15},
    {&AgentParams::winter_food_loss,      0.01,  0.2},
    {&AgentParams::collapse_food_threshold, 0.01, 0.2},
    {&AgentParams::collapse_prob_starve,  0.02,  0.4},
    {&AgentParams::collapse_pop_loss,     0.1,   0.9},
    {&AgentParams::expand_pop_threshold,  0.5,   3.0},
    {&AgentParams::expand_prob_base,      0.005, 0.15},
    {&AgentParams::expand_pop_factor,     0.005, 0.1},
    {&AgentParams::expand_radius,         1.5,   5.0},
    {&AgentParams::new_settlement_pop,    0.1,   1.0},
    {&AgentParams::new_settlement_food,   0.1,   0.9},
    {&AgentParams::ruin_rebuild_prob,     0.005, 0.1},
    {&AgentParams::ruin_to_empty_prob,    0.005, 0.1},
    {&AgentParams::ruin_to_forest_prob,   0.002, 0.05},
    {&AgentParams::port_conversion_prob,  0.002, 0.05},
    {&AgentParams::spontaneous_settle_prob, 0.001, 0.03},
    {&AgentParams::init_pop_mean,         0.3,   2.5},
    {&AgentParams::init_pop_std,          0.1,   1.5},
    {&AgentParams::init_food_mean,        0.3,   0.95},
    {&AgentParams::init_food_std,         0.05,  0.5},
    {&AgentParams::init_defense_mean,     0.1,   0.8},
    {&AgentParams::init_defense_std,      0.05,  0.5},
};
static constexpr int N_PARAMS = sizeof(AgentParams::PARAM_DEFS) / sizeof(AgentParams::PARAM_DEFS[0]);

// ============================================================
// Settlement entity (simulation state)
// ============================================================

struct SimSettlement {
    int x, y;
    double population, food, defense, wealth;
    int owner_id;
    bool has_port;
    bool alive;

    double distance_to(const SimSettlement& other) const {
        return std::max(std::abs(x - other.x), std::abs(y - other.y));
    }
};

// ============================================================
// World state
// ============================================================

struct World {
    int H, W;
    std::vector<std::vector<int>> grid;  // terrain codes
    std::vector<SimSettlement> settlements;
    std::vector<std::vector<bool>> ocean_adj;  // precomputed
    std::vector<std::vector<bool>> is_ocean;

    // Settlement spatial index: (x,y) -> settlement index
    std::map<std::pair<int,int>, int> settle_map;

    void rebuild_settle_map() {
        settle_map.clear();
        for (int i = 0; i < (int)settlements.size(); i++)
            if (settlements[i].alive)
                settle_map[{settlements[i].x, settlements[i].y}] = i;
    }

    SimSettlement* settlement_at(int x, int y) {
        auto it = settle_map.find({x, y});
        if (it != settle_map.end()) return &settlements[it->second];
        return nullptr;
    }

    void remove_settlement(SimSettlement& s) {
        s.alive = false;
        settle_map.erase({s.x, s.y});
        grid[s.y][s.x] = TERRAIN_RUIN;
    }

    void add_settlement(SimSettlement s) {
        grid[s.y][s.x] = s.has_port ? TERRAIN_PORT : TERRAIN_SETTLEMENT;
        settlements.push_back(s);
        settle_map[{s.x, s.y}] = (int)settlements.size() - 1;
    }

    std::vector<SimSettlement*> alive_settlements() {
        std::vector<SimSettlement*> result;
        for (auto& s : settlements)
            if (s.alive) result.push_back(&s);
        return result;
    }
};

// ============================================================
// Initialize world from initial state
// ============================================================

static World init_world(const std::vector<std::vector<int>>& initial_grid,
                         const std::vector<Settlement>& initial_settlements,
                         const AgentParams& params,
                         std::mt19937& rng) {
    World w;
    w.H = (int)initial_grid.size();
    w.W = w.H > 0 ? (int)initial_grid[0].size() : 0;
    w.grid = initial_grid;

    // Precompute ocean adjacency
    w.is_ocean.assign(w.H, std::vector<bool>(w.W, false));
    w.ocean_adj.assign(w.H, std::vector<bool>(w.W, false));
    for (int y = 0; y < w.H; y++)
        for (int x = 0; x < w.W; x++) {
            w.is_ocean[y][x] = (initial_grid[y][x] == TERRAIN_OCEAN);
        }
    for (int y = 0; y < w.H; y++)
        for (int x = 0; x < w.W; x++) {
            if (w.is_ocean[y][x]) continue;
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    int ny = y+dy, nx = x+dx;
                    if (ny >= 0 && ny < w.H && nx >= 0 && nx < w.W
                        && w.is_ocean[ny][nx])
                        w.ocean_adj[y][x] = true;
                }
        }

    // Create settlements with sampled stats
    std::normal_distribution<double> pop_dist(params.init_pop_mean, params.init_pop_std);
    std::normal_distribution<double> food_dist(params.init_food_mean, params.init_food_std);
    std::normal_distribution<double> def_dist(params.init_defense_mean, params.init_defense_std);
    std::normal_distribution<double> wealth_dist(params.init_wealth_mean, params.init_wealth_std);

    std::set<std::pair<int,int>> occupied;
    int owner_counter = 0;

    for (auto& is : initial_settlements) {
        SimSettlement s;
        s.x = is.x; s.y = is.y;
        s.population = std::max(0.1, pop_dist(rng));
        s.food = std::clamp(food_dist(rng), 0.0, 1.0);
        s.defense = std::clamp(def_dist(rng), 0.01, 1.0);
        s.wealth = std::max(0.0, wealth_dist(rng));
        s.owner_id = owner_counter++;
        s.has_port = is.has_port;
        s.alive = true;
        w.settlements.push_back(s);
        occupied.insert({is.x, is.y});
    }

    // Also create settlements for grid cells with settlement/port terrain
    // but no matching entity
    for (int y = 0; y < w.H; y++)
        for (int x = 0; x < w.W; x++) {
            if (occupied.count({x, y})) continue;
            int t = initial_grid[y][x];
            if (t == TERRAIN_SETTLEMENT || t == TERRAIN_PORT) {
                SimSettlement s;
                s.x = x; s.y = y;
                s.population = std::max(0.1, pop_dist(rng));
                s.food = std::clamp(food_dist(rng), 0.0, 1.0);
                s.defense = std::clamp(def_dist(rng), 0.01, 1.0);
                s.wealth = std::max(0.0, wealth_dist(rng));
                s.owner_id = owner_counter++;
                s.has_port = (t == TERRAIN_PORT);
                s.alive = true;
                w.settlements.push_back(s);
            }
        }

    w.rebuild_settle_map();
    return w;
}

// ============================================================
// Phase 1: Growth
// ============================================================

static void phase_growth(World& w, const AgentParams& p, std::mt19937& rng) {
    std::normal_distribution<double> noise_pop(0, 0.05);
    std::normal_distribution<double> noise_food(0, 0.05);
    std::normal_distribution<double> noise_def(0, 0.02);

    for (auto* s : w.alive_settlements()) {
        // Population growth
        double food_factor = s->food * p.pop_food_factor;
        double growth = p.pop_growth_rate * s->population * food_factor;
        growth += noise_pop(rng) * s->population;
        s->population += growth;
        s->population = std::max(0.1, s->population);

        // Food: mean-revert + drain
        s->food += p.food_mean_revert_rate * (p.food_mean_revert_target - s->food);
        s->food -= p.food_pop_drain * s->population;
        s->food += noise_food(rng);
        s->food = std::clamp(s->food, 0.0, 1.0);

        // Defense
        double defense_cap = std::min(1.0, s->population * p.defense_pop_scale);
        s->defense += p.defense_growth_rate * (defense_cap - s->defense);
        s->defense += noise_def(rng);
        s->defense = std::clamp(s->defense, 0.0, 1.0);

        // Wealth
        s->wealth += p.wealth_growth_rate + p.wealth_pop_factor * s->population;
        s->wealth = std::max(0.0, s->wealth);
    }
}

// ============================================================
// Phase 2: Conflict
// ============================================================

static void phase_conflict(World& w, const AgentParams& p, std::mt19937& rng) {
    auto alive = w.alive_settlements();
    // Shuffle for fairness
    std::shuffle(alive.begin(), alive.end(), rng);
    std::uniform_real_distribution<double> uni(0.0, 1.0);

    for (auto* attacker : alive) {
        if (!attacker->alive) continue;

        // Find targets in range from different faction
        for (auto* target : alive) {
            if (target == attacker || !target->alive) continue;
            if (target->owner_id == attacker->owner_id) continue;
            if (attacker->distance_to(*target) > p.raid_range) continue;

            double desperation = std::max(0.0, 1.0 - attacker->food) * p.raid_desperation;
            double defense_penalty = target->defense * p.raid_defense_weight;
            double raid_prob = std::clamp(p.raid_prob_base + desperation - defense_penalty, 0.0, 0.8);

            if (uni(rng) < raid_prob) {
                // Raid succeeds
                double pop_loss = target->population * p.raid_pop_damage;
                target->population -= pop_loss;
                target->population = std::max(0.1, target->population);

                double food_loot = target->food * p.raid_loot_frac;
                double wealth_loot = target->wealth * p.raid_loot_frac;
                target->food -= food_loot;
                target->wealth -= wealth_loot;
                attacker->food += food_loot * 0.5;
                attacker->wealth += wealth_loot * 0.5;

                if (uni(rng) < p.raid_conquest_prob) {
                    target->owner_id = attacker->owner_id;
                    target->population *= 0.5;
                    target->population = std::max(0.1, target->population);
                }

                break;  // One raid per attacker per step
            }
        }
    }
}

// ============================================================
// Phase 3: Trade
// ============================================================

static void phase_trade(World& w, const AgentParams& p, std::mt19937& /*rng*/) {
    auto alive = w.alive_settlements();
    for (auto* port : alive) {
        if (!port->has_port) continue;
        for (auto* partner : alive) {
            if (partner == port || !partner->has_port) continue;
            if (port->distance_to(*partner) > p.trade_range) continue;
            port->food = std::min(1.0, port->food + p.trade_food_gain);
            port->wealth += p.trade_wealth_gain;
        }
    }
}

// ============================================================
// Phase 4: Winter
// ============================================================

static void phase_winter(World& w, const AgentParams& p, std::mt19937& rng) {
    std::uniform_real_distribution<double> uni(0.0, 1.0);

    auto alive = w.alive_settlements();
    for (auto* s : alive) {
        s->food -= p.winter_food_loss;
        s->food = std::max(0.0, s->food);

        if (s->food < p.collapse_food_threshold) {
            if (uni(rng) < p.collapse_prob_starve) {
                s->population *= (1.0 - p.collapse_pop_loss);
                s->defense *= (1.0 - p.collapse_defense_loss);
                s->population = std::max(0.1, s->population);
                s->defense = std::max(0.0, s->defense);

                if (s->population < 0.15) {
                    w.remove_settlement(*s);
                }
            }
        }
    }
}

// ============================================================
// Phase 5: Environment (expansion, ruin resolution, port conversion)
// ============================================================

static void phase_environment(World& w, const AgentParams& p, std::mt19937& rng) {
    std::uniform_real_distribution<double> uni(0.0, 1.0);

    // Expansion: high-pop settlements spawn new ones
    auto alive = w.alive_settlements();
    for (auto* s : alive) {
        if (!s->alive) continue;
        if (s->population < p.expand_pop_threshold) continue;

        double excess = s->population - p.expand_pop_threshold;
        double expand_prob = p.expand_prob_base + p.expand_pop_factor * excess;
        if (uni(rng) < expand_prob) {
            // Find valid expansion cells
            int r = (int)p.expand_radius;
            std::vector<std::pair<int,int>> candidates;
            for (int dy = -r; dy <= r; dy++)
                for (int dx = -r; dx <= r; dx++) {
                    if (dy == 0 && dx == 0) continue;
                    int ny = s->y + dy, nx = s->x + dx;
                    if (ny < 0 || ny >= w.H || nx < 0 || nx >= w.W) continue;
                    int t = w.grid[ny][nx];
                    if (t == TERRAIN_EMPTY || t == TERRAIN_PLAINS || t == TERRAIN_FOREST) {
                        if (!w.settlement_at(nx, ny))
                            candidates.push_back({nx, ny});
                    }
                }

            if (!candidates.empty()) {
                auto [nx, ny] = candidates[rng() % candidates.size()];
                bool is_coastal = w.ocean_adj[ny][nx];
                SimSettlement ns;
                ns.x = nx; ns.y = ny;
                ns.population = p.new_settlement_pop;
                ns.food = p.new_settlement_food;
                ns.defense = p.new_settlement_defense;
                ns.wealth = 0.0;
                ns.owner_id = s->owner_id;
                ns.has_port = is_coastal && uni(rng) < p.port_conversion_prob * 5;
                ns.alive = true;
                w.add_settlement(ns);
                s->population -= p.new_settlement_pop * 0.5;
            }
        }
    }

    // Ruin resolution
    // Build settlement presence grid
    std::vector<std::vector<bool>> settle_presence(w.H, std::vector<bool>(w.W, false));
    auto alive2 = w.alive_settlements();
    for (auto* s : alive2) settle_presence[s->y][s->x] = true;

    for (int y = 0; y < w.H; y++) {
        for (int x = 0; x < w.W; x++) {
            if (w.grid[y][x] != TERRAIN_RUIN) continue;

            int n_nearby = 0;
            for (int dy = -2; dy <= 2; dy++)
                for (int dx = -2; dx <= 2; dx++) {
                    int ny = y+dy, nx = x+dx;
                    if (ny >= 0 && ny < w.H && nx >= 0 && nx < w.W)
                        if (settle_presence[ny][nx]) n_nearby++;
                }

            double r = uni(rng);
            double rebuild_bonus = 0.01 * n_nearby;
            if (r < p.ruin_rebuild_prob + rebuild_bonus) {
                // Find nearest settlement for owner
                int nearest_owner = 0;
                double min_dist = 999;
                for (auto* s : alive2) {
                    double d = std::max(std::abs(s->x - x), std::abs(s->y - y));
                    if (d < min_dist) { min_dist = d; nearest_owner = s->owner_id; }
                }

                SimSettlement ns;
                ns.x = x; ns.y = y;
                ns.population = p.new_settlement_pop;
                ns.food = p.new_settlement_food;
                ns.defense = p.new_settlement_defense;
                ns.wealth = 0.0;
                ns.owner_id = nearest_owner;
                ns.has_port = w.ocean_adj[y][x] && uni(rng) < 0.1;
                ns.alive = true;
                w.add_settlement(ns);
            } else if (r < p.ruin_rebuild_prob + rebuild_bonus + p.ruin_to_empty_prob) {
                w.grid[y][x] = TERRAIN_PLAINS;
            } else if (r < p.ruin_rebuild_prob + rebuild_bonus + p.ruin_to_empty_prob + p.ruin_to_forest_prob) {
                w.grid[y][x] = TERRAIN_FOREST;
            }
        }
    }

    // Spontaneous settlement from existing settlements
    auto alive3 = w.alive_settlements();
    for (auto* s : alive3) {
        if (!s->alive) continue;
        if (uni(rng) >= p.spontaneous_settle_prob) continue;

        int r = (int)p.spontaneous_settle_range;
        std::uniform_int_distribution<int> range_dist(-r, r);
        int dx = range_dist(rng), dy = range_dist(rng);
        if (dx == 0 && dy == 0) continue;
        int nx = s->x + dx, ny = s->y + dy;
        if (ny < 0 || ny >= w.H || nx < 0 || nx >= w.W) continue;
        int t = w.grid[ny][nx];
        if (t != TERRAIN_EMPTY && t != TERRAIN_PLAINS && t != TERRAIN_FOREST) continue;
        if (w.settlement_at(nx, ny)) continue;

        SimSettlement ns;
        ns.x = nx; ns.y = ny;
        ns.population = p.new_settlement_pop;
        ns.food = p.new_settlement_food;
        ns.defense = p.new_settlement_defense;
        ns.wealth = 0.0;
        ns.owner_id = s->owner_id;
        ns.has_port = w.ocean_adj[ny][nx] && uni(rng) < 0.1;
        ns.alive = true;
        w.add_settlement(ns);
    }

    // Port conversion: coastal settlements may become ports
    for (auto* s : w.alive_settlements()) {
        if (s->has_port) continue;
        if (w.ocean_adj[s->y][s->x]) {
            if (uni(rng) < p.port_conversion_prob) {
                s->has_port = true;
                w.grid[s->y][s->x] = TERRAIN_PORT;
            }
        }
    }
}

// ============================================================
// Run one full simulation
// ============================================================

static std::vector<std::vector<int>> simulate_once(
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<Settlement>& initial_settlements,
    const AgentParams& params,
    std::mt19937& rng) {

    World w = init_world(initial_grid, initial_settlements, params, rng);

    for (int t = 0; t < params.num_steps; t++) {
        phase_growth(w, params, rng);
        phase_conflict(w, params, rng);
        phase_trade(w, params, rng);
        phase_winter(w, params, rng);
        phase_environment(w, params, rng);
    }

    // Convert to class grid
    int H = w.H, W = w.W;
    std::vector<std::vector<int>> result(H, std::vector<int>(W));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
            result[y][x] = terrain_to_class(w.grid[y][x]);

    return result;
}

// ============================================================
// Monte Carlo: run N simulations, aggregate
// ============================================================

ProbTensor monte_carlo(
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<Settlement>& initial_settlements,
    const AgentParams& params,
    int n_sims,
    std::mt19937& rng) {

    int H = (int)initial_grid.size();
    int W = H > 0 ? (int)initial_grid[0].size() : 0;

    std::vector<std::vector<std::array<int, NUM_CLASSES>>> counts(
        H, std::vector<std::array<int, NUM_CLASSES>>(W, {0,0,0,0,0,0}));

    for (int sim = 0; sim < n_sims; sim++) {
        auto result = simulate_once(initial_grid, initial_settlements, params, rng);
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++)
                counts[y][x][result[y][x]]++;
    }

    ProbTensor tensor(H, std::vector<std::array<double, NUM_CLASSES>>(W));
    double inv_n = 1.0 / n_sims;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
            for (int c = 0; c < NUM_CLASSES; c++)
                tensor[y][x][c] = counts[y][x][c] * inv_n;

    return tensor;
}

// ============================================================
// Hill-climb agent parameters against observations
// ============================================================

static double score_vs_observations(
    const ProbTensor& mc_pred,
    const std::vector<std::vector<std::array<double, NUM_CLASSES>>>& emp,
    int obs_vx, int obs_vy, int obs_vw, int obs_vh,
    const std::vector<std::vector<int>>& initial_grid) {

    double total_kl = 0, total_w = 0;

    for (int ty = 0; ty < obs_vh; ty++) {
        for (int tx = 0; tx < obs_vw; tx++) {
            int gy = obs_vy + ty, gx = obs_vx + tx;
            if (gy >= (int)mc_pred.size() || gx >= (int)mc_pred[0].size()) continue;

            int t = initial_grid[gy][gx];
            if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;

            auto& p = emp[ty][tx];
            auto& q = mc_pred[gy][gx];

            // Entropy weight
            double h = 0;
            for (int c = 0; c < NUM_CLASSES; c++) {
                double pi = std::max(p[c], 0.001);
                h -= pi * std::log(pi);
            }
            double w = std::max(h, 0.01);

            // KL divergence
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
    return 100.0 * std::exp(-3.0 * total_kl / total_w);
}

AgentParams hill_climb(
    const std::vector<std::vector<std::vector<int>>>& observations,
    int obs_vx, int obs_vy, int obs_vw, int obs_vh,
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<Settlement>& initial_settlements,
    const AgentParams& start_params,
    int iterations,
    int n_sims_per_eval,
    std::mt19937& rng) {

    // Build empirical distribution from observations
    std::vector<std::vector<std::array<double, NUM_CLASSES>>> emp(
        obs_vh, std::vector<std::array<double, NUM_CLASSES>>(obs_vw, {0,0,0,0,0,0}));

    int n_obs = (int)observations.size();
    if (n_obs == 0) return start_params;

    double inv_n = 1.0 / n_obs;
    for (auto& obs : observations)
        for (int y = 0; y < (int)obs.size() && y < obs_vh; y++)
            for (int x = 0; x < (int)obs[y].size() && x < obs_vw; x++) {
                int c = obs[y][x];
                if (c >= 0 && c < NUM_CLASSES) emp[y][x][c] += inv_n;
            }

    // Evaluate starting params
    auto eval = [&](const AgentParams& p) -> double {
        ProbTensor pred = monte_carlo(initial_grid, initial_settlements, p, n_sims_per_eval, rng);
        return score_vs_observations(pred, emp, obs_vx, obs_vy, obs_vw, obs_vh, initial_grid);
    };

    AgentParams best = start_params;
    double best_score = eval(best);

    std::uniform_int_distribution<int> param_dist(0, N_PARAMS - 1);
    std::uniform_real_distribution<double> delta_dist(-1.0, 1.0);
    std::uniform_int_distribution<int> coin(0, 3);

    double step_size = 0.15;
    int no_improve = 0;

    for (int it = 0; it < iterations; it++) {
        AgentParams trial = best;

        // Perturb 1-2 params
        int n_perturb = (coin(rng) == 0) ? 2 : 1;
        for (int pp = 0; pp < n_perturb; pp++) {
            int pi = param_dist(rng);
            auto& def = AgentParams::PARAM_DEFS[pi];
            double range = def.hi - def.lo;
            double delta = delta_dist(rng) * step_size * range;
            double& val = trial.*(def.ptr);
            val = std::clamp(val + delta, def.lo, def.hi);
        }

        double score = eval(trial);
        if (score > best_score) {
            best_score = score;
            best = trial;
            no_improve = 0;
        } else {
            no_improve++;
            if (no_improve >= 10) {
                step_size = std::max(0.03, step_size * 0.85);
                no_improve = 0;
            }
        }
    }

    return best;
}

}  // namespace agent
