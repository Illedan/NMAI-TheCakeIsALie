#include "infra.hpp"
#include <cmath>
#include <cassert>
#include <fstream>
#include <sstream>
#include <iostream>
#include <algorithm>
#include <numeric>
#include <thread>
#include <filesystem>
#include <random>

// ----------------------------------------------------------------
// Terrain helpers
// ----------------------------------------------------------------

static int terrain_to_class(int t) {
    switch (t) {
        case 1:  return 1;  // Settlement
        case 2:  return 2;  // Port
        case 3:  return 3;  // Ruin
        case 4:  return 4;  // Forest
        case 5:  return 5;  // Mountain
        default: return 0;  // Empty, Ocean(10), Plains(11)
    }
}

static bool is_ocean(int t) { return t == 10; }

// ----------------------------------------------------------------
// Default params / bounds
// ----------------------------------------------------------------

std::vector<double> default_params() {
    std::vector<double> p(N_PARAMS);
    p[P_ES_BASE]     = 0.004;
    p[P_ES_NS]       = 0.35;
    p[P_ES_NS2]      = 0.0;
    p[P_ES_SR2]      = 0.12;
    p[P_ER_RATIO]    = 0.15;
    p[P_SR_BASE]     = 0.10;
    p[P_SR_SUP]      = 0.08;
    p[P_SR_NF_WT]    = 0.8;
    p[P_SR_SR2]      = 0.003;
    p[P_SR_RAID]     = 0.015;
    p[P_SR_RUIN]     = 0.03;
    p[P_SP_BASE]     = 0.104;
    p[P_SP_NS]       = -0.08;
    p[P_FS_BASE]     = 0.005;
    p[P_FS_NS]       = 0.45;
    p[P_FS_NS2]      = 0.0;
    p[P_FR_RATIO]    = 0.20;
    p[P_PR_BASE]     = 0.048;
    p[P_PR_NS]       = -0.04;
    p[P_RUIN_SETTLE] = 0.48;
    p[P_RUIN_EMPTY]  = 0.34;
    p[P_RUIN_FOREST] = 0.16;
    p[P_RUIN_NS]     = 0.05;
    p[P_DIST_DECAY]  = 0.0;
    p[P_ES_GATE]     = 0.0;
    return p;
}

std::vector<double> param_lo() {
    std::vector<double> p(N_PARAMS);
    p[P_ES_BASE]     = 0.0005; p[P_ES_NS]    = 0.01;  p[P_ES_NS2]  = 0.0;
    p[P_ES_SR2]      = 0.0;    p[P_ER_RATIO] = 0.01;
    p[P_SR_BASE]     = 0.003;  p[P_SR_SUP]   = 0.01;  p[P_SR_NF_WT]= 0.1;
    p[P_SR_SR2]      = 0.0;    p[P_SR_RAID]  = 0.0;   p[P_SR_RUIN] = 0.0;
    p[P_SP_BASE]     = 0.02;   p[P_SP_NS]    = -0.3;
    p[P_FS_BASE]     = 0.0005; p[P_FS_NS]    = 0.01;  p[P_FS_NS2]  = 0.0;
    p[P_FR_RATIO]    = 0.01;
    p[P_PR_BASE]     = 0.005;  p[P_PR_NS]    = -0.2;
    p[P_RUIN_SETTLE] = 0.1;    p[P_RUIN_EMPTY]= 0.1;  p[P_RUIN_FOREST]= 0.02;
    p[P_RUIN_NS]     = 0.0;    p[P_DIST_DECAY]= 0.0;  p[P_ES_GATE] = 0.0;
    return p;
}

std::vector<double> param_hi() {
    std::vector<double> p(N_PARAMS);
    p[P_ES_BASE]     = 0.15;  p[P_ES_NS]    = 1.5;   p[P_ES_NS2]  = 0.3;
    p[P_ES_SR2]      = 0.5;   p[P_ER_RATIO] = 0.5;
    p[P_SR_BASE]     = 0.25;  p[P_SR_SUP]   = 0.5;   p[P_SR_NF_WT]= 2.0;
    p[P_SR_SR2]      = 0.02;  p[P_SR_RAID]  = 0.06;  p[P_SR_RUIN] = 0.10;
    p[P_SP_BASE]     = 0.25;  p[P_SP_NS]    = 0.1;
    p[P_FS_BASE]     = 0.08;  p[P_FS_NS]    = 1.5;   p[P_FS_NS2]  = 0.3;
    p[P_FR_RATIO]    = 0.5;
    p[P_PR_BASE]     = 0.15;  p[P_PR_NS]    = 0.1;
    p[P_RUIN_SETTLE] = 0.8;   p[P_RUIN_EMPTY]= 0.7;  p[P_RUIN_FOREST]= 0.5;
    p[P_RUIN_NS]     = 0.2;   p[P_DIST_DECAY]= 0.3;  p[P_ES_GATE] = 5.0;
    return p;
}

