/*
 * Astar Island — one-step simulator
 *
 * Protocol (line-delimited JSON on stdin/stdout):
 *   Input:  one JSON object per line — current frame state
 *   Output: one JSON object per line — state after one step
 *
 * Input JSON fields:
 *   grid        H×W raw cell values
 *   settlements [{x,y,population,food,wealth,defense,has_port,alive,owner_id},...]
 *   width, height
 *   params      (optional) round-specific hidden parameters
 *
 * Grid cell values: 0=Empty  1=Settlement  2=Port  3=Ruin  4=Forest  5=Mountain
 *                   10=Ocean  11=Plains
 *
 * Step order:
 *   1. Ruin transitions   (ruins → settlement/plains/forest/port)
 *   2. Food production    (plains/forest tiles feed adjacent settlements)
 *   3. Population growth  (dpop = pop_growth * pop)
 *   4. Defense growth     (ddef = def_growth * def)
 *   5. Food consumption   (food -= beta * pop)
 *   6. Port formation     (settlement → port if food ≥ thresh and coastal)
 *   7. Spawning           (high-pop settlements found children)
 *   8. Raiding            (wealth/pop/def damage, possible conquest)
 *   9. Collapse           (starvation or low defense → ruin)
 */

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <random>
#include <string>
#include <unordered_map>
#include <vector>
#include "nlohmann/json.hpp"

using json = nlohmann::json;

// ── cell values ─────────────────────────────────────────────────────────────
static constexpr int EMPTY      = 0;
static constexpr int SETTLEMENT = 1;
static constexpr int PORT       = 2;
static constexpr int RUIN       = 3;
static constexpr int FOREST     = 4;
static constexpr int MOUNTAIN   = 5;
static constexpr int OCEAN      = 10;
static constexpr int PLAINS     = 11;

// ── RNG ─────────────────────────────────────────────────────────────────────
static std::mt19937 rng(std::random_device{}());
static std::uniform_real_distribution<float> U01(0.f, 1.f);
static inline float rand01() { return U01(rng); }

// ── Params (hidden per-round parameters + growth constants) ─────────────────
struct Params {
    // Food
    float alpha_plains     = 0.029f;  // food per adjacent plains tile
    float alpha_forest     = 0.021f;  // food per adjacent forest tile
    float beta             = 0.095f;  // food consumed per unit population per step

    // Growth
    float pop_growth  = 0.065f;   // dpop = pop_growth * pop
    float def_growth  = 0.067f;   // ddef = def_growth * def

    // Spawning (logistic in population)
    float mu_spawn    = 2.184f;   // population at 50% spawn probability
    float s_spawn     = 0.432f;   // logistic steepness
    float lambda      = 1.056f;   // exponential distance decay
    float p_multi     = 0.076f;   // probability of spawning a second child, etc.
    float hi_food_transfer = 0.092f; // extra food given to hi-tier child

    // Port formation
    float port_thresh = 0.454f;   // food threshold; above → ~10.4% port chance

    // Raiding
    float p_raid      = 0.126f;   // base raid probability per step
    float sigma_raid  = 1.67f;    // Gaussian range for non-port raiders
    float sigma_port  = 2.52f;    // Gaussian range for port raiders
};

static Params read_params(const json& j) {
    Params p;
    if (!j.contains("params")) return p;
    const auto& pj = j["params"];
    auto get = [&](const char* k, float& v) {
        if (pj.contains(k)) v = pj[k].get<float>();
    };
    get("alpha_plains",     p.alpha_plains);
    get("alpha_forest",     p.alpha_forest);
    get("beta",             p.beta);
    get("pop_growth",       p.pop_growth);
    get("def_growth",       p.def_growth);
    get("mu_spawn",         p.mu_spawn);
    get("s_spawn",          p.s_spawn);
    get("lambda",           p.lambda);
    get("p_multi",          p.p_multi);
    get("hi_food_transfer", p.hi_food_transfer);
    get("port_thresh",      p.port_thresh);
    get("p_raid",           p.p_raid);
    get("sigma_raid",       p.sigma_raid);
    get("sigma_port",       p.sigma_port);
    return p;
}

