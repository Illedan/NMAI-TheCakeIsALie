// true_sim.cpp — Fast settlement-level Astar Island simulation.
// Reads initial state + params from stdin, runs N simulations, writes H*W*6 counts to stdout.
//
// Input format (text, from Python):
//   H W n_settlements n_simulations n_steps
//   grid[0][0] grid[0][1] ... grid[0][W-1]
//   ...
//   grid[H-1][0] ... grid[H-1][W-1]
//   x y population food wealth defense has_port alive owner_id   (per settlement)
//   ...
//   alpha_pop alpha_def alpha_plains alpha_forest beta
//   mu_spawn s_spawn sigma_dist p_multi hi_food_transfer mu_f_tier
//   port_thresh
//   p_raid_nonport sigma_raid_nonport p_raid_port sigma_raid_port p_raid_success p_conquest
//   collapse_s
//
// Output: H*W*6 integers (counts), one per line, in row-major order [y][x][c].

#include <cstdio>
#include <cmath>
#include <cstdlib>
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
        case 1: return 1;
        case 2: return 2;
        case 3: return 3;
        case 4: return 4;
        case 5: return 5;
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

struct State {
    int H, W;
    std::vector<std::vector<int>> grid;
    std::vector<Settlement> settlements;
    // Precomputed
    std::vector<std::vector<double>> n_ocean;

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

    // Fast settlement lookup by position
    int settle_idx_at[50][50];  // -1 if none; max grid 50x50

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

    void to_class_grid(std::vector<std::vector<int>>& cg) const {
        cg.assign(H, std::vector<int>(W));
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++)
                cg[y][x] = raw_to_class(grid[y][x]);
    }
};

static inline double logistic(double x, double mu, double s) {
    double z = (x - mu) / s;
    z = std::max(-20.0, std::min(20.0, z));
    return 1.0 / (1.0 + std::exp(-z));
}

// Phase 1: Growth
static void step_growth(State& st, const Params& p) {
    for (auto& s : st.settlements) {
        if (!s.alive) continue;
        s.pop += p.alpha_pop * s.pop;
        s.defense = std::min(s.defense + p.alpha_def * s.defense, 1.0);
    }
}

// Phase 2: Spawning
static void step_spawning(State& st, const Params& p, std::mt19937& rng) {
    std::uniform_real_distribution<double> U(0.0, 1.0);

    int n_parents = (int)st.settlements.size();
    int next_owner = 0;
    for (auto& s : st.settlements)
        next_owner = std::max(next_owner, s.owner_id + 1);

    for (int pi = 0; pi < n_parents; pi++) {
        auto& parent = st.settlements[pi];
        if (!parent.alive) continue;

        // Isolation check: no same-owner within Chebyshev 6
        bool has_nearby = false;
        for (int j = 0; j < n_parents; j++) {
            if (j == pi || !st.settlements[j].alive) continue;
            if (st.settlements[j].owner_id != parent.owner_id) continue;
            if (std::max(std::abs(st.settlements[j].x - parent.x),
                         std::abs(st.settlements[j].y - parent.y)) <= 6) {
                has_nearby = true;
                break;
            }
        }
        if (has_nearby) continue;

        double p_spawn = logistic(parent.pop, p.mu_spawn, p.s_spawn);
        if (U(rng) > p_spawn) continue;

        bool hi_eligible = (parent.pop > 1.39 && parent.food > p.mu_f_tier);

        // Spawn loop (multi-spawn)
        std::normal_distribution<double> half_norm(0.0, p.sigma_dist);
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
                            if (v == PLAINS || v == FOREST || v == RUIN)
                                cands.push_back({nx, ny, v});
                        } else {
                            if (v == RUIN)
                                cands.push_back({nx, ny, v});
                        }
                    }
                if (cands.empty()) continue;

                std::vector<double> weights(cands.size());
                double total = 0;
                for (int i = 0; i < (int)cands.size(); i++) {
                    weights[i] = (hi_eligible && cands[i].val == RUIN) ? 8.0 : 1.0;
                    total += weights[i];
                }
                double r = U(rng) * total;
                int idx = 0;
                double cum = 0;
                for (int i = 0; i < (int)cands.size(); i++) {
                    cum += weights[i];
                    if (r < cum) { idx = i; break; }
                }

                auto& c = cands[idx];
                Settlement child;
                child.x = c.x; child.y = c.y;
                child.has_port = false; child.alive = true;
                child.owner_id = parent.owner_id;

                if (c.val == RUIN || !hi_eligible) {
                    // Lo-tier
                    child.pop = 0.400; child.defense = 0.150;
                    child.food = 0.148;
                    child.wealth = parent.wealth * 0.098;
                } else {
                    // Hi-tier
                    child.pop = 0.500; child.defense = 0.200;
                    child.food = 0.148 + std::max(0.0, p.hi_food_transfer);
                    child.wealth = parent.wealth * 0.217;
                    parent.pop -= 0.10;
                    parent.food -= 0.22;
                }

                st.grid[c.y][c.x] = SETTLEMENT;
                st.settle_idx_at[c.y][c.x] = (int)st.settlements.size();
                st.settlements.push_back(child);
                placed = true;
                break;
            }

            if (!placed) break;
            if (U(rng) > p.p_multi) break;
        }
    }
}