// ----------------------------------------------------------------
// Transition probabilities (stateless, params passed explicitly)
// ----------------------------------------------------------------

static std::array<double, 6> transition(int cls, int ns, int nf, int nr, int sr2,
                                        bool ocean_adj,
                                        const std::vector<double>& p,
                                        int dist) {
    double dist_factor = (p[P_DIST_DECAY] > 0.001 && dist > 0)
                         ? std::exp(-p[P_DIST_DECAY] * dist) : 1.0;

    if (cls == 5) return {0,0,0,0,0,1};  // Mountain: static

    if (cls == 0) {  // Empty/Plains/Ocean-mapped
        double ps = p[P_ES_BASE] * std::exp(p[P_ES_NS]*ns + p[P_ES_NS2]*ns*ns + p[P_ES_SR2]*sr2);
        if (p[P_ES_GATE] > 0.01) ps *= 1.0 - std::exp(-p[P_ES_GATE]*ns);
        ps = std::min(ps * dist_factor, 0.50);
        double pr = ps * p[P_ER_RATIO];
        double pp = (ocean_adj && ns >= 1) ? 0.001 : 0.0;
        double pe = std::max(0.5, 1.0 - ps - pr - pp);
        double tot = pe + ps + pp + pr;
        return {pe/tot, ps/tot, pp/tot, pr/tot, 0, 0};
    }

    if (cls == 1) {  // Settlement
        double support = ns + p[P_SR_NF_WT]*nf;
        double pr = p[P_SR_BASE]*std::exp(-p[P_SR_SUP]*support)
                  + p[P_SR_RAID]*ns + p[P_SR_RUIN]*nr + p[P_SR_SR2]*sr2;
        pr = std::max(0.002, std::min(0.30, pr));
        double pp = ocean_adj ? std::max(0.001, p[P_SP_BASE] + p[P_SP_NS]*ns) : 0.0;
        pp = std::min(pp, 0.20);
        double ps = std::max(0.4, 1.0 - pr - pp);
        double tot = ps + pr + pp;
        return {0, ps/tot, pp/tot, pr/tot, 0, 0};
    }

    if (cls == 2) {  // Port
        double pr = std::max(0.01, std::min(0.20, p[P_PR_BASE] + p[P_PR_NS]*ns));
        return {0, 0, 1.0-pr, pr, 0, 0};
    }

    if (cls == 3) {  // Ruin
        double ps = std::max(0.05, p[P_RUIN_SETTLE] + p[P_RUIN_NS]*ns);
        double pe = std::max(0.05, p[P_RUIN_EMPTY]  - p[P_RUIN_NS]*ns*0.5);
        double pf = std::max(0.02, p[P_RUIN_FOREST]);
        double pp = ocean_adj ? 0.015 : 0.0;
        double tot = ps + pe + pf + pp;
        return {pe/tot, ps/tot, pp/tot, 0, pf/tot, 0};
    }

    if (cls == 4) {  // Forest
        double ps = p[P_FS_BASE] * std::exp(p[P_FS_NS]*ns + p[P_FS_NS2]*ns*ns);
        ps = std::min(ps * dist_factor, 0.45);
        double pr = ps * p[P_FR_RATIO];
        double pf = std::max(0.5, 1.0 - ps - pr);
        double tot = pf + ps + pr;
        return {0, ps/tot, 0, pr/tot, pf/tot, 0};
    }

    return {1,0,0,0,0,0};
}

// ----------------------------------------------------------------
// Single simulation run (returns final grid as class indices)
// ----------------------------------------------------------------

