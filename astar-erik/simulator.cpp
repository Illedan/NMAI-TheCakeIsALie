#include "simulator.h"
#include <thread>
#include <queue>

namespace simulator {

// Global tuning parameters — defaults match replay-learned rates
TuneParams tune;

// ============================================================
// Parametric transition model
// All rates are simple functions of neighborhood features.
// Coefficients are tunable by hill climbing.
// ============================================================

std::array<double, NUM_CLASSES> get_transition_probs(const CellContext& ctx) {
    int c = ctx.terrain_class;
    double ns = ctx.n_settle_neighbors;
    double nf = ctx.n_forest_neighbors;
    double sr2 = ctx.settle_r2;
    bool ocean = ctx.has_ocean_neighbor;

    if (c == CLASS_MOUNTAIN)
        return {0.0, 0.0, 0.0, 0.0, 0.0, 1.0};

    if (c == CLASS_EMPTY) {
        // Empty -> Settlement: parametric rate with quadratic neighbor boost
        double p_s = tune.es_base * std::exp(tune.es_ns_coeff * ns + tune.es_ns2_coeff * ns * ns + tune.es_sr2_coeff * sr2);
        // Neighbor gating: kills spawning at ns=0, ramps quickly to 1
        // factor = 1 - exp(-es_ns_gate * ns). At ns=0: 0, ns=1,gate=3: 0.95
        if (tune.es_ns_gate > 0.01)
            p_s *= 1.0 - std::exp(-tune.es_ns_gate * ns);
        p_s = std::min(p_s, 0.50);
        double p_r = p_s * tune.er_ratio;
        double p_p = (ocean && ns >= 1) ? 0.001 : 0.0;
        double p_e = std::max(0.5, 1.0 - p_s - p_r - p_p);
        double total = p_e + p_s + p_p + p_r;
        return {p_e/total, p_s/total, p_p/total, p_r/total, 0.0, 0.0};
    }

    if (c == CLASS_SETTLEMENT) {
        // Settlement -> Ruin: support from allies, raiding from enemies
        // With N factions, ~(N-1)/N neighbors are enemies
        double nr = ctx.n_ruin_neighbors;
        double support = ns + tune.sr_nf_weight * nf;
        double p_r = tune.sr_base * std::exp(-tune.sr_support * support)
                   + tune.sr_raid * ns          // raiding: more neighbors = more enemies
                   + tune.sr_ruin_coeff * nr    // nearby ruins increase collapse
                   + tune.sr_sr2_coeff * sr2;
        p_r = std::max(0.002, std::min(0.30, p_r));
        double p_p = ocean ? std::max(0.001, tune.sp_base + tune.sp_ns_coeff * ns) : 0.0;
        p_p = std::min(p_p, 0.20);
        double p_s = std::max(0.4, 1.0 - p_r - p_p);
        double total = p_s + p_r + p_p;
        return {0.0, p_s/total, p_p/total, p_r/total, 0.0, 0.0};
    }

    if (c == CLASS_PORT) {
        double p_r = std::max(0.01, std::min(0.20,
            tune.pr_base + tune.pr_ns_coeff * ns));
        return {0.0, 0.0, 1.0 - p_r, p_r, 0.0, 0.0};
    }

    if (c == CLASS_RUIN) {
        double p_s = tune.ruin_settle + tune.ruin_ns_coeff * ns;
        double p_e = tune.ruin_empty - tune.ruin_ns_coeff * ns * 0.5;
        double p_f = tune.ruin_forest;
        double p_p = ocean ? tune.ruin_port : 0.0;
        // Clamp
        p_s = std::max(0.05, p_s);
        p_e = std::max(0.05, p_e);
        p_f = std::max(0.02, p_f);
        double total = p_s + p_e + p_f + p_p;
        return {p_e/total, p_s/total, p_p/total, 0.0, p_f/total, 0.0};
    }

    if (c == CLASS_FOREST) {
        double p_s = tune.fs_base * std::exp(tune.fs_ns_coeff * ns + tune.fs_ns2_coeff * ns * ns);
        p_s = std::min(p_s, 0.45);
        double p_r = p_s * tune.fr_ratio;
        double p_f = std::max(0.5, 1.0 - p_s - p_r);
        double total = p_f + p_s + p_r;
        return {0.0, p_s/total, 0.0, p_r/total, p_f/total, 0.0};
    }

    return {1.0, 0.0, 0.0, 0.0, 0.0, 0.0};
}

// ============================================================
// Single simulation run
// ============================================================

std::vector<std::vector<int>> simulate_once(
    const std::vector<std::vector<int>>& initial_grid,
    std::mt19937& rng) {

    int H = (int)initial_grid.size();
    int W = (int)initial_grid[0].size();

    std::vector<std::vector<int>> grid(H, std::vector<int>(W));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
            grid[y][x] = terrain_to_class(initial_grid[y][x]);

    // Precompute static features
    std::vector<std::vector<bool>> ocean_adj(H, std::vector<bool>(W, false));
    std::vector<std::vector<bool>> is_ocean(H, std::vector<bool>(W, false));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            is_ocean[y][x] = (initial_grid[y][x] == TERRAIN_OCEAN);
            if (!is_ocean[y][x]) {
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        if (dy == 0 && dx == 0) continue;
                        int ny = y+dy, nx = x+dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W
                            && initial_grid[ny][nx] == TERRAIN_OCEAN)
                            ocean_adj[y][x] = true;
                    }
            }
        }

    std::uniform_real_distribution<double> uni(0.0, 1.0);
    std::vector<std::vector<int>> next_grid(H, std::vector<int>(W));

    for (int year = 0; year < 50; year++) {
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                int c = grid[y][x];

                if (c == CLASS_MOUNTAIN || is_ocean[y][x]) {
                    next_grid[y][x] = c;
                    continue;
                }

                int ns = 0, nf = 0, nr = 0;
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        if (dy == 0 && dx == 0) continue;
                        int ny = y+dy, nx = x+dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W) {
                            int nc = grid[ny][nx];
                            if (nc == CLASS_SETTLEMENT || nc == CLASS_PORT) ns++;
                            else if (nc == CLASS_FOREST) nf++;
                            else if (nc == CLASS_RUIN) nr++;
                        }
                    }

                int sr2 = 0;
                for (int dy = -2; dy <= 2; dy++)
                    for (int dx = -2; dx <= 2; dx++) {
                        if (std::abs(dy) <= 1 && std::abs(dx) <= 1) continue;
                        int ny = y+dy, nx = x+dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W) {
                            int nc = grid[ny][nx];
                            if (nc == CLASS_SETTLEMENT || nc == CLASS_PORT) sr2++;
                        }
                    }

                CellContext ctx = {c, (double)ns, (double)nf, (double)nr, (double)sr2, ocean_adj[y][x]};
                auto probs = get_transition_probs(ctx);

                double r = uni(rng);
                double cumul = 0;
                int sampled = 0;
                for (int cl = 0; cl < NUM_CLASSES; cl++) {
                    cumul += probs[cl];
                    if (r <= cumul) { sampled = cl; break; }
                }
                next_grid[y][x] = sampled;
            }
        }
        std::swap(grid, next_grid);
    }

    return grid;
}