// Phase 3: Food production
static void step_food_production(State& st, const Params& p) {
    for (int y = 0; y < st.H; y++)
        for (int x = 0; x < st.W; x++) {
            int v = st.grid[y][x];
            double alpha;
            if (v == PLAINS) alpha = p.alpha_plains;
            else if (v == FOREST) alpha = p.alpha_forest;
            else continue;

            // Count adjacent alive settlements
            int adj[8]; int nadj = 0;
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    if (dy == 0 && dx == 0) continue;
                    int ny = y + dy, nx = x + dx;
                    if (ny >= 0 && ny < st.H && nx >= 0 && nx < st.W) {
                        int si = st.settle_idx_at[ny][nx];
                        if (si >= 0 && st.settlements[si].alive)
                            adj[nadj++] = si;
                    }
                }
            if (nadj == 0) continue;
            double share = alpha / nadj;
            for (int i = 0; i < nadj; i++)
                st.settlements[adj[i]].food += share;
        }
}

// Phase 4: Port formation
static void step_port_formation(State& st, const Params& p, std::mt19937& rng) {
    std::uniform_real_distribution<double> U(0.0, 1.0);
    for (auto& s : st.settlements) {
        if (!s.alive || s.has_port) continue;
        if (st.n_ocean[s.y][s.x] < 2) continue;
        if (s.food < p.port_thresh) continue;
        if (U(rng) < 0.104) {
            s.has_port = true;
            s.wealth += 0.005;
        }
    }
}

// Phase 5: Raiding
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
            double prob = pr * std::exp(-(double)(d * d) / (2.0 * sigma * sigma));
            if (U(rng) > prob) continue;

            // Raid damage
            victim.defense -= 0.20 * victim.defense;
            victim.pop -= 0.15 * victim.pop;
            victim.food -= 0.10 * victim.food;

            if (U(rng) < p.p_raid_success) {
                double stolen = 0.40 * victim.wealth;
                victim.wealth -= stolen;
                raider.wealth += 0.57 * stolen;
            } else {
                if (U(rng) < 0.174)
                    raider.wealth -= 0.20 * raider.wealth;
            }

            if (U(rng) < p.p_conquest)
                victim.owner_id = raider.owner_id;
        }
    }
}

// Phase 6: Food consumption
static void step_food_consumption(State& st, const Params& p) {
    for (auto& s : st.settlements) {
        if (!s.alive) continue;
        s.food -= p.beta * s.pop;
    }
}