static std::vector<std::vector<int>> simulate_once(
    const Grid& initial_grid,
    const std::vector<double>& params,
    const std::vector<std::vector<int>>& bfs_dist,  // BFS distance from initial settlements
    std::mt19937& rng)
{
    int H = (int)initial_grid.size();
    int W = (int)initial_grid[0].size();

    // Precompute static per-cell properties
    std::vector<std::vector<bool>> ocean_adj(H, std::vector<bool>(W, false));
    std::vector<std::vector<bool>> cell_ocean(H, std::vector<bool>(W, false));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            cell_ocean[y][x] = is_ocean(initial_grid[y][x]);
            if (!cell_ocean[y][x])
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        int ny = y+dy, nx = x+dx;
                        if (ny>=0&&ny<H&&nx>=0&&nx<W && is_ocean(initial_grid[ny][nx]))
                            ocean_adj[y][x] = true;
                    }
        }

    // Working grid (class indices)
    std::vector<std::vector<int>> grid(H, std::vector<int>(W));
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
            grid[y][x] = terrain_to_class(initial_grid[y][x]);

    std::uniform_real_distribution<double> uni(0.0, 1.0);
    std::vector<std::vector<int>> next(H, std::vector<int>(W));

    for (int year = 0; year < 50; year++) {
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                if (cell_ocean[y][x]) { next[y][x] = grid[y][x]; continue; }
                if (grid[y][x] == 5)  { next[y][x] = 5; continue; }

                int ns = 0, nf = 0, nr = 0, sr2 = 0;
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        if (!dy && !dx) continue;
                        int ny=y+dy, nx=x+dx;
                        if (ny<0||ny>=H||nx<0||nx>=W) continue;
                        int c = grid[ny][nx];
                        if (c==1||c==2) ns++;
                        else if (c==4) nf++;
                        else if (c==3) nr++;
                    }
                for (int dy = -2; dy <= 2; dy++)
                    for (int dx = -2; dx <= 2; dx++) {
                        if (std::abs(dy)<=1 && std::abs(dx)<=1) continue;
                        int ny=y+dy, nx=x+dx;
                        if (ny<0||ny>=H||nx<0||nx>=W) continue;
                        int c = grid[ny][nx];
                        if (c==1||c==2) sr2++;
                    }

                auto probs = transition(grid[y][x], ns, nf, nr, sr2,
                                        ocean_adj[y][x], params, bfs_dist[y][x]);
                double r = uni(rng), cum = 0;
                int sampled = 0;
                for (int c = 0; c < 6; c++) {
                    cum += probs[c];
                    if (r <= cum) { sampled = c; break; }
                }
                next[y][x] = sampled;
            }
        }
        std::swap(grid, next);
    }
    return grid;
}

// ----------------------------------------------------------------
// BFS distance precomputation
// ----------------------------------------------------------------

static std::vector<std::vector<int>> compute_bfs_dist(const Grid& initial_grid) {
    int H = (int)initial_grid.size(), W = (int)initial_grid[0].size();
    std::vector<std::vector<int>> dist(H, std::vector<int>(W, 9999));
    std::vector<std::pair<int,int>> q;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int c = terrain_to_class(initial_grid[y][x]);
            if (c==1||c==2||c==3) { dist[y][x]=0; q.push_back({y,x}); }
        }
    for (size_t i = 0; i < q.size(); i++) {
        auto [cy,cx] = q[i];
        for (int dy=-1; dy<=1; dy++) for (int dx=-1; dx<=1; dx++) {
            if (!dy&&!dx) continue;
            int ny=cy+dy, nx=cx+dx;
            if (ny<0||ny>=H||nx<0||nx>=W) continue;
            if (dist[ny][nx] > dist[cy][cx]+1) {
                dist[ny][nx] = dist[cy][cx]+1;
                q.push_back({ny,nx});
            }
        }
    }
    return dist;
}

// ----------------------------------------------------------------
// run_mc — threaded Monte Carlo
// ----------------------------------------------------------------

ProbGrid run_mc(const std::vector<double>& params,
                const Grid& initial_grid,
                int n_sims,
                uint32_t seed)
{
    int H = (int)initial_grid.size();
    int W = (int)initial_grid[0].size();
    auto bfs = compute_bfs_dist(initial_grid);

    int n_threads = std::max(1, (int)std::thread::hardware_concurrency());
    n_threads = std::min(n_threads, n_sims);

    using CountGrid = std::vector<std::vector<std::array<int,6>>>;
    std::vector<CountGrid> counts(n_threads,
        CountGrid(H, std::vector<std::array<int,6>>(W, {0,0,0,0,0,0})));

    std::mt19937 seeder(seed);
    std::vector<uint32_t> seeds(n_threads);
    for (auto& s : seeds) s = seeder();

    std::vector<std::thread> threads;
    int done = 0;
    for (int t = 0; t < n_threads; t++) {
        int my = (n_sims - done) / (n_threads - t);
        done += my;
        threads.emplace_back([&, t, my]() {
            std::mt19937 rng(seeds[t]);
            for (int s = 0; s < my; s++) {
                auto g = simulate_once(initial_grid, params, bfs, rng);
                for (int y = 0; y < H; y++)
                    for (int x = 0; x < W; x++)
                        counts[t][y][x][g[y][x]]++;
            }
        });
    }
    for (auto& th : threads) th.join();

    ProbGrid out(H, std::vector<std::array<double,6>>(W, {0,0,0,0,0,0}));
    double inv = 1.0 / n_sims;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
            for (int t = 0; t < n_threads; t++)
                for (int c = 0; c < 6; c++)
                    out[y][x][c] += counts[t][y][x][c] * inv;
    return out;
}