// ============================================================
// Monte Carlo
// ============================================================

ProbTensor monte_carlo(
    const std::vector<std::vector<int>>& initial_grid,
    int num_simulations,
    std::mt19937& rng) {

    int H = (int)initial_grid.size();
    int W = (int)initial_grid[0].size();

    int n_threads = std::min((int)std::thread::hardware_concurrency(), num_simulations);
    if (n_threads < 1) n_threads = 1;

    using CountGrid = std::vector<std::vector<std::array<int, NUM_CLASSES>>>;
    std::vector<CountGrid> thread_counts(n_threads);
    for (auto& tc : thread_counts)
        tc.assign(H, std::vector<std::array<int, NUM_CLASSES>>(W, {0,0,0,0,0,0}));

    std::vector<uint32_t> seeds(n_threads);
    for (int t = 0; t < n_threads; t++) seeds[t] = rng();

    std::vector<std::thread> threads;
    int sims_done = 0;
    for (int t = 0; t < n_threads; t++) {
        int my_sims = (num_simulations - sims_done) / (n_threads - t);
        sims_done += my_sims;
        threads.emplace_back([&, t, my_sims]() {
            std::mt19937 local_rng(seeds[t]);
            auto& counts = thread_counts[t];
            for (int sim = 0; sim < my_sims; sim++) {
                auto final_grid = simulate_once(initial_grid, local_rng);
                for (int y = 0; y < H; y++)
                    for (int x = 0; x < W; x++)
                        counts[y][x][final_grid[y][x]]++;
            }
        });
    }
    for (auto& th : threads) th.join();

    ProbTensor tensor(H, std::vector<std::array<double, NUM_CLASSES>>(W));
    double inv_n = 1.0 / num_simulations;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            for (int t = 0; t < n_threads; t++)
                for (int c = 0; c < NUM_CLASSES; c++)
                    tensor[y][x][c] += thread_counts[t][y][x][c];
            for (int c = 0; c < NUM_CLASSES; c++)
                tensor[y][x][c] *= inv_n;
        }

    return tensor;
}

// ============================================================
// Mean-field deterministic propagation
// ============================================================

