// evo_sim.cpp — Batch simulation for evolutionary parameter search.
// Each particle gets its own initial settlement stats + hidden params.
// Runs K stochastic simulations per particle, outputs per-particle class counts.
//
// Input (text, stdin):
//   H W n_settle n_particles n_steps rng_offset n_runs_per_particle
//   grid (H rows of W ints)
//   settlement positions (n_settle rows: x y has_port)
//   For each of n_particles:
//     settlement stats (n_settle rows: pop food wealth defense)
//     alpha_pop alpha_def alpha_plains alpha_forest beta
//     mu_spawn s_spawn sigma_dist p_multi hi_food_transfer mu_f_tier
//     port_thresh
//     p_raid_nonport sigma_raid_nonport p_raid_port sigma_raid_port p_raid_success p_conquest
//     collapse_s
//
// Output (binary, stdout):
//   n_particles * H * W * 6 unsigned shorts (uint16_t), counts per class.
//   Layout: particle_idx * (H*W*6) + y*W*6 + x*6 + class.

#include <cstdio>
#include <cmath>
#include <cstring>
#include <vector>
#include <algorithm>
#include <random>

static constexpr int OCEAN = 10, PLAINS = 11, FOREST = 4, MOUNTAIN = 5;
static constexpr int SETTLEMENT = 1, PORT = 2, RUIN = 3;
static constexpr int NUM_CLASSES = 6;

static int raw_to_class(int v) {
    switch (v) {
        case 0: case 10: case 11: return 0;
        case 1: return 1; case 2: return 2; case 3: return 3;
        case 4: return 4; case 5: return 5;
        default: return 0;
    }
}

struct Settlement {
    int x, y;
    double pop, food, wealth, defense;
    bool has_port, alive;
    int owner_id;
};

struct Params {
    double alpha_pop, alpha_def;
    double alpha_plains, alpha_forest, beta;
    double mu_spawn, s_spawn, sigma_dist, p_multi, hi_food_transfer, mu_f_tier;
    double port_thresh;
    double p_raid_nonport, sigma_raid_nonport, p_raid_port, sigma_raid_port;
    double p_raid_success, p_conquest;
    double collapse_s;
};

struct SettlePos { int x, y; bool has_port; };

struct State {
    int H, W;
    std::vector<std::vector<int>> grid;
    std::vector<Settlement> settlements;
    std::vector<std::vector<double>> n_ocean;
    int settle_idx_at[50][50];

    void init(int h, int w) {
        H = h; W = w;
        grid.assign(H, std::vector<int>(W, 0));
        n_ocean.assign(H, std::vector<double>(W, 0.0));
    }

    void compute_ocean() {
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                double cnt = 0;
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        if (dy == 0 && dx == 0) continue;
                        int ny = y + dy, nx = x + dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W && grid[ny][nx] == OCEAN)
                            cnt++;
                    }
                n_ocean[y][x] = cnt;
            }
    }

    void rebuild_lookup() {
        memset(settle_idx_at, -1, sizeof(settle_idx_at));
        for (int i = 0; i < (int)settlements.size(); i++)
            if (settlements[i].alive)
                settle_idx_at[settlements[i].y][settlements[i].x] = i;
    }

    void sync_grid() {
        for (auto& s : settlements) {
            if (s.alive)
                grid[s.y][s.x] = s.has_port ? PORT : SETTLEMENT;
            else if (grid[s.y][s.x] == SETTLEMENT || grid[s.y][s.x] == PORT)
                grid[s.y][s.x] = RUIN;
        }
        rebuild_lookup();
    }
};

static inline double logistic(double x, double mu, double s) {
    double z = std::max(-20.0, std::min(20.0, (x - mu) / s));
    return 1.0 / (1.0 + std::exp(-z));
}

static void step_growth(State& st, const Params& p) {
    for (auto& s : st.settlements) {
        if (!s.alive) continue;
        s.pop += p.alpha_pop * s.pop;
        s.defense = std::min(s.defense + p.alpha_def * s.defense, 1.0);
    }
}