// ----------------------------------------------------------------
// Minimal JSON parsing helpers
// ----------------------------------------------------------------

static size_t skip_ws(const std::string& s, size_t i) {
    while (i < s.size() && (s[i]==' '||s[i]=='\t'||s[i]=='\n'||s[i]=='\r')) i++;
    return i;
}

static double parse_num(const std::string& s, size_t& i) {
    size_t start = i;
    if (s[i]=='-') i++;
    while (i<s.size() && (isdigit(s[i])||s[i]=='.'||s[i]=='e'||s[i]=='E')) {
        if (i>start && (s[i]=='+'||s[i]=='-') && s[i-1]!='e' && s[i-1]!='E') break;
        i++;
    }
    return std::stod(s.substr(start, i-start));
}

static std::string parse_str(const std::string& s, size_t& i) {
    assert(s[i]=='"'); i++;
    std::string r;
    while (i<s.size()&&s[i]!='"') { if(s[i]=='\\') i++; r+=s[i++]; }
    i++; return r;
}

static void skip_val(const std::string& s, size_t& i);
static void skip_val(const std::string& s, size_t& i) {
    i = skip_ws(s, i);
    if (s[i]=='"') { parse_str(s,i); return; }
    if (s[i]=='['||s[i]=='{') {
        char open=s[i], close=(open=='['?']':'}');
        i++; int d=1;
        while (i<s.size()&&d>0) {
            if (s[i]==open) d++;
            else if (s[i]==close) d--;
            else if (s[i]=='"') { parse_str(s,i); continue; }
            i++;
        }
        return;
    }
    while (i<s.size()&&s[i]!=','&&s[i]!='}'&&s[i]!=']'&&s[i]!=' '&&s[i]!='\n') i++;
}

static Grid parse_grid_2d(const std::string& s, size_t& i) {
    Grid g;
    i=skip_ws(s,i); assert(s[i]=='['); i++;
    while (true) {
        i=skip_ws(s,i);
        if (s[i]==']') { i++; break; }
        if (s[i]==',') { i++; continue; }
        assert(s[i]=='['); i++;
        std::vector<int> row;
        while (true) {
            i=skip_ws(s,i);
            if (s[i]==']') { i++; break; }
            if (s[i]==',') { i++; continue; }
            row.push_back((int)parse_num(s,i));
        }
        g.push_back(std::move(row));
    }
    return g;
}

static ProbGrid parse_prob_3d(const std::string& s, size_t& i) {
    ProbGrid g;
    i=skip_ws(s,i); assert(s[i]=='['); i++;
    while (true) {
        i=skip_ws(s,i);
        if (s[i]==']') { i++; break; }
        if (s[i]==',') { i++; continue; }
        assert(s[i]=='['); i++;
        std::vector<std::array<double,6>> row;
        while (true) {
            i=skip_ws(s,i);
            if (s[i]==']') { i++; break; }
            if (s[i]==',') { i++; continue; }
            assert(s[i]=='['); i++;
            std::array<double,6> cell{};
            int ci=0;
            while (true) {
                i=skip_ws(s,i);
                if (s[i]==']') { i++; break; }
                if (s[i]==',') { i++; continue; }
                if (ci<6) cell[ci++] = parse_num(s,i); else skip_val(s,i);
            }
            row.push_back(cell);
        }
        g.push_back(std::move(row));
    }
    return g;
}

static std::string read_file(const std::string& path) {
    std::ifstream f(path);
    if (!f) { std::cerr << "cannot open " << path << "\n"; return ""; }
    std::ostringstream ss; ss << f.rdbuf(); return ss.str();
}

// Find value after a JSON key in a flat object (not nested-aware, but works
// for top-level keys)
static size_t find_key(const std::string& s, const std::string& key) {
    std::string needle = "\"" + key + "\"";
    size_t p = s.find(needle);
    if (p==std::string::npos) return p;
    p = s.find(':', p + needle.size());
    return p+1;
}