// ── Settlement ───────────────────────────────────────────────────────────────
struct Settlement {
    int   x, y;
    float population;
    float food;
    float wealth;
    float defense;
    bool  has_port;
    bool  alive;
    int   owner_id;
};

// ── World ────────────────────────────────────────────────────────────────────
struct World {
    int W, H;
    std::vector<std::vector<int>> grid;  // [y][x]
    std::vector<Settlement> settlements;

    int  cell(int x, int y) const { return grid[y][x]; }
    void set (int x, int y, int v) { grid[y][x] = v; }
    bool inbounds(int x, int y) const { return x>=0 && x<W && y>=0 && y<H; }

    int count_neighbors(int cx, int cy, int val) const {
        int n = 0;
        for (int dy=-1; dy<=1; dy++)
        for (int dx=-1; dx<=1; dx++) {
            if (!dx && !dy) continue;
            int nx=cx+dx, ny=cy+dy;
            if (inbounds(nx,ny) && grid[ny][nx]==val) n++;
        }
        return n;
    }

    bool is_static(int x, int y) const {
        int v = cell(x,y);
        return v==OCEAN || v==MOUNTAIN;
    }
};

// ── Helpers ──────────────────────────────────────────────────────────────────
static float sigmoid(float x) { return 1.f / (1.f + std::exp(-x)); }

// Chebyshev distance
static int cheby(int ax, int ay, int bx, int by) {
    return std::max(std::abs(ax-bx), std::abs(ay-by));
}