static void step_spawning(State& st, const Params& p, std::mt19937& rng) {
    std::uniform_real_distribution<double> U(0.0, 1.0);
    std::normal_distribution<double> half_norm(0.0, p.sigma_dist);
    int n_parents = (int)st.settlements.size();
    int next_owner = 0;
    for (auto& s : st.settlements) next_owner = std::max(next_owner, s.owner_id + 1);

    for (int pi = 0; pi < n_parents; pi++) {
        auto& parent = st.settlements[pi];
        if (!parent.alive) continue;
        bool has_nearby = false;
        for (int j = 0; j < n_parents; j++) {
            if (j == pi || !st.settlements[j].alive) continue;
            if (st.settlements[j].owner_id != parent.owner_id) continue;
            if (std::max(std::abs(st.settlements[j].x - parent.x),
                         std::abs(st.settlements[j].y - parent.y)) <= 6) {
                has_nearby = true; break;
            }
        }
        if (has_nearby) continue;
        if (U(rng) > logistic(parent.pop, p.mu_spawn, p.s_spawn)) continue;

        // Determine if parent is eligible for hi-tier spawning
        // Hi-tier requires pop > mu_p_tier (~1.39) AND food > mu_f_tier
        bool hi_eligible = (parent.pop > 1.39 && parent.food > p.mu_f_tier);

        while (true) {
            bool placed = false;
            for (int attempt = 0; attempt < 20; attempt++) {
                int d = std::max(1, (int)std::round(std::abs(half_norm(rng))));
                if (d > 10) continue;
                struct Cand { int x, y, val; };
                std::vector<Cand> cands;
                for (int dy = -d; dy <= d; dy++)
                    for (int dx = -d; dx <= d; dx++) {
                        if (std::abs(dx) + std::abs(dy) != d) continue;
                        int nx = parent.x + dx, ny = parent.y + dy;
                        if (nx < 0 || nx >= st.W || ny < 0 || ny >= st.H) continue;
                        int v = st.grid[ny][nx];
                        if (hi_eligible) {
                            // Hi-tier: can spawn on any buildable tile
                            if (v == PLAINS || v == FOREST || v == RUIN)
                                cands.push_back({nx, ny, v});
                        } else {
                            // Lo-tier: can only spawn on ruins
                            if (v == RUIN)
                                cands.push_back({nx, ny, v});
                        }
                    }
                if (cands.empty()) continue;
                // Weight selection: ruins 8x more likely for hi-tier parents
                std::vector<double> w(cands.size());
                double tot = 0;
                for (int i = 0; i < (int)cands.size(); i++) {
                    w[i] = (hi_eligible && cands[i].val == RUIN) ? 8.0 : 1.0;
                    tot += w[i];
                }
                double r = U(rng) * tot, cum = 0;
                int idx = 0;
                for (int i = 0; i < (int)cands.size(); i++) {
                    cum += w[i]; if (r < cum) { idx = i; break; }
                }
                auto& c = cands[idx];
                Settlement child;
                child.x = c.x; child.y = c.y; child.has_port = false; child.alive = true;
                child.owner_id = parent.owner_id;
                if (c.val == RUIN || !hi_eligible) {
                    // Lo-tier child
                    child.pop = 0.4; child.defense = 0.15; child.food = 0.148;
                    child.wealth = parent.wealth * 0.098;
                } else {
                    // Hi-tier child
                    child.pop = 0.5; child.defense = 0.2;
                    child.food = 0.148 + std::max(0.0, p.hi_food_transfer);
                    child.wealth = parent.wealth * 0.217;
                    parent.pop -= 0.10; parent.food -= 0.22;
                }
                st.grid[c.y][c.x] = SETTLEMENT;
                st.settle_idx_at[c.y][c.x] = (int)st.settlements.size();
                st.settlements.push_back(child);
                placed = true; break;
            }
            if (!placed || U(rng) > p.p_multi) break;
        }
    }
}