// ----------------------------------------------------------------
// Data loading
// ----------------------------------------------------------------

Grid load_initial_grid(const std::string& json_path) {
    auto s = read_file(json_path);
    size_t i = find_key(s, "grid");
    assert(i != std::string::npos);
    return parse_grid_2d(s, i);
}

std::vector<Grid> load_replay_finals(const std::string& replays_dir,
                                     const std::string& round_id,
                                     int seed_index)
{
    std::string seed_tag = "seed_" + std::to_string(seed_index);
    std::vector<Grid> finals;

    for (auto& entry : std::filesystem::directory_iterator(replays_dir)) {
        std::string name = entry.path().filename().string();
        if (name.find(round_id) == std::string::npos) continue;
        if (name.find(seed_tag) == std::string::npos) continue;
        if (name.substr(name.size()-5) != ".json") continue;

        auto s = read_file(entry.path().string());

        // Find "frames" array, iterate to last frame, grab its "grid"
        size_t fp = s.find("\"frames\"");
        if (fp == std::string::npos) continue;
        fp = s.find('[', fp);

        // Walk frames to find the last one
        Grid last_grid;
        size_t fi = fp + 1;
        while (true) {
            fi = skip_ws(s, fi);
            if (s[fi]==']') break;
            if (s[fi]==',') { fi++; continue; }
            // Frame object
            assert(s[fi]=='{'); fi++;
            Grid frame_grid;
            bool has_grid = false;
            while (true) {
                fi = skip_ws(s, fi);
                if (s[fi]=='}') { fi++; break; }
                if (s[fi]==',') { fi++; continue; }
                assert(s[fi]=='"');
                std::string key = parse_str(s, fi);
                fi = skip_ws(s, fi); assert(s[fi]==':'); fi++;
                fi = skip_ws(s, fi);
                if (key == "grid") {
                    frame_grid = parse_grid_2d(s, fi);
                    has_grid = true;
                } else {
                    skip_val(s, fi);
                }
            }
            if (has_grid) last_grid = std::move(frame_grid);
        }
        if (!last_grid.empty()) finals.push_back(std::move(last_grid));
    }

    if (finals.empty())
        std::cerr << "Warning: no replays found for round=" << round_id
                  << " seed=" << seed_index << " in " << replays_dir << "\n";
    return finals;
}

ProbGrid load_ground_truth(const std::string& json_path) {
    auto s = read_file(json_path);
    size_t i = find_key(s, "ground_truth");
    assert(i != std::string::npos);
    return parse_prob_3d(s, i);
}

// ----------------------------------------------------------------
// Scoring
// ----------------------------------------------------------------

static double kl_score(const ProbGrid& pred, const ProbGrid& truth) {
    int H = (int)pred.size(), W = (int)pred[0].size();
    double total_kl = 0, total_w = 0;
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            // Entropy of truth
            double h = 0;
            for (int c = 0; c < 6; c++) {
                double p = std::max(truth[y][x][c], 0.001);
                h -= p * std::log(p);
            }
            if (h < 0.001) continue;  // static cell, skip
            double kl = 0;
            for (int c = 0; c < 6; c++) {
                double p = std::max(truth[y][x][c], 0.01);
                double q = std::max(pred[y][x][c],  0.01);
                kl += p * std::log(p / q);
            }
            total_kl += h * kl;
            total_w  += h;
        }
    }
    if (total_w == 0) return 100.0;
    return 100.0 * std::exp(-3.0 * total_kl / total_w);
}

double score_vs_replays(const ProbGrid& pred,
                        const Grid& initial_grid,
                        const std::vector<Grid>& finals)
{
    if (finals.empty()) return 0.0;
    int H = (int)pred.size(), W = (int)pred[0].size();

    // Build empirical distribution from finals
    ProbGrid truth(H, std::vector<std::array<double,6>>(W, {0,0,0,0,0,0}));
    double inv = 1.0 / finals.size();
    for (auto& g : finals)
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++)
                truth[y][x][terrain_to_class(g[y][x])] += inv;

    // Zero out static cells (ocean/mountain never change)
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int t = initial_grid[y][x];
            if (t == 10 || t == 5) {  // ocean or mountain
                truth[y][x].fill(0);
                truth[y][x][terrain_to_class(t)] = 1.0;
            }
        }

    return kl_score(pred, truth);
}

double score_vs_truth(const ProbGrid& pred, const ProbGrid& truth) {
    return kl_score(pred, truth);
}