// ── Step ─────────────────────────────────────────────────────────────────────
World step(const World& w, const Params& p) {
    World next = w;
    int H = w.H, W = w.W;

    // Build position → settlement index map for quick lookup
    std::unordered_map<int,int> pos_to_idx;
    auto encode = [&](int x, int y){ return y*W + x; };
    for (int i = 0; i < (int)w.settlements.size(); i++) {
        const auto& s = w.settlements[i];
        if (s.alive) pos_to_idx[encode(s.x, s.y)] = i;
    }

    // ── 1. Ruin transitions ──────────────────────────────────────────────────
    // Ruins always resolve in the very next step (never persist).
    // Rates: ~48% settlement, ~33% plains, ~18% forest, ~1% port (coastal only)
    for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
        if (w.cell(x,y) != RUIN) continue;
        int n_ocean = w.count_neighbors(x, y, OCEAN);
        float r = rand01();
        float p_port   = (n_ocean >= 2) ? 0.010f : 0.0f;
        float p_settl  = 0.480f;
        float p_plains = 0.330f;
        float p_forest = 0.180f;
        float cum = 0;
        if (r < (cum += p_port))                        next.set(x,y, PORT);
        else if (r < (cum += p_settl))                  next.set(x,y, SETTLEMENT);
        else if (r < (cum += p_plains))                 next.set(x,y, PLAINS);
        else if (r < (cum += p_forest))                 next.set(x,y, FOREST);
        // else stays ruin (rare remainder)

        // If rebuilt to settlement/port, create a lo-tier settlement entry
        int nv = next.cell(x,y);
        if (nv == SETTLEMENT || nv == PORT) {
            // Find nearest alive settlement to inherit owner_id and donate wealth
            int best_owner = 0;
            float best_dist = 1e9f;
            float best_wealth = 0;
            for (const auto& s : w.settlements) {
                if (!s.alive) continue;
                float d = (float)cheby(x,y,s.x,s.y);
                if (d < best_dist) { best_dist=d; best_owner=s.owner_id; best_wealth=s.wealth; }
            }
            Settlement child;
            child.x = x; child.y = y;
            child.population = 0.400f;
            child.defense    = 0.150f;
            child.food       = 0.148f;
            child.wealth     = best_wealth * 0.098f;  // lo-tier: 9.8% of patron wealth
            child.has_port   = (nv == PORT);
            child.alive      = true;
            child.owner_id   = best_owner;
            next.settlements.push_back(child);
            pos_to_idx[encode(x,y)] = (int)next.settlements.size()-1;
        }
    }

    // ── 2. Food production ───────────────────────────────────────────────────
    // Each plains/forest tile adjacent to ≥1 settlement produces food,
    // shared equally among all adjacent settlements.
    // Stochastic: each tile fires with ~50% probability (when fired gives 2×alpha).
    for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
        int v = w.cell(x,y);
        float alpha;
        if      (v == PLAINS) alpha = p.alpha_plains;
        else if (v == FOREST) alpha = p.alpha_forest;
        else continue;

        // Collect adjacent alive settlements
        std::vector<int> adj;
        for (int dy=-1; dy<=1; dy++)
        for (int dx=-1; dx<=1; dx++) {
            if (!dx && !dy) continue;
            int nx=x+dx, ny=y+dy;
            if (!w.inbounds(nx,ny)) continue;
            int cv = w.cell(nx,ny);
            if (cv==SETTLEMENT || cv==PORT) {
                auto it = pos_to_idx.find(encode(nx,ny));
                if (it != pos_to_idx.end()) adj.push_back(it->second);
            }
        }
        if (adj.empty()) continue;

        // Each tile fires independently (Bernoulli); when fired gives 2×alpha
        if (rand01() < 0.5f) continue;
        float share = 2.f * alpha / (float)adj.size();
        for (int idx : adj) next.settlements[idx].food += share;
    }

    // ── 3. Population growth ─────────────────────────────────────────────────
    for (auto& s : next.settlements) {
        if (!s.alive) continue;
        s.population *= (1.f + p.pop_growth);
    }

    // ── 4. Defense growth ────────────────────────────────────────────────────
    for (auto& s : next.settlements) {
        if (!s.alive) continue;
        s.defense = std::min(s.defense * (1.f + p.def_growth), 1.0f);
    }

    // ── 5. Food consumption ───────────────────────────────────────────────────
    for (auto& s : next.settlements) {
        if (!s.alive) continue;
        s.food -= p.beta * s.population;
        // food can go negative; collapse check is in step 9
    }

    // ── 6. Port formation ────────────────────────────────────────────────────
    // Settlement with ≥2 ocean neighbors + food ≥ thresh → 10.4% chance of port
    for (int i = 0; i < (int)next.settlements.size(); i++) {
        auto& s = next.settlements[i];
        if (!s.alive || s.has_port) continue;
        if (next.cell(s.x, s.y) != SETTLEMENT) continue;
        int n_ocean = w.count_neighbors(s.x, s.y, OCEAN);
        if (n_ocean < 2) continue;
        if (s.food < p.port_thresh) continue;
        if (rand01() < 0.104f) {
            next.set(s.x, s.y, PORT);
            s.has_port = true;
            s.wealth  += 0.005f;  // one-time wealth bonus
        }
    }

    // ── 7. Spawning ──────────────────────────────────────────────────────────
    // For each alive settlement, roll logistic spawn probability.
    // Children placed on tiles within Chebyshev distance, preferring ruins 8×.
    // Lo-tier (pop=0.4) on ruins; Hi-tier (pop=0.5) on plains/forest.

    // Collect occupied positions (to avoid double-spawning onto same tile)
    auto occupied = [&](int x, int y) -> bool {
        int v = next.cell(x,y);
        return v==SETTLEMENT || v==PORT || v==RUIN || v==MOUNTAIN || v==OCEAN;
    };

    int n_orig = (int)next.settlements.size();
    for (int i = 0; i < n_orig; i++) {
        auto& parent = next.settlements[i];
        if (!parent.alive) continue;

        float p_spawn = sigmoid((parent.population - p.mu_spawn) / p.s_spawn);
        if (rand01() >= p_spawn) continue;

        // Keep spawning (multi-spawn) until a roll fails
        bool first = true;
        while (true) {
            if (!first && rand01() >= p.p_multi) break;
            first = false;

            // Build weighted candidate tile list out to distance 5
            struct Cand { int x,y; float w; bool is_ruin; };
            std::vector<Cand> cands;
            float total_w = 0;
            for (int d = 1; d <= 5; d++) {
                float dist_w = std::exp(-p.lambda * (d - 1)) * (1.f - std::exp(-p.lambda));
                for (int dy = -d; dy <= d; dy++)
                for (int dx = -d; dx <= d; dx++) {
                    if (std::max(std::abs(dx),std::abs(dy)) != d) continue;
                    int tx = parent.x+dx, ty = parent.y+dy;
                    if (!next.inbounds(tx,ty)) continue;
                    int tv = next.cell(tx,ty);
                    bool is_ruin  = (tv == RUIN);
                    bool is_fresh = (tv == PLAINS || tv == EMPTY || tv == FOREST);
                    if (!is_ruin && !is_fresh) continue;
                    float tile_w = dist_w * (is_ruin ? 8.f : 1.f);
                    cands.push_back({tx, ty, tile_w, is_ruin});
                    total_w += tile_w;
                }
            }
            if (cands.empty()) break;

            // Sample a tile
            float roll = rand01() * total_w;
            float cum  = 0;
            int chosen = (int)cands.size()-1;
            for (int k=0; k<(int)cands.size(); k++) {
                cum += cands[k].w;
                if (roll <= cum) { chosen=k; break; }
            }
            auto& c = cands[chosen];
            if (occupied(c.x, c.y)) break; // tile taken since we started

            Settlement child;
            child.x = c.x; child.y = c.y;
            child.alive    = true;
            child.owner_id = parent.owner_id;

            if (c.is_ruin) {
                // Lo-tier: spawns on ruin, costs parent nothing in population
                child.population = 0.400f;
                child.defense    = 0.150f;
                child.food       = 0.148f;
                child.wealth     = parent.wealth * 0.098f;
                child.has_port   = false;
                next.set(c.x, c.y, SETTLEMENT);
            } else {
                // Hi-tier: spawns on fresh land, costs parent 0.10 pop + 0.22 food
                child.population  = 0.500f;
                child.defense     = 0.200f;
                child.food        = 0.148f + p.hi_food_transfer;
                child.wealth      = parent.wealth * 0.217f;
                child.has_port    = false;
                parent.population -= 0.10f;
                parent.food       -= 0.22f;
                next.set(c.x, c.y, SETTLEMENT);
            }
            next.settlements.push_back(child);
        }
    }

    // ── 8. Raiding ───────────────────────────────────────────────────────────
    // Each alive settlement may raid each enemy in Gaussian range.
    // P(raid from dist d) = p_raid × exp(-d² / (2σ²))
    // 60% success: victim loses ~40% wealth, raider gains ~23% of victim wealth.
    // 23% chance of conquest on successful raid.
    // Stat damage: ~15% pop, ~20% def, ~9% food.

    int n_now = (int)next.settlements.size();
    for (int i = 0; i < n_now; i++) {
        auto& raider = next.settlements[i];
        if (!raider.alive) continue;

        float sigma = raider.has_port ? p.sigma_port : p.sigma_raid;
        float sigma2 = 2.f * sigma * sigma;

        for (int j = 0; j < n_now; j++) {
            if (i == j) continue;
            auto& victim = next.settlements[j];
            if (!victim.alive) continue;
            if (raider.owner_id == victim.owner_id) continue;

            int dx = raider.x - victim.x, dy = raider.y - victim.y;
            float dist2 = (float)(dx*dx + dy*dy);
            float p_this_raid = p.p_raid * std::exp(-dist2 / sigma2);
            if (rand01() >= p_this_raid) continue;

            // Raid attempt
            if (rand01() < 0.605f) {
                // Success
                float stolen = victim.wealth * 0.401f;
                victim.wealth  -= stolen;
                raider.wealth  += stolen * 0.227f / 0.401f;  // raider gets 57% of what victim lost
                // Stat damage to victim
                victim.population *= 0.85f;
                victim.defense    *= 0.80f;
                victim.food       *= 0.91f;
                // Conquest
                if (rand01() < 0.230f) {
                    victim.owner_id = raider.owner_id;
                }
            } else {
                // Failed raid — 17% chance raider loses ~20% wealth
                if (rand01() < 0.174f) {
                    raider.wealth *= 0.80f;
                }
            }
        }
    }

    // ── 9. Collapse ──────────────────────────────────────────────────────────
    // Starvation: food < 0 (already consumed in step 5).
    // Defense: P(collapse) = sigmoid(-defense / collapse_s), collapse_s=0.158
    static constexpr float COLLAPSE_S = 0.158f;
    for (auto& s : next.settlements) {
        if (!s.alive) continue;
        bool collapse = false;
        if (s.food < 0.f) {
            collapse = true;  // starved
        } else {
            float p_coll = sigmoid(-s.defense / COLLAPSE_S);
            if (rand01() < p_coll) collapse = true;
        }
        if (collapse) {
            s.alive   = false;
            s.wealth  = 0.f;
            next.set(s.x, s.y, RUIN);
        }
    }

    // Sync has_port from grid for surviving settlements
    for (auto& s : next.settlements) {
        if (s.alive) s.has_port = (next.cell(s.x,s.y) == PORT);
    }

    // Remove dead settlements from the active list
    next.settlements.erase(
        std::remove_if(next.settlements.begin(), next.settlements.end(),
                       [](const Settlement& s){ return !s.alive; }),
        next.settlements.end());

    return next;
}