static void step_food_production(State& st, const Params& p) {
    for (int y = 0; y < st.H; y++)
        for (int x = 0; x < st.W; x++) {
            int v = st.grid[y][x];
            double alpha = (v == PLAINS) ? p.alpha_plains : (v == FOREST) ? p.alpha_forest : -1;
            if (alpha < 0) continue;
            int adj[8], nadj = 0;
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    if (dy == 0 && dx == 0) continue;
                    int ny = y + dy, nx = x + dx;
                    if (ny >= 0 && ny < st.H && nx >= 0 && nx < st.W) {
                        int si = st.settle_idx_at[ny][nx];
                        if (si >= 0 && st.settlements[si].alive) adj[nadj++] = si;
                    }
                }
            if (nadj == 0) continue;
            double share = alpha / nadj;
            for (int i = 0; i < nadj; i++) st.settlements[adj[i]].food += share;
        }
}

static void step_port_formation(State& st, const Params& p, std::mt19937& rng) {
    std::uniform_real_distribution<double> U(0.0, 1.0);
    for (auto& s : st.settlements) {
        if (!s.alive || s.has_port) continue;
        if (st.n_ocean[s.y][s.x] < 2 || s.food < p.port_thresh) continue;
        if (U(rng) < 0.104) { s.has_port = true; s.wealth += 0.005; }
    }
}

static void step_raiding(State& st, const Params& p, std::mt19937& rng) {
    std::uniform_real_distribution<double> U(0.0, 1.0);
    int n = (int)st.settlements.size();
    for (int vi = 0; vi < n; vi++) {
        auto& victim = st.settlements[vi];
        if (!victim.alive) continue;
        for (int ri = 0; ri < n; ri++) {
            auto& raider = st.settlements[ri];
            if (!raider.alive || raider.owner_id == victim.owner_id) continue;
            int d = std::abs(raider.x - victim.x) + std::abs(raider.y - victim.y);
            if (d > 10) continue;
            double sigma = raider.has_port ? p.sigma_raid_port : p.sigma_raid_nonport;
            double pr = raider.has_port ? p.p_raid_port : p.p_raid_nonport;
            if (U(rng) > pr * std::exp(-(double)(d*d)/(2.0*sigma*sigma))) continue;
            victim.defense -= 0.20 * victim.defense;
            victim.pop -= 0.15 * victim.pop;
            victim.food -= 0.10 * victim.food;
            if (U(rng) < p.p_raid_success) {
                double stolen = 0.40 * victim.wealth;
                victim.wealth -= stolen; raider.wealth += 0.57 * stolen;
            } else if (U(rng) < 0.174) {
                raider.wealth -= 0.20 * raider.wealth;
            }
            if (U(rng) < p.p_conquest) victim.owner_id = raider.owner_id;
        }
    }
}

static void step_food_consumption(State& st, const Params& p) {
    for (auto& s : st.settlements) {
        if (!s.alive) continue;
        s.food -= p.beta * s.pop;
    }
}

static void step_collapse(State& st, const Params& p, std::mt19937& rng) {
    std::uniform_real_distribution<double> U(0.0, 1.0);
    for (auto& s : st.settlements) {
        if (!s.alive) continue;
        if (s.food < 0) { s.alive = false; continue; }
        double z = std::max(-20.0, std::min(20.0, -s.defense / p.collapse_s));
        if (U(rng) < 1.0 / (1.0 + std::exp(-z))) s.alive = false;
    }
}

static void step_ruin_transitions(State& st, std::mt19937& rng) {
    std::uniform_real_distribution<double> U(0.0, 1.0);
    for (int y = 0; y < st.H; y++)
        for (int x = 0; x < st.W; x++) {
            if (st.grid[y][x] != RUIN) continue;
            st.grid[y][x] = (U(rng) < 0.324) ? FOREST : PLAINS;
        }
}

static void step_rare_terrain(State& st, std::mt19937& rng) {
    std::uniform_real_distribution<double> U(0.0, 1.0);
    for (int y = 0; y < st.H; y++)
        for (int x = 0; x < st.W; x++) {
            int v = st.grid[y][x];
            if (v == PLAINS && U(rng) < 0.0004) st.grid[y][x] = RUIN;
            else if (v == FOREST && U(rng) < 0.0005) st.grid[y][x] = RUIN;
        }
}