ProbTensor mean_field(const std::vector<std::vector<int>>& initial_grid, int num_steps) {
    int H = (int)initial_grid.size();
    int W = (int)initial_grid[0].size();

    // Precompute static features
    std::vector<std::vector<bool>> ocean_adj(H, std::vector<bool>(W, false));
    std::vector<std::vector<bool>> is_ocean(H, std::vector<bool>(W, false));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            is_ocean[y][x] = (initial_grid[y][x] == TERRAIN_OCEAN);
            if (!is_ocean[y][x]) {
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        if (dy == 0 && dx == 0) continue;
                        int ny = y+dy, nx = x+dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W
                            && initial_grid[ny][nx] == TERRAIN_OCEAN)
                            ocean_adj[y][x] = true;
                    }
            }
        }

    // Compute BFS distance from initial settlements (for dist_decay)
    std::vector<std::vector<int>> settle_dist;
    bool use_dist_decay = (tune.dist_decay > 0.001);
    if (use_dist_decay) {
        settle_dist.assign(H, std::vector<int>(W, 999));
        std::queue<std::pair<int,int>> bfs;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                int c = terrain_to_class(initial_grid[y][x]);
                if (c == CLASS_SETTLEMENT || c == CLASS_PORT || c == CLASS_RUIN) {
                    settle_dist[y][x] = 0;
                    bfs.push({y, x});
                }
            }
        while (!bfs.empty()) {
            auto [cy, cx] = bfs.front(); bfs.pop();
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    if (dy == 0 && dx == 0) continue;
                    int ny = cy+dy, nx = cx+dx;
                    if (ny >= 0 && ny < H && nx >= 0 && nx < W) {
                        int nd = settle_dist[cy][cx] + 1;
                        if (nd < settle_dist[ny][nx]) {
                            settle_dist[ny][nx] = nd;
                            bfs.push({ny, nx});
                        }
                    }
                }
        }
    }

    // prob[y][x][class] = probability of being in that class
    ProbTensor cur(H, std::vector<std::array<double, NUM_CLASSES>>(W));
    ProbTensor nxt(H, std::vector<std::array<double, NUM_CLASSES>>(W));

    // Init: deterministic from initial grid
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            cur[y][x].fill(0.0);
            int c = terrain_to_class(initial_grid[y][x]);
            cur[y][x][c] = 1.0;
        }

    for (int year = 0; year < num_steps; year++) {
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                if (is_ocean[y][x]) {
                    nxt[y][x] = cur[y][x];
                    continue;
                }

                // Check if mountain (static)
                if (cur[y][x][CLASS_MOUNTAIN] > 0.999) {
                    nxt[y][x] = cur[y][x];
                    continue;
                }

                // Compute expected neighbor features
                double e_ns = 0, e_nf = 0, e_nr = 0;
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        if (dy == 0 && dx == 0) continue;
                        int ny = y+dy, nx = x+dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W) {
                            e_ns += cur[ny][nx][CLASS_SETTLEMENT] + cur[ny][nx][CLASS_PORT];
                            e_nf += cur[ny][nx][CLASS_FOREST];
                            e_nr += cur[ny][nx][CLASS_RUIN];
                        }
                    }

                double e_sr2 = 0;
                for (int dy = -2; dy <= 2; dy++)
                    for (int dx = -2; dx <= 2; dx++) {
                        if (std::abs(dy) <= 1 && std::abs(dx) <= 1) continue;
                        int ny = y+dy, nx = x+dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W) {
                            e_sr2 += cur[ny][nx][CLASS_SETTLEMENT] + cur[ny][nx][CLASS_PORT];
                        }
                    }

                // Mean-field variance correction for Jensen's inequality
                // E[exp(a*X)] ≈ exp(a*E[X] + 0.5*a²*Var[X])
                // Approximate Var[ns] ≈ E[ns] * (1 - E[ns]/8) (binomial-like)
                double ns_eff = e_ns;
                if (tune.mf_var_boost > 0 && e_ns > 0.01) {
                    double var_approx = e_ns * (1.0 - e_ns / 8.0);
                    if (var_approx > 0)
                        ns_eff = e_ns + tune.mf_var_boost * var_approx;
                }

                // Accumulate transition probabilities weighted by source class probability
                nxt[y][x].fill(0.0);
                for (int from = 0; from < NUM_CLASSES; from++) {
                    double p_from = cur[y][x][from];
                    if (p_from < 1e-10) continue;

                    CellContext ctx = {from, ns_eff, e_nf, e_nr, e_sr2, ocean_adj[y][x]};
                    auto trans = get_transition_probs(ctx);

                    // Distance-based settlement spawning decay
                    if (use_dist_decay && (from == CLASS_EMPTY || from == CLASS_FOREST) && settle_dist[y][x] > 0) {
                        double factor = std::exp(-tune.dist_decay * settle_dist[y][x]);
                        double s_orig = trans[CLASS_SETTLEMENT];
                        double p_orig = trans[CLASS_PORT];
                        trans[CLASS_SETTLEMENT] *= factor;
                        trans[CLASS_PORT] *= factor;
                        // Redistribute removed probability mass back to source class
                        trans[from] += (s_orig - trans[CLASS_SETTLEMENT]) + (p_orig - trans[CLASS_PORT]);
                    }

                    for (int to = 0; to < NUM_CLASSES; to++)
                        nxt[y][x][to] += p_from * trans[to];
                }
            }
        }
        std::swap(cur, nxt);
    }

    return cur;
}

// ============================================================
// Agent-based simulation with research-calibrated mechanics
// ============================================================

AgentSimParams agent_params;

struct SimSettle {
    int x, y;
    double pop, food, wealth, defense;
    int owner_id;
    bool has_port;
    bool alive;
};