// ── JSON I/O ─────────────────────────────────────────────────────────────────
World from_json(const json& j) {
    World w;
    w.W = j["width"].get<int>();
    w.H = j["height"].get<int>();
    const auto& gj = j["grid"];
    w.grid.resize(w.H, std::vector<int>(w.W));
    for (int y=0; y<w.H; y++)
        for (int x=0; x<w.W; x++)
            w.grid[y][x] = gj[y][x].get<int>();
    for (const auto& sj : j["settlements"]) {
        Settlement s;
        s.x          = sj["x"].get<int>();
        s.y          = sj["y"].get<int>();
        s.population = sj.value("population", 1.0f);
        s.food       = sj.value("food",       0.5f);
        s.wealth     = sj.value("wealth",     0.5f);
        s.defense    = sj.value("defense",    0.5f);
        s.has_port   = sj.value("has_port",   false);
        s.alive      = sj.value("alive",      true);
        s.owner_id   = sj.value("owner_id",   0);
        w.settlements.push_back(s);
    }
    return w;
}

json to_json(const World& w) {
    json j;
    json gj = json::array();
    for (int y=0; y<w.H; y++) {
        json row = json::array();
        for (int x=0; x<w.W; x++) row.push_back(w.grid[y][x]);
        gj.push_back(row);
    }
    j["grid"] = gj;
    json sj = json::array();
    for (const auto& s : w.settlements) {
        json o;
        o["x"]=s.x; o["y"]=s.y;
        o["population"]=s.population; o["food"]=s.food;
        o["wealth"]=s.wealth; o["defense"]=s.defense;
        o["has_port"]=s.has_port; o["alive"]=s.alive;
        o["owner_id"]=s.owner_id;
        sj.push_back(o);
    }
    j["settlements"] = sj;
    return j;
}

// ── Main ──────────────────────────────────────────────────────────────────────
int main() {
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;
        try {
            auto  j = json::parse(line);
            Params p = read_params(j);
            World w  = from_json(j);
            World nx = step(w, p);
            std::puts(to_json(nx).dump().c_str());
            std::fflush(stdout);
        } catch (const std::exception& e) {
            fprintf(stderr, "sim error: %s\n", e.what());
            fprintf(stdout, "{\"error\":\"%s\"}\n", e.what());
            fflush(stdout);
        }
    }
}