static void evolve(State& st, const Params& p, std::mt19937& rng) {
    step_growth(st, p);
    step_spawning(st, p, rng);
    step_food_production(st, p);
    step_port_formation(st, p, rng);
    step_raiding(st, p, rng);
    step_food_consumption(st, p);
    step_collapse(st, p, rng);
    st.sync_grid();
    step_ruin_transitions(st, rng);
    step_rare_terrain(st, rng);
}

int main() {
    int H, W, n_settle, n_particles, n_steps, rng_offset, n_runs;
    scanf("%d %d %d %d %d %d %d", &H, &W, &n_settle, &n_particles, &n_steps, &rng_offset, &n_runs);

    // Read grid
    std::vector<std::vector<int>> base_grid(H, std::vector<int>(W));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
            scanf("%d", &base_grid[y][x]);

    // Precompute ocean neighbors
    std::vector<std::vector<double>> base_n_ocean(H, std::vector<double>(W, 0.0));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            double cnt = 0;
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    if (dy == 0 && dx == 0) continue;
                    int ny = y + dy, nx = x + dx;
                    if (ny >= 0 && ny < H && nx >= 0 && nx < W && base_grid[ny][nx] == OCEAN)
                        cnt++;
                }
            base_n_ocean[y][x] = cnt;
        }

    // Read settlement positions
    std::vector<SettlePos> positions(n_settle);
    for (int i = 0; i < n_settle; i++) {
        int hp;
        scanf("%d %d %d", &positions[i].x, &positions[i].y, &hp);
        positions[i].has_port = hp;
    }

    // Output buffer: per-particle H*W*6 counts (uint16)
    int cells = H * W * NUM_CLASSES;
    std::vector<uint16_t> output(n_particles * cells, 0);

    for (int pi = 0; pi < n_particles; pi++) {
        // Read settlement stats for this particle
        std::vector<double> init_pop(n_settle), init_food(n_settle),
                            init_wealth(n_settle), init_def(n_settle);
        for (int i = 0; i < n_settle; i++)
            scanf("%lf %lf %lf %lf", &init_pop[i], &init_food[i], &init_wealth[i], &init_def[i]);

        // Read params
        Params p;
        scanf("%lf %lf %lf %lf %lf", &p.alpha_pop, &p.alpha_def, &p.alpha_plains, &p.alpha_forest, &p.beta);
        scanf("%lf %lf %lf %lf %lf %lf", &p.mu_spawn, &p.s_spawn, &p.sigma_dist, &p.p_multi, &p.hi_food_transfer, &p.mu_f_tier);
        scanf("%lf", &p.port_thresh);
        scanf("%lf %lf %lf %lf %lf %lf", &p.p_raid_nonport, &p.sigma_raid_nonport, &p.p_raid_port, &p.sigma_raid_port, &p.p_raid_success, &p.p_conquest);
        scanf("%lf", &p.collapse_s);

        uint16_t* counts = &output[pi * cells];

        // Run K simulations with this particle's params
        for (int run = 0; run < n_runs; run++) {
            State st;
            st.H = H; st.W = W;
            st.grid = base_grid;
            st.n_ocean = base_n_ocean;
            st.settlements.resize(n_settle);
            for (int i = 0; i < n_settle; i++) {
                auto& s = st.settlements[i];
                s.x = positions[i].x; s.y = positions[i].y;
                s.has_port = positions[i].has_port; s.alive = true;
                s.owner_id = i;
                s.pop = init_pop[i]; s.food = init_food[i];
                s.wealth = init_wealth[i]; s.defense = init_def[i];
            }
            for (auto& s : st.settlements)
                if (s.alive)
                    st.grid[s.y][s.x] = s.has_port ? PORT : SETTLEMENT;
            st.rebuild_lookup();

            std::mt19937 rng(pi * 104729 + run * 7919 + rng_offset);
            for (int step = 0; step < n_steps; step++)
                evolve(st, p, rng);

            // Accumulate counts
            for (int y = 0; y < H; y++)
                for (int x = 0; x < W; x++)
                    counts[(y * W + x) * NUM_CLASSES + raw_to_class(st.grid[y][x])]++;
        }
    }

    // Write all output at once (binary, uint16)
    fwrite(output.data(), sizeof(uint16_t), output.size(), stdout);
    return 0;
}