static std::vector<std::vector<int>> agent_simulate_once(
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<Settlement>& initial_settlements,
    const AgentSimParams& p,
    std::mt19937& rng) {

    int H = (int)initial_grid.size();
    int W = (int)initial_grid[0].size();

    // Build grid (mutable copy)
    std::vector<std::vector<int>> grid(H, std::vector<int>(W));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
            grid[y][x] = initial_grid[y][x];

    // Precompute ocean adjacency + ocean neighbor count
    std::vector<std::vector<bool>> is_ocean(H, std::vector<bool>(W, false));
    std::vector<std::vector<int>> ocean_count(H, std::vector<int>(W, 0));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            is_ocean[y][x] = (initial_grid[y][x] == TERRAIN_OCEAN);
        }
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            if (is_ocean[y][x]) continue;
            int cnt = 0;
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    if (dy == 0 && dx == 0) continue;
                    int ny = y+dy, nx = x+dx;
                    if (ny >= 0 && ny < H && nx >= 0 && nx < W && is_ocean[ny][nx])
                        cnt++;
                }
            ocean_count[y][x] = cnt;
        }

    // Initialize settlements
    std::vector<SimSettle> settlements;
    std::uniform_real_distribution<double> uni(0.0, 1.0);
    std::uniform_real_distribution<double> pop_dist(0.50, 1.50);
    std::uniform_real_distribution<double> food_dist(0.30, 0.80);
    std::uniform_real_distribution<double> wealth_dist(0.10, 0.50);
    std::uniform_real_distribution<double> def_dist(0.20, 0.60);

    for (auto& s : initial_settlements) {
        SimSettle ss;
        ss.x = s.x; ss.y = s.y;
        ss.pop = pop_dist(rng);
        ss.food = food_dist(rng);
        ss.wealth = wealth_dist(rng);
        ss.defense = def_dist(rng);
        ss.owner_id = s.owner_id;
        ss.has_port = s.has_port;
        ss.alive = true;
        settlements.push_back(ss);
    }

    // Grid-based settlement lookup (O(1) instead of O(n))
    std::vector<std::vector<int>> settle_idx(H, std::vector<int>(W, -1));
    for (int i = 0; i < (int)settlements.size(); i++)
        if (settlements[i].alive)
            settle_idx[settlements[i].y][settlements[i].x] = i;

    auto settle_at = [&](int x, int y) -> SimSettle* {
        int idx = settle_idx[y][x];
        return (idx >= 0 && settlements[idx].alive) ? &settlements[idx] : nullptr;
    };

    for (int step = 0; step < p.num_steps; step++) {
        // === GROWTH PHASE ===

        // Food production: each land tile adjacent to a settlement contributes food
        // Food from a tile is split among all adjacent settlements
        for (auto& s : settlements) {
            if (!s.alive) continue;
            double food_gain = 0;
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    if (dy == 0 && dx == 0) continue;
                    int ny = s.y + dy, nx = s.x + dx;
                    if (ny < 0 || ny >= H || nx < 0 || nx >= W) continue;
                    int t = grid[ny][nx];
                    double yield = 0;
                    if (t == TERRAIN_PLAINS || t == TERRAIN_EMPTY) yield = p.food_alpha_p;
                    else if (t == TERRAIN_FOREST) yield = p.food_alpha_f;
                    // Split yield among adjacent settlements
                    if (yield > 0) {
                        int share = 0;
                        for (int dy2 = -1; dy2 <= 1; dy2++)
                            for (int dx2 = -1; dx2 <= 1; dx2++) {
                                if (dy2 == 0 && dx2 == 0) continue;
                                int sy = ny+dy2, sx = nx+dx2;
                                if (sy >= 0 && sy < H && sx >= 0 && sx < W && settle_at(sx, sy))
                                    share++;
                            }
                        if (share > 0) food_gain += yield / share;
                    }
                }
            s.food += food_gain;
        }

        // Population growth: pop += pop_growth * food
        for (auto& s : settlements) {
            if (!s.alive) continue;
            s.pop += p.pop_growth * s.food;
        }

        // Settlement spawning: logistic CDF based on population
        int n_alive = 0;
        for (auto& s : settlements) if (s.alive) n_alive++;
        // Process spawning for existing settlements (snapshot indices)
        int n_current = (int)settlements.size();
        for (int i = 0; i < n_current; i++) {
            auto& s = settlements[i];
            if (!s.alive) continue;

            // Logistic spawn probability
            double spawn_prob = 1.0 / (1.0 + std::exp(-(s.pop - p.spawn_mu) / std::max(0.01, p.spawn_s)));
            if (uni(rng) >= spawn_prob) continue;

            // Sample spawn distance (geometric)
            int max_dist = 5;
            std::vector<double> dist_probs(max_dist);
            double dist_sum = 0;
            for (int d = 1; d <= max_dist; d++) {
                dist_probs[d-1] = std::exp(-p.spawn_lambda * (d-1)) * (1.0 - std::exp(-p.spawn_lambda));
                dist_sum += dist_probs[d-1];
            }
            // Normalize
            for (auto& dp : dist_probs) dp /= dist_sum;

            // Sample distance
            double r = uni(rng);
            int spawn_dist = 1;
            double cum = 0;
            for (int d = 0; d < max_dist; d++) {
                cum += dist_probs[d];
                if (r <= cum) { spawn_dist = d + 1; break; }
            }

            // Find valid cells at that distance (Chebyshev)
            // Can spawn on empty, plains, forest, AND ruins
            std::vector<std::pair<int,int>> candidates;
            for (int dy = -spawn_dist; dy <= spawn_dist; dy++)
                for (int dx = -spawn_dist; dx <= spawn_dist; dx++) {
                    if (std::max(std::abs(dy), std::abs(dx)) != spawn_dist) continue;
                    int ny = s.y + dy, nx = s.x + dx;
                    if (ny < 0 || ny >= H || nx < 0 || nx >= W) continue;
                    int t = grid[ny][nx];
                    if (t == TERRAIN_EMPTY || t == TERRAIN_PLAINS || t == TERRAIN_FOREST || t == TERRAIN_RUIN) {
                        if (!settle_at(nx, ny))
                            candidates.push_back({nx, ny});
                    }
                }

            // If no candidates at exact distance, try closer
            if (candidates.empty()) {
                for (int d = spawn_dist - 1; d >= 1 && candidates.empty(); d--) {
                    for (int dy = -d; dy <= d; dy++)
                        for (int dx = -d; dx <= d; dx++) {
                            if (std::max(std::abs(dy), std::abs(dx)) != d) continue;
                            int ny = s.y + dy, nx = s.x + dx;
                            if (ny < 0 || ny >= H || nx < 0 || nx >= W) continue;
                            int t = grid[ny][nx];
                            if (t == TERRAIN_EMPTY || t == TERRAIN_PLAINS || t == TERRAIN_FOREST || t == TERRAIN_RUIN) {
                                if (!settle_at(nx, ny))
                                    candidates.push_back({nx, ny});
                            }
                        }
                }
            }

            if (!candidates.empty()) {
                // Multi-spawn: geometric with p_multi ~= 0.076
                constexpr double P_MULTI = 0.076;
                int n_children = 1;
                while (uni(rng) < P_MULTI && n_children < (int)candidates.size())
                    n_children++;

                // Shuffle candidates for multi-spawn
                for (int ci = 0; ci < n_children && ci < (int)candidates.size(); ci++) {
                    int ri = ci + rng() % (candidates.size() - ci);
                    std::swap(candidates[ci], candidates[ri]);

                    auto [nx, ny] = candidates[ci];

                    // Tier selection based on target tile (empirical finding):
                    // Ruin tile -> ALWAYS lo-tier
                    // Plains/Forest/Empty -> 83% hi, 12% mid, 4% lo
                    int t = grid[ny][nx];
                    bool is_ruin = (t == TERRAIN_RUIN);
                    double child_pop, child_def, child_wealth_frac, child_food;
                    if (is_ruin) {
                        // Lo-tier (100% on ruins)
                        child_pop = p.child_pop;           // 0.400
                        child_def = p.child_def;           // 0.150
                        child_wealth_frac = p.child_wealth_frac; // 0.10
                        child_food = 0.15;                 // constant, no parent transfer
                    } else {
                        double tier_r = uni(rng);
                        if (tier_r < 0.83) {
                            // Hi-tier
                            child_pop = 0.500;
                            child_def = 0.200;
                            child_wealth_frac = 0.217;
                            child_food = 0.15 + 0.092;    // baseline + food transfer
                            // Hi-tier costs parent pop and food
                            settlements[i].pop -= 0.10;
                            settlements[i].food -= 0.22;
                        } else if (tier_r < 0.95) {
                            // Mid-tier
                            child_pop = 0.425;
                            child_def = 0.160;
                            child_wealth_frac = 0.20;
                            child_food = 0.30;
                        } else {
                            // Lo-tier (rare on fresh land)
                            child_pop = p.child_pop;
                            child_def = p.child_def;
                            child_wealth_frac = p.child_wealth_frac;
                            child_food = 0.15;
                        }
                    }

                    SimSettle child;
                    child.x = nx; child.y = ny;
                    child.pop = child_pop;
                    child.food = child_food;
                    child.defense = child_def;
                    child.wealth = s.wealth * child_wealth_frac;
                    child.owner_id = s.owner_id;
                    child.has_port = (ocean_count[ny][nx] >= 2 && uni(rng) < p.port_rate);
                    child.alive = true;
                    grid[ny][nx] = child.has_port ? TERRAIN_PORT : TERRAIN_SETTLEMENT;
                    settle_idx[ny][nx] = (int)settlements.size();
                    settlements.push_back(child);
                }
            }
        }

        // Port formation for existing settlements
        for (auto& s : settlements) {
            if (!s.alive || s.has_port) continue;
            if (ocean_count[s.y][s.x] >= 2 && s.food >= p.port_thresh) {
                if (uni(rng) < p.port_rate) {
                    s.has_port = true;
                    grid[s.y][s.x] = TERRAIN_PORT;
                }
            }
        }

        // === RAIDING PHASE ===
        // Enemy settlements within dist 3-4 increase collapse probability
        // Collapse rate: 2.4% base, +1.5% per enemy within dist 3, +0.5% per enemy at dist 4
        for (int i = 0; i < (int)settlements.size(); i++) {
            auto& s = settlements[i];
            if (!s.alive) continue;

            int enemy_count = 0;
            for (int dy = -4; dy <= 4; dy++)
                for (int dx = -4; dx <= 4; dx++) {
                    if (dy == 0 && dx == 0) continue;
                    int dist = std::max(std::abs(dy), std::abs(dx));
                    if (dist > 4) continue;
                    int ny = s.y + dy, nx = s.x + dx;
                    if (ny < 0 || ny >= H || nx < 0 || nx >= W) continue;
                    auto* other = settle_at(nx, ny);
                    if (other && other->owner_id != s.owner_id) {
                        // Closer enemies have stronger effect
                        if (dist <= 3) enemy_count += 2;
                        else enemy_count += 1;
                    }
                }

            // Raiding collapse probability
            double raid_prob = 0;
            if (enemy_count > 0) {
                // Empirical: 0 enemies=2.4%, 1=3.9%, 2=7.4%, 3=10.6%, 5+=21%
                raid_prob = 0.015 * enemy_count;
                raid_prob = std::min(raid_prob, 0.25);
            }

            if (raid_prob > 0 && uni(rng) < raid_prob) {
                s.alive = false;
                settle_idx[s.y][s.x] = -1;
                grid[s.y][s.x] = TERRAIN_RUIN;
            }
        }

        // === WINTER PHASE ===
        // Food consumed by population
        for (auto& s : settlements) {
            if (!s.alive) continue;
            s.food -= s.pop * p.winter_beta;
            if (s.food <= 0) {
                // Settlement collapses to ruin
                s.alive = false;
                settle_idx[s.y][s.x] = -1;
                grid[s.y][s.x] = TERRAIN_RUIN;
            }
        }

        // === ENVIRONMENT: ruin resolution ===
        // Ruins transition IMMEDIATELY (never persist >1 step)
        // Empirical split: 48% settlement, 33% plains, 18% forest, 1% port
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                if (grid[y][x] != TERRAIN_RUIN) continue;

                double r = uni(rng);
                if (r < 0.48) {
                    // Rebuild as settlement (find nearby owner)
                    int owner = -1;
                    for (int dy = -2; dy <= 2 && owner < 0; dy++)
                        for (int dx = -2; dx <= 2 && owner < 0; dx++) {
                            int ny = y+dy, nx = x+dx;
                            if (ny >= 0 && ny < H && nx >= 0 && nx < W) {
                                auto* nearby = settle_at(nx, ny);
                                if (nearby) owner = nearby->owner_id;
                            }
                        }
                    SimSettle ns;
                    ns.x = x; ns.y = y;
                    ns.pop = 0.400; ns.food = 0.15; ns.defense = 0.150; ns.wealth = 0.0;
                    ns.owner_id = owner; ns.has_port = false; ns.alive = true;
                    grid[y][x] = TERRAIN_SETTLEMENT;
                    settle_idx[y][x] = (int)settlements.size();
                    settlements.push_back(ns);
                } else if (r < 0.48 + 0.33) {
                    // Fade to plains
                    grid[y][x] = TERRAIN_PLAINS;
                } else if (r < 0.48 + 0.33 + 0.18) {
                    // Reclaimed by nature
                    grid[y][x] = TERRAIN_FOREST;
                } else {
                    // Port (rare, ~1%, only if coastal)
                    if (ocean_count[y][x] >= 2) {
                        SimSettle ns;
                        ns.x = x; ns.y = y;
                        ns.pop = 0.400; ns.food = 0.15; ns.defense = 0.150; ns.wealth = 0.0;
                        ns.owner_id = -1; ns.has_port = true; ns.alive = true;
                        grid[y][x] = TERRAIN_PORT;
                        settle_idx[y][x] = (int)settlements.size();
                        settlements.push_back(ns);
                    } else {
                        grid[y][x] = TERRAIN_PLAINS;
                    }
                }
            }
        }
    }

    // Convert to class grid
    std::vector<std::vector<int>> result(H, std::vector<int>(W));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
            result[y][x] = terrain_to_class(grid[y][x]);
    return result;
}