// Phase 7: Collapse
static void step_collapse(State& st, const Params& p, std::mt19937& rng) {
    std::uniform_real_distribution<double> U(0.0, 1.0);
    for (auto& s : st.settlements) {
        if (!s.alive) continue;
        if (s.food < 0) { s.alive = false; continue; }
        double z = -s.defense / p.collapse_s;
        z = std::max(-20.0, std::min(20.0, z));
        double pc = 1.0 / (1.0 + std::exp(-z));
        if (U(rng) < pc) s.alive = false;
    }
}

// Phase 8: Ruin transitions — all ruins decay every step (rebuilding is via spawning)
static void step_ruin_transitions(State& st, std::mt19937& rng) {
    std::uniform_real_distribution<double> U(0.0, 1.0);
    for (int y = 0; y < st.H; y++)
        for (int x = 0; x < st.W; x++) {
            if (st.grid[y][x] != RUIN) continue;
            st.grid[y][x] = (U(rng) < 0.324) ? FOREST : PLAINS;
        }
}

// Phase 9: Rare terrain
static void step_rare_terrain(State& st, std::mt19937& rng) {
    std::uniform_real_distribution<double> U(0.0, 1.0);
    for (int y = 0; y < st.H; y++)
        for (int x = 0; x < st.W; x++) {
            int v = st.grid[y][x];
            if (v == PLAINS && U(rng) < 0.0004)
                st.grid[y][x] = RUIN;
            else if (v == FOREST && U(rng) < 0.0005)
                st.grid[y][x] = RUIN;
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
    int H, W, n_settle, n_sims, n_steps;
    scanf("%d %d %d %d %d", &H, &W, &n_settle, &n_sims, &n_steps);

    // Read initial grid
    State init_state;
    init_state.init(H, W);
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
            scanf("%d", &init_state.grid[y][x]);
    init_state.compute_ocean();

    // Read settlements
    init_state.settlements.resize(n_settle);
    for (int i = 0; i < n_settle; i++) {
        auto& s = init_state.settlements[i];
        int hp, al;
        scanf("%d %d %lf %lf %lf %lf %d %d %d",
              &s.x, &s.y, &s.pop, &s.food, &s.wealth, &s.defense, &hp, &al, &s.owner_id);
        s.has_port = hp; s.alive = al;
    }
    init_state.rebuild_lookup();

    // Read params
    Params p;
    scanf("%lf %lf %lf %lf %lf", &p.alpha_pop, &p.alpha_def, &p.alpha_plains, &p.alpha_forest, &p.beta);
    scanf("%lf %lf %lf %lf %lf %lf", &p.mu_spawn, &p.s_spawn, &p.sigma_dist, &p.p_multi, &p.hi_food_transfer, &p.mu_f_tier);
    scanf("%lf", &p.port_thresh);
    scanf("%lf %lf %lf %lf %lf %lf", &p.p_raid_nonport, &p.sigma_raid_nonport, &p.p_raid_port, &p.sigma_raid_port, &p.p_raid_success, &p.p_conquest);
    scanf("%lf", &p.collapse_s);

    // Accumulate counts
    std::vector<int> counts(H * W * NUM_CLASSES, 0);

    for (int sim = 0; sim < n_sims; sim++) {
        // Deep copy initial state
        State st;
        st.init(H, W);
        st.grid = init_state.grid;
        st.n_ocean = init_state.n_ocean;
        st.settlements = init_state.settlements;
        st.rebuild_lookup();

        std::mt19937 rng(sim * 1000 + 7);

        for (int step = 0; step < n_steps; step++)
            evolve(st, p, rng);

        // Tally final class grid
        std::vector<std::vector<int>> cg;
        st.to_class_grid(cg);
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++)
                counts[(y * W + x) * NUM_CLASSES + cg[y][x]]++;
    }

    // Output counts
    for (int i = 0; i < H * W * NUM_CLASSES; i++)
        printf("%d\n", counts[i]);

    return 0;
}