ProbTensor agent_monte_carlo(
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<Settlement>& initial_settlements,
    const AgentSimParams& params,
    int num_simulations,
    std::mt19937& rng) {

    int H = (int)initial_grid.size();
    int W = (int)initial_grid[0].size();

    int n_threads = std::min((int)std::thread::hardware_concurrency(), num_simulations);
    if (n_threads < 1) n_threads = 1;

    // Per-thread count arrays
    using CountGrid = std::vector<std::vector<std::array<int, NUM_CLASSES>>>;
    std::vector<CountGrid> thread_counts(n_threads);
    for (auto& tc : thread_counts)
        tc.assign(H, std::vector<std::array<int, NUM_CLASSES>>(W, {0,0,0,0,0,0}));

    // Generate per-thread RNG seeds
    std::vector<uint32_t> seeds(n_threads);
    for (int t = 0; t < n_threads; t++) seeds[t] = rng();

    // Distribute simulations across threads
    std::vector<std::thread> threads;
    int sims_done = 0;
    for (int t = 0; t < n_threads; t++) {
        int my_sims = (num_simulations - sims_done) / (n_threads - t);
        sims_done += my_sims;
        threads.emplace_back([&, t, my_sims]() {
            std::mt19937 local_rng(seeds[t]);
            auto& counts = thread_counts[t];
            for (int sim = 0; sim < my_sims; sim++) {
                auto final_grid = agent_simulate_once(initial_grid, initial_settlements, params, local_rng);
                for (int y = 0; y < H; y++)
                    for (int x = 0; x < W; x++)
                        counts[y][x][final_grid[y][x]]++;
            }
        });
    }
    for (auto& th : threads) th.join();

    // Merge counts
    ProbTensor tensor(H, std::vector<std::array<double, NUM_CLASSES>>(W));
    double inv_n = 1.0 / num_simulations;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            for (int t = 0; t < n_threads; t++)
                for (int c = 0; c < NUM_CLASSES; c++)
                    tensor[y][x][c] += thread_counts[t][y][x][c];
            for (int c = 0; c < NUM_CLASSES; c++)
                tensor[y][x][c] *= inv_n;
        }

    return tensor;
}

// ============================================================
// Mean-field agent simulation
// Tracks per-cell: class probabilities + expected pop/food
// ============================================================

ProbTensor agent_mean_field(
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<Settlement>& initial_settlements,
    const AgentSimParams& p) {

    int H = (int)initial_grid.size();
    int W = (int)initial_grid[0].size();

    // Precompute static terrain info
    std::vector<std::vector<bool>> is_ocean(H, std::vector<bool>(W, false));
    std::vector<std::vector<bool>> is_mountain(H, std::vector<bool>(W, false));
    std::vector<std::vector<int>> ocean_count(H, std::vector<int>(W, 0));
    // P(terrain yields food): plains/empty and forest
    std::vector<std::vector<double>> yield_plains(H, std::vector<double>(W, 0));
    std::vector<std::vector<double>> yield_forest(H, std::vector<double>(W, 0));

    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int t = initial_grid[y][x];
            is_ocean[y][x] = (t == TERRAIN_OCEAN);
            is_mountain[y][x] = (t == TERRAIN_MOUNTAIN);
            if (t == TERRAIN_PLAINS || t == TERRAIN_EMPTY) yield_plains[y][x] = 1.0;
            if (t == TERRAIN_FOREST) yield_forest[y][x] = 1.0;
        }

    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            if (is_ocean[y][x]) continue;
            int cnt = 0;
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    if (dy == 0 && dx == 0) continue;
                    int ny = y+dy, nx = x+dx;
                    if (ny >= 0 && ny < H && nx >= 0 && nx < W && is_ocean[ny][nx])
                        cnt++;
                }
            ocean_count[y][x] = cnt;
        }

    // Per-cell state: class probs + expected pop and food (weighted by P(settle+port))
    ProbTensor prob(H, std::vector<std::array<double, NUM_CLASSES>>(W));
    std::vector<std::vector<double>> e_pop(H, std::vector<double>(W, 0));
    std::vector<std::vector<double>> e_food(H, std::vector<double>(W, 0));

    // Initialize from initial grid + settlement stats
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            prob[y][x].fill(0.0);
            int c = terrain_to_class(initial_grid[y][x]);
            prob[y][x][c] = 1.0;
        }

    // Set initial pop/food for known settlements (mean of uniform distributions)
    for (auto& s : initial_settlements) {
        if (s.x >= 0 && s.x < W && s.y >= 0 && s.y < H) {
            e_pop[s.y][s.x] = 1.0;   // E[U(0.5,1.5)]
            e_food[s.y][s.x] = 0.55;  // E[U(0.3,0.8)]
        }
    }

    // Precompute spawn distance weights
    constexpr int MAX_SPAWN_DIST = 5;
    double dist_weights[MAX_SPAWN_DIST];
    {
        double sum = 0;
        for (int d = 1; d <= MAX_SPAWN_DIST; d++) {
            dist_weights[d-1] = std::exp(-p.spawn_lambda * (d-1)) * (1.0 - std::exp(-p.spawn_lambda));
            sum += dist_weights[d-1];
        }
        for (int d = 0; d < MAX_SPAWN_DIST; d++) dist_weights[d] /= sum;
    }

    // Precompute valid land target count at each Chebyshev distance (static)
    std::vector<std::vector<std::array<int, MAX_SPAWN_DIST>>> land_targets(
        H, std::vector<std::array<int, MAX_SPAWN_DIST>>(W));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
            for (int d = 1; d <= MAX_SPAWN_DIST; d++) {
                int cnt = 0;
                for (int dy = -d; dy <= d; dy++)
                    for (int dx = -d; dx <= d; dx++) {
                        if (std::max(std::abs(dy), std::abs(dx)) != d) continue;
                        int ny = y+dy, nx = x+dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W
                            && !is_ocean[ny][nx] && !is_mountain[ny][nx])
                            cnt++;
                    }
                land_targets[y][x][d-1] = cnt;
            }

    // Temporary buffers
    std::vector<std::vector<double>> spawn_pressure(H, std::vector<double>(W, 0));
    ProbTensor next_prob(H, std::vector<std::array<double, NUM_CLASSES>>(W));
    std::vector<std::vector<double>> next_pop(H, std::vector<double>(W, 0));
    std::vector<std::vector<double>> next_food(H, std::vector<double>(W, 0));

    // Precompute per-tile: expected adjacent settlement count (reused each step)
    std::vector<std::vector<double>> adj_settle(H, std::vector<double>(W, 0));

    for (int step = 0; step < p.num_steps; step++) {
        // Compute E[adjacent settlements] for each tile
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                double ns = 0;
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        if (dy == 0 && dx == 0) continue;
                        int ny = y+dy, nx = x+dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W)
                            ns += prob[ny][nx][CLASS_SETTLEMENT] + prob[ny][nx][CLASS_PORT];
                    }
                adj_settle[y][x] = ns;
            }

        // === FOOD PRODUCTION ===
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                double p_settle = prob[y][x][CLASS_SETTLEMENT] + prob[y][x][CLASS_PORT];
                if (p_settle < 1e-6) continue;

                double food_gain = 0;
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        if (dy == 0 && dx == 0) continue;
                        int ny = y+dy, nx = x+dx;
                        if (ny < 0 || ny >= H || nx < 0 || nx >= W) continue;

                        double yield_val = yield_plains[ny][nx] * p.food_alpha_p
                                         + yield_forest[ny][nx] * p.food_alpha_f;
                        if (yield_val < 1e-8) continue;

                        if (adj_settle[ny][nx] > 0.01)
                            food_gain += yield_val / adj_settle[ny][nx];
                    }
                e_food[y][x] += food_gain * p_settle;
            }

        // === POPULATION GROWTH ===
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                double p_settle = prob[y][x][CLASS_SETTLEMENT] + prob[y][x][CLASS_PORT];
                if (p_settle < 1e-6) continue;
                double avg_food = (p_settle > 0.01) ? e_food[y][x] / p_settle : 0;
                e_pop[y][x] += p.pop_growth * avg_food * p_settle;
            }

        // === SPAWN PRESSURE ===
        // For each cell, compute probability it spawns, then distribute to neighbors
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++)
                spawn_pressure[y][x] = 0;

        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                double p_settle = prob[y][x][CLASS_SETTLEMENT] + prob[y][x][CLASS_PORT];
                if (p_settle < 1e-6) continue;

                // Expected pop per settlement at this cell
                double avg_pop = (p_settle > 0.01) ? e_pop[y][x] / p_settle : 0;
                // Logistic spawn probability
                double spawn_prob = p_settle / (1.0 + std::exp(-(avg_pop - p.spawn_mu) / std::max(0.01, p.spawn_s)));

                if (spawn_prob < 1e-8) continue;

                // Distribute spawn pressure by distance (using precomputed target counts)
                for (int d = 1; d <= MAX_SPAWN_DIST; d++) {
                    double d_weight = dist_weights[d-1] * spawn_prob;
                    if (d_weight < 1e-8) continue;

                    int n_targets = land_targets[y][x][d-1];
                    if (n_targets == 0) continue;
                    double per_target = d_weight / n_targets;

                    for (int dy = -d; dy <= d; dy++)
                        for (int dx = -d; dx <= d; dx++) {
                            if (std::max(std::abs(dy), std::abs(dx)) != d) continue;
                            int ny = y+dy, nx = x+dx;
                            if (ny < 0 || ny >= H || nx < 0 || nx >= W) continue;
                            if (is_ocean[ny][nx] || is_mountain[ny][nx]) continue;
                            spawn_pressure[ny][nx] += per_target;
                        }
                }
            }

        // === UPDATE PROBABILITIES ===
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                next_prob[y][x] = prob[y][x];
                next_pop[y][x] = e_pop[y][x];
                next_food[y][x] = e_food[y][x];

                if (is_ocean[y][x] || is_mountain[y][x]) continue;

                double p_settle = prob[y][x][CLASS_SETTLEMENT] + prob[y][x][CLASS_PORT];

                // Winter: food consumed, possible ruin
                double avg_pop = (p_settle > 0.01) ? e_pop[y][x] / p_settle : 0;
                double avg_food = (p_settle > 0.01) ? e_food[y][x] / p_settle : 0;
                double food_after = avg_food - avg_pop * p.winter_beta;
                // Probability of ruin from starvation (food <= 0)
                double p_starve = 0;
                if (food_after < 0.1 && p_settle > 0.01) {
                    // Approximate: prob of starvation increases as food decreases
                    p_starve = p_settle * std::max(0.0, std::min(1.0, 0.5 - food_after));
                }

                // Port formation
                double p_port_gain = 0;
                if (ocean_count[y][x] >= 2 && avg_food >= p.port_thresh) {
                    p_port_gain = prob[y][x][CLASS_SETTLEMENT] * p.port_rate;
                }

                // Spawn converts non-settlement to settlement
                double sp = std::min(spawn_pressure[y][x], 0.8); // cap at 80%
                double p_non_settle = 1.0 - p_settle;
                double p_new_settle = p_non_settle * sp;

                // Apply transitions
                // Settlement gains from spawn
                next_prob[y][x][CLASS_SETTLEMENT] += p_new_settle - p_port_gain;
                next_prob[y][x][CLASS_PORT] += p_port_gain;
                // Losses from the source classes (proportional)
                if (p_non_settle > 0.01) {
                    for (int c = 0; c < NUM_CLASSES; c++) {
                        if (c == CLASS_SETTLEMENT || c == CLASS_PORT) continue;
                        if (c == CLASS_SETTLEMENT || c == CLASS_PORT) continue;
                        double frac = prob[y][x][c] / p_non_settle;
                        next_prob[y][x][c] -= p_new_settle * frac;
                    }
                }

                // Starvation: settlement -> ruin
                if (p_starve > 0) {
                    double settle_frac = (p_settle > 0.01) ? prob[y][x][CLASS_SETTLEMENT] / p_settle : 0.5;
                    next_prob[y][x][CLASS_SETTLEMENT] -= p_starve * settle_frac;
                    next_prob[y][x][CLASS_PORT] -= p_starve * (1.0 - settle_frac);
                    next_prob[y][x][CLASS_RUIN] += p_starve;
                }

                // Ruin resolution (slow decay)
                double p_ruin = prob[y][x][CLASS_RUIN];
                if (p_ruin > 0.01) {
                    double ruin_decay = p_ruin * 0.05;
                    next_prob[y][x][CLASS_RUIN] -= ruin_decay;
                    next_prob[y][x][CLASS_EMPTY] += ruin_decay * 0.5;
                    next_prob[y][x][CLASS_FOREST] += ruin_decay * 0.3;
                    next_prob[y][x][CLASS_SETTLEMENT] += ruin_decay * 0.2;
                }

                // Update pop/food for new settlements
                next_pop[y][x] = e_pop[y][x] + p_new_settle * p.child_pop;
                next_food[y][x] = std::max(0.0, e_food[y][x] - p_settle * avg_pop * p.winter_beta);
                next_food[y][x] += p_new_settle * 0.5; // child food

                // Clamp probabilities
                double total = 0;
                for (int c = 0; c < NUM_CLASSES; c++) {
                    next_prob[y][x][c] = std::max(0.0, next_prob[y][x][c]);
                    total += next_prob[y][x][c];
                }
                if (total > 0)
                    for (int c = 0; c < NUM_CLASSES; c++)
                        next_prob[y][x][c] /= total;
            }

        std::swap(prob, next_prob);
        std::swap(e_pop, next_pop);
        std::swap(e_food, next_food);
    }

    return prob;
}

}  // namespace simulator
