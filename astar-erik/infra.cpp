#include "infra.h"
#include <regex>
#include <iomanip>
#include <functional>

namespace infra {

// ============================================================
// Minimal JSON helpers (no external deps)
// We parse the specific JSON formats used by the challenge.
// ============================================================

std::string read_file(const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) {
        std::cerr << "ERROR: cannot open " << path << "\n";
        return "";
    }
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

// Skip whitespace
static size_t skip_ws(const std::string& s, size_t i) {
    while (i < s.size() && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r')) i++;
    return i;
}

// Parse a JSON number (int or float)
static double parse_number(const std::string& s, size_t& i) {
    size_t start = i;
    if (s[i] == '-') i++;
    while (i < s.size() && (isdigit(s[i]) || s[i] == '.' || s[i] == 'e' || s[i] == 'E' || s[i] == '+' || s[i] == '-')) {
        if (i > start && (s[i] == '-' || s[i] == '+') && s[i-1] != 'e' && s[i-1] != 'E') break;
        i++;
    }
    return std::stod(s.substr(start, i - start));
}

// Parse a JSON string (returns content without quotes)
static std::string parse_string(const std::string& s, size_t& i) {
    assert(s[i] == '"');
    i++;
    std::string result;
    while (i < s.size() && s[i] != '"') {
        if (s[i] == '\\') { i++; result += s[i]; }
        else result += s[i];
        i++;
    }
    i++; // skip closing "
    return result;
}

// Skip a JSON value (for fields we don't care about)
static void skip_value(const std::string& s, size_t& i) {
    i = skip_ws(s, i);
    if (s[i] == '"') { parse_string(s, i); return; }
    if (s[i] == '[') {
        i++; int depth = 1;
        while (i < s.size() && depth > 0) {
            if (s[i] == '[') depth++;
            else if (s[i] == ']') depth--;
            else if (s[i] == '"') { parse_string(s, i); continue; }
            i++;
        }
        return;
    }
    if (s[i] == '{') {
        i++; int depth = 1;
        while (i < s.size() && depth > 0) {
            if (s[i] == '{') depth++;
            else if (s[i] == '}') depth--;
            else if (s[i] == '"') { parse_string(s, i); continue; }
            i++;
        }
        return;
    }
    // number, bool, null
    while (i < s.size() && s[i] != ',' && s[i] != '}' && s[i] != ']' && s[i] != ' ' && s[i] != '\n') i++;
}

// Parse a 2D grid of ints: [[int, ...], ...]
static std::vector<std::vector<int>> parse_grid(const std::string& s, size_t& i) {
    std::vector<std::vector<int>> grid;
    i = skip_ws(s, i);
    assert(s[i] == '['); i++;
    while (true) {
        i = skip_ws(s, i);
        if (s[i] == ']') { i++; break; }
        if (s[i] == ',') { i++; continue; }
        assert(s[i] == '['); i++;
        std::vector<int> row;
        while (true) {
            i = skip_ws(s, i);
            if (s[i] == ']') { i++; break; }
            if (s[i] == ',') { i++; continue; }
            row.push_back((int)parse_number(s, i));
        }
        grid.push_back(std::move(row));
    }
    return grid;
}

// Parse a 3D probability tensor: [[[float,...], ...], ...]
static ProbTensor parse_prob_tensor(const std::string& s, size_t& i) {
    ProbTensor tensor;
    i = skip_ws(s, i);
    assert(s[i] == '['); i++;
    while (true) {
        i = skip_ws(s, i);
        if (s[i] == ']') { i++; break; }
        if (s[i] == ',') { i++; continue; }
        assert(s[i] == '['); i++;
        std::vector<std::array<double, NUM_CLASSES>> row;
        while (true) {
            i = skip_ws(s, i);
            if (s[i] == ']') { i++; break; }
            if (s[i] == ',') { i++; continue; }
            assert(s[i] == '['); i++;
            std::array<double, NUM_CLASSES> probs = {};
            int idx = 0;
            while (true) {
                i = skip_ws(s, i);
                if (s[i] == ']') { i++; break; }
                if (s[i] == ',') { i++; continue; }
                if (idx < NUM_CLASSES) probs[idx++] = parse_number(s, i);
                else parse_number(s, i);
            }
            row.push_back(probs);
        }
        tensor.push_back(std::move(row));
    }
    return tensor;
}

// Parse settlements array
static std::vector<Settlement> parse_settlements(const std::string& s, size_t& i) {
    std::vector<Settlement> settlements;
    i = skip_ws(s, i);
    assert(s[i] == '['); i++;
    while (true) {
        i = skip_ws(s, i);
        if (s[i] == ']') { i++; break; }
        if (s[i] == ',') { i++; continue; }
        assert(s[i] == '{'); i++;
        Settlement st = {};
        while (true) {
            i = skip_ws(s, i);
            if (s[i] == '}') { i++; break; }
            if (s[i] == ',') { i++; continue; }
            std::string key = parse_string(s, i);
            i = skip_ws(s, i);
            assert(s[i] == ':'); i++;
            i = skip_ws(s, i);
            if (key == "x") st.x = (int)parse_number(s, i);
            else if (key == "y") st.y = (int)parse_number(s, i);
            else if (key == "has_port") { st.has_port = (s[i] == 't'); skip_value(s, i); }
            else if (key == "alive") { st.alive = (s[i] == 't'); skip_value(s, i); }
            else if (key == "population") st.population = parse_number(s, i);
            else if (key == "food") st.food = parse_number(s, i);
            else if (key == "wealth") st.wealth = parse_number(s, i);
            else if (key == "defense") st.defense = parse_number(s, i);
            else if (key == "owner_id") st.owner_id = (int)parse_number(s, i);
            else skip_value(s, i);
        }
        settlements.push_back(st);
    }
    return settlements;
}

// ============================================================
// Load functions
// ============================================================

Replay load_replay(const std::string& path) {
    std::string s = read_file(path);
    Replay r;
    if (s.empty()) { std::cerr << "WARNING: empty replay " << path << "\n"; return r; }
    size_t i = skip_ws(s, 0);
    if (i >= s.size() || s[i] != '{') { std::cerr << "WARNING: bad replay " << path << "\n"; return r; }
    i++;
    while (true) {
        i = skip_ws(s, i);
        if (s[i] == '}') break;
        if (s[i] == ',') { i++; continue; }
        std::string key = parse_string(s, i);
        i = skip_ws(s, i); assert(s[i] == ':'); i++;
        i = skip_ws(s, i);
        if (key == "round_id") r.round_id = parse_string(s, i);
        else if (key == "seed_index") r.seed_index = (int)parse_number(s, i);
        else if (key == "sim_seed") r.sim_seed = (int)parse_number(s, i);
        else if (key == "width") r.width = (int)parse_number(s, i);
        else if (key == "height") r.height = (int)parse_number(s, i);
        else if (key == "frames") {
            assert(s[i] == '['); i++;
            while (true) {
                i = skip_ws(s, i);
                if (s[i] == ']') { i++; break; }
                if (s[i] == ',') { i++; continue; }
                assert(s[i] == '{'); i++;
                Frame f;
                while (true) {
                    i = skip_ws(s, i);
                    if (s[i] == '}') { i++; break; }
                    if (s[i] == ',') { i++; continue; }
                    std::string fkey = parse_string(s, i);
                    i = skip_ws(s, i); assert(s[i] == ':'); i++;
                    i = skip_ws(s, i);
                    if (fkey == "step") f.step = (int)parse_number(s, i);
                    else if (fkey == "grid") f.grid = parse_grid(s, i);
                    else if (fkey == "settlements") f.settlements = parse_settlements(s, i);
                    else skip_value(s, i);
                }
                r.frames.push_back(std::move(f));
            }
        }
        else skip_value(s, i);
    }
    return r;
}

InitialState load_initial_state(const std::string& path) {
    std::string s = read_file(path);
    InitialState is;
    size_t i = skip_ws(s, 0);
    assert(s[i] == '{'); i++;
    while (true) {
        i = skip_ws(s, i);
        if (s[i] == '}') break;
        if (s[i] == ',') { i++; continue; }
        std::string key = parse_string(s, i);
        i = skip_ws(s, i); assert(s[i] == ':'); i++;
        i = skip_ws(s, i);
        if (key == "grid") is.grid = parse_grid(s, i);
        else if (key == "settlements") is.settlements = parse_settlements(s, i);
        else skip_value(s, i);
    }
    return is;
}

Analysis load_analysis(const std::string& path) {
    std::string s = read_file(path);
    Analysis a;
    size_t i = skip_ws(s, 0);
    assert(s[i] == '{'); i++;
    while (true) {
        i = skip_ws(s, i);
        if (s[i] == '}') break;
        if (s[i] == ',') { i++; continue; }
        std::string key = parse_string(s, i);
        i = skip_ws(s, i); assert(s[i] == ':'); i++;
        i = skip_ws(s, i);
        if (key == "prediction") a.prediction = parse_prob_tensor(s, i);
        else if (key == "ground_truth") a.ground_truth = parse_prob_tensor(s, i);
        else if (key == "score") a.score = parse_number(s, i);
        else if (key == "width") a.width = (int)parse_number(s, i);
        else if (key == "height") a.height = (int)parse_number(s, i);
        else if (key == "initial_grid") a.initial_grid = parse_grid(s, i);
        else skip_value(s, i);
    }
    return a;
}

RoundInfo load_round_info(const std::string& dir) {
    std::string s = read_file(dir + "/summary.json");
    RoundInfo ri;
    size_t i = skip_ws(s, 0);
    assert(s[i] == '{'); i++;
    while (true) {
        i = skip_ws(s, i);
        if (s[i] == '}') break;
        if (s[i] == ',') { i++; continue; }
        std::string key = parse_string(s, i);
        i = skip_ws(s, i); assert(s[i] == ':'); i++;
        i = skip_ws(s, i);
        if (key == "round_id") ri.round_id = parse_string(s, i);
        else if (key == "round_number") ri.round_number = (int)parse_number(s, i);
        else if (key == "map_width") ri.map_width = (int)parse_number(s, i);
        else if (key == "map_height") ri.map_height = (int)parse_number(s, i);
        else if (key == "seeds_count") ri.seeds_count = (int)parse_number(s, i);
        else if (key == "timestamp") ri.timestamp = parse_string(s, i);
        else skip_value(s, i);
    }
    return ri;
}

// ============================================================
// Discover rounds by scanning the filesystem
// ============================================================

std::vector<RoundData> discover_rounds(const std::string& base_dir) {
    namespace fs = std::filesystem;
    std::string is_dir = base_dir + "/initial_states";
    std::string replay_dir = base_dir + "/replays";
    std::string analysis_dir = base_dir + "/analysis";

    std::vector<RoundData> rounds;

    for (auto& entry : fs::directory_iterator(is_dir)) {
        if (!entry.is_directory()) continue;
        std::string dirname = entry.path().filename().string();
        // Format: 20260320_120420_71451d74
        // Extract round_id prefix (last 8 chars)
        if (dirname.size() < 8) continue;
        std::string round_prefix = dirname.substr(dirname.size() - 8);

        RoundData rd;
        rd.initial_states_dir = entry.path().string();
        rd.info = load_round_info(rd.initial_states_dir);
        rd.replay_files.resize(NUM_SEEDS);
        rd.analysis_files.resize(NUM_SEEDS);

        // Find replay files for this round
        if (fs::exists(replay_dir)) {
            for (auto& rentry : fs::directory_iterator(replay_dir)) {
                std::string fname = rentry.path().filename().string();
                if (fname.find(rd.info.round_id) != std::string::npos && fname.find("replay") != std::string::npos && fname.size() > 5 && fname.rfind(".json") == fname.size() - 5) {
                    // Extract seed index from filename like: 03_19_22_replay_seed_0_71451d74-...
                    auto pos = fname.find("seed_");
                    if (pos != std::string::npos) {
                        int seed = fname[pos + 5] - '0';
                        if (seed >= 0 && seed < NUM_SEEDS)
                            rd.replay_files[seed].push_back(rentry.path().string());
                    }
                }
            }
        }

        // Find analysis files for this round
        if (fs::exists(analysis_dir)) {
            for (auto& aentry : fs::directory_iterator(analysis_dir)) {
                std::string fname = aentry.path().filename().string();
                if (fname.find(rd.info.round_id) != std::string::npos && fname.find("analysis") != std::string::npos) {
                    auto pos = fname.find("seed_");
                    if (pos != std::string::npos) {
                        int seed = fname[pos + 5] - '0';
                        if (seed >= 0 && seed < NUM_SEEDS)
                            rd.analysis_files[seed] = aentry.path().string();
                    }
                }
            }
        }

        rounds.push_back(std::move(rd));
    }

    // Sort by timestamp
    std::sort(rounds.begin(), rounds.end(), [](const RoundData& a, const RoundData& b) {
        return a.info.timestamp < b.info.timestamp;
    });

    // Deduplicate by round_id — keep the latest (most replays)
    {
        std::map<std::string, int> seen;
        std::vector<RoundData> deduped;
        for (auto& rd : rounds) {
            auto it = seen.find(rd.info.round_id);
            if (it != seen.end()) {
                // Keep the one with more replays
                auto& existing = deduped[it->second];
                int existing_replays = 0, new_replays = 0;
                for (auto& v : existing.replay_files) existing_replays += v.size();
                for (auto& v : rd.replay_files) new_replays += v.size();
                if (new_replays > existing_replays)
                    existing = std::move(rd);
            } else {
                seen[rd.info.round_id] = (int)deduped.size();
                deduped.push_back(std::move(rd));
            }
        }
        rounds = std::move(deduped);
    }

    return rounds;
}

// ============================================================
// Local query from replays
// ============================================================

ViewportResult query_local(const std::vector<std::string>& replay_files,
                           int vx, int vy, int vw, int vh,
                           std::mt19937& rng) {
    ViewportResult vr;
    if (replay_files.empty()) {
        std::cerr << "WARNING: no replay files for query\n";
        vr.grid.assign(vh, std::vector<int>(vw, TERRAIN_OCEAN));
        vr.vx = vx; vr.vy = vy; vr.vw = vw; vr.vh = vh;
        return vr;
    }

    // Pick a random replay
    std::uniform_int_distribution<int> dist(0, (int)replay_files.size() - 1);
    Replay rep = load_replay(replay_files[dist(rng)]);

    // Get the final frame (step 50)
    const Frame& final_frame = rep.frames.back();

    // Clamp viewport
    int cx = std::max(0, std::min(vx, rep.width - vw));
    int cy = std::max(0, std::min(vy, rep.height - vh));
    int cw = std::min(vw, rep.width - cx);
    int ch = std::min(vh, rep.height - cy);

    vr.vx = cx; vr.vy = cy; vr.vw = cw; vr.vh = ch;
    vr.grid.resize(ch);
    for (int y = 0; y < ch; y++) {
        vr.grid[y].resize(cw);
        for (int x = 0; x < cw; x++) {
            vr.grid[y][x] = final_frame.grid[cy + y][cx + x];
        }
    }

    // Filter settlements to viewport
    for (auto& st : final_frame.settlements) {
        if (st.x >= cx && st.x < cx + cw && st.y >= cy && st.y < cy + ch) {
            vr.settlements.push_back(st);
        }
    }

    return vr;
}

// ============================================================
// Sample viewport from ground truth probabilities
// ============================================================

// Map class index back to a terrain code for the sampled grid
static int class_to_terrain(int cls) {
    switch (cls) {
        case CLASS_EMPTY:      return TERRAIN_PLAINS;
        case CLASS_SETTLEMENT: return TERRAIN_SETTLEMENT;
        case CLASS_PORT:       return TERRAIN_PORT;
        case CLASS_RUIN:       return TERRAIN_RUIN;
        case CLASS_FOREST:     return TERRAIN_FOREST;
        case CLASS_MOUNTAIN:   return TERRAIN_MOUNTAIN;
        default:               return TERRAIN_PLAINS;
    }
}

ViewportResult sample_from_ground_truth(const ProbTensor& ground_truth,
                                        int vx, int vy, int vw, int vh,
                                        std::mt19937& rng) {
    int map_h = (int)ground_truth.size();
    int map_w = (int)ground_truth[0].size();

    // Clamp viewport
    int cx = std::max(0, std::min(vx, map_w - vw));
    int cy = std::max(0, std::min(vy, map_h - vh));
    int cw = std::min(vw, map_w - cx);
    int ch = std::min(vh, map_h - cy);

    ViewportResult vr;
    vr.vx = cx; vr.vy = cy; vr.vw = cw; vr.vh = ch;
    vr.grid.resize(ch);

    std::uniform_real_distribution<double> dist(0.0, 1.0);

    for (int y = 0; y < ch; y++) {
        vr.grid[y].resize(cw);
        for (int x = 0; x < cw; x++) {
            const auto& probs = ground_truth[cy + y][cx + x];
            double r = dist(rng);
            double cumul = 0;
            int sampled_class = 0;
            for (int c = 0; c < NUM_CLASSES; c++) {
                cumul += probs[c];
                if (r <= cumul) { sampled_class = c; break; }
            }
            vr.grid[y][x] = class_to_terrain(sampled_class);
        }
    }

    return vr;
}

// ============================================================
// Probability normalization
// ============================================================

void normalize_with_floor(ProbTensor& tensor) {
    for (auto& row : tensor) {
        for (auto& cell : row) {
            for (int c = 0; c < NUM_CLASSES; c++) {
                cell[c] = std::max(cell[c], PROB_FLOOR);
            }
            double sum = 0;
            for (int c = 0; c < NUM_CLASSES; c++) sum += cell[c];
            for (int c = 0; c < NUM_CLASSES; c++) cell[c] /= sum;
        }
    }
}

void normalize_with_floor(ProbTensor& tensor, const std::vector<std::vector<int>>& initial_grid) {
    int H = (int)tensor.size();
    int W = (int)tensor[0].size();

    // Precompute ocean adjacency for port feasibility
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            int t = initial_grid[y][x];
            auto& cell = tensor[y][x];

            // Determine which classes are possible for this cell
            bool is_ocean = (t == TERRAIN_OCEAN);
            bool is_mountain = (t == TERRAIN_MOUNTAIN);
            bool has_ocean_neighbor = false;

            if (!is_ocean && !is_mountain) {
                for (int dy = -1; dy <= 1 && !has_ocean_neighbor; dy++)
                    for (int dx = -1; dx <= 1 && !has_ocean_neighbor; dx++) {
                        int ny = y+dy, nx = x+dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W
                            && initial_grid[ny][nx] == TERRAIN_OCEAN)
                            has_ocean_neighbor = true;
                    }
            }

            // Apply terrain-aware floor
            // Mountain cells: only mountain is possible
            if (is_mountain) {
                cell = {0.0, 0.0, 0.0, 0.0, 0.0, 1.0};
            }
            // Ocean cells: only empty is possible
            else if (is_ocean) {
                cell = {1.0, 0.0, 0.0, 0.0, 0.0, 0.0};
            }
            else {
                // Regular land cell
                for (int c = 0; c < NUM_CLASSES; c++) {
                    if (c == CLASS_MOUNTAIN) {
                        // Land never becomes mountain
                        cell[c] = 0.0;
                    } else if (c == CLASS_PORT && !has_ocean_neighbor) {
                        // Non-coastal cells can't become ports
                        cell[c] = 0.0;
                    } else {
                        cell[c] = std::max(cell[c], PROB_FLOOR);
                    }
                }
            }

            // Normalize
            double sum = 0;
            for (int c = 0; c < NUM_CLASSES; c++) sum += cell[c];
            for (int c = 0; c < NUM_CLASSES; c++) cell[c] /= sum;
        }
    }
}

// ============================================================
// Scoring
// ============================================================

double kl_divergence(const std::array<double, NUM_CLASSES>& p,
                     const std::array<double, NUM_CLASSES>& q) {
    double kl = 0;
    for (int c = 0; c < NUM_CLASSES; c++) {
        if (p[c] > 1e-12) {
            double q_safe = std::max(q[c], 1e-12);
            kl += p[c] * std::log(p[c] / q_safe);
        }
    }
    return kl;
}

double entropy(const std::array<double, NUM_CLASSES>& p) {
    double h = 0;
    for (int c = 0; c < NUM_CLASSES; c++) {
        if (p[c] > 1e-12) {
            h -= p[c] * std::log(p[c]);
        }
    }
    return h;
}

double score_prediction(const ProbTensor& prediction, const ProbTensor& ground_truth) {
    int H = (int)ground_truth.size();
    int W = (int)ground_truth[0].size();
    double sum_weighted_kl = 0;
    double sum_entropy = 0;

    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            double h = entropy(ground_truth[y][x]);
            if (h < 1e-8) continue;  // skip static cells
            double kl = kl_divergence(ground_truth[y][x], prediction[y][x]);
            sum_weighted_kl += h * kl;
            sum_entropy += h;
        }
    }

    if (sum_entropy < 1e-8) return 100.0;
    double weighted_kl = sum_weighted_kl / sum_entropy;
    double score = std::max(0.0, std::min(100.0, 100.0 * std::exp(-3.0 * weighted_kl)));
    return score;
}

// ============================================================
// HTML viewer generation — single combined file
// ============================================================

// Helper to emit a 2D grid as JS array
static void emit_grid_js(std::ofstream& out, const std::string& name,
                          const std::vector<std::vector<int>>& grid) {
    int H = (int)grid.size(), W = (int)grid[0].size();
    out << "const " << name << "=[";
    for (int y = 0; y < H; y++) {
        out << "[";
        for (int x = 0; x < W; x++) { if (x) out << ","; out << grid[y][x]; }
        out << "],";
    }
    out << "];\n";
}

// Helper to emit a prob tensor as JS array
static void emit_prob_js(std::ofstream& out, const std::string& name,
                          const ProbTensor& t) {
    int H = (int)t.size(), W = (int)t[0].size();
    out << "const " << name << "=[";
    for (int y = 0; y < H; y++) {
        out << "[";
        for (int x = 0; x < W; x++) {
            out << "[";
            for (int c = 0; c < NUM_CLASSES; c++) {
                if (c) out << ",";
                out << std::fixed << std::setprecision(4) << t[y][x][c];
            }
            out << "],";
        }
        out << "],";
    }
    out << "];\n";
}

void generate_html_report(const std::string& output_path,
                          const std::vector<RoundResult>& results) {
    if (results.empty()) return;
    int H = MAP_H, W = MAP_W;
    int cell_size = 7;  // small cells for MacBook

    std::ofstream out(output_path);
    out << R"(<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Astar Island - All Rounds</title>
<style>
*{box-sizing:border-box}
body{font-family:monospace;background:#1a1a2e;color:#eee;margin:10px;font-size:11px}
h1{color:#e94560;margin:5px 0;font-size:18px}
.round-header{background:#16213e;border-left:4px solid #e94560;padding:6px 12px;margin:15px 0 8px 0;font-size:14px;font-weight:bold}
.round-divider{border:0;border-top:2px solid #e94560;margin:20px 0}
.seed-row{display:flex;gap:8px;align-items:center;margin:3px 0;flex-wrap:nowrap}
.seed-label{width:90px;flex-shrink:0;font-size:11px;text-align:right;padding-right:5px}
.seed-label .score{color:#e94560}
canvas{border:1px solid #333;cursor:crosshair}
.col-label{font-size:9px;color:#888;text-align:center}
.col-headers{display:flex;gap:8px;margin-left:98px}
.col-headers div{width:)" << W*cell_size << R"(px;text-align:center;font-size:9px;color:#aaa}
.legend{display:flex;gap:10px;margin:5px 0;flex-wrap:wrap;font-size:10px}
.legend-item{display:flex;align-items:center;gap:3px}
.legend-color{width:12px;height:12px;border:1px solid #555}
.tooltip{position:fixed;background:rgba(0,0,0,0.92);color:#fff;padding:6px 10px;
         border-radius:4px;font-size:11px;pointer-events:none;z-index:1000;
         max-width:240px;white-space:pre-line;display:none}
.summary{background:#0f3460;padding:8px 12px;margin:10px 0;border-radius:4px;font-size:12px}
</style>
</head><body>
<h1>Astar Island Viewer</h1>
<div class="legend">)";

    const char* legend_colors[] = {"#d4ac6e","#c0392b","#8e44ad","#7f8c8d","#27ae60","#5d6d7e"};
    const char* class_names[] = {"Empty/Ocean/Plains","Settlement","Port","Ruin","Forest","Mountain"};
    for (int c = 0; c < NUM_CLASSES; c++) {
        out << "<div class='legend-item'><div class='legend-color' style='background:"
            << legend_colors[c] << "'></div>" << class_names[c] << "</div>\n";
    }

    // Overall summary
    double grand_total = 0; int grand_count = 0;
    for (auto& r : results) { for (auto& s : r.seeds) { grand_total += s.score; grand_count++; } }
    out << "</div>\n<div class='summary'>Overall avg: <b>" << std::fixed << std::setprecision(2)
        << (grand_count > 0 ? grand_total/grand_count : 0) << "</b> / 100 across "
        << grand_count << " seeds, " << results.size() << " rounds</div>\n";

    // Column headers
    out << "<div class='col-headers'>"
        << "<div>Initial</div><div>Truth (argmax)</div><div>Guessed (argmax)</div><div>Error Map</div>"
        << "</div>\n";

    // Tooltip div must appear before scripts that reference it
    out << "<div class='tooltip' id='tooltip'></div>\n";

    // Emit data and canvases for each round/seed
    out << "<script>\n";
    out << "const W=" << W << ",H=" << H << ",CS=" << cell_size << ";\n";
    out << R"(const CLASS_NAMES=["Empty/Ocean/Plains","Settlement","Port","Ruin","Forest","Mountain"];
const CLASS_COLORS=["#d4ac6e","#c0392b","#8e44ad","#7f8c8d","#27ae60","#5d6d7e"];
const TERRAIN_NAMES={0:"Empty",1:"Settlement",2:"Port",3:"Ruin",4:"Forest",5:"Mountain",10:"Ocean",11:"Plains"};
const TERRAIN_COLORS={0:"#d4ac6e",1:"#c0392b",2:"#8e44ad",3:"#7f8c8d",4:"#27ae60",5:"#5d6d7e",10:"#1a5276",11:"#d4ac6e"};
const allData={};
)";

    // Emit all data
    for (size_t ri = 0; ri < results.size(); ri++) {
        auto& r = results[ri];
        for (size_t si = 0; si < r.seeds.size(); si++) {
            auto& s = r.seeds[si];
            std::string prefix = "r" + std::to_string(ri) + "s" + std::to_string(si);
            emit_grid_js(out, prefix + "_ig", s.initial_grid);
            emit_prob_js(out, prefix + "_g", s.guessed);
            emit_prob_js(out, prefix + "_a", s.actual);
            out << "allData['" << prefix << "']={ig:" << prefix << "_ig,g:"
                << prefix << "_g,a:" << prefix << "_a};\n";
        }
    }

    // Drawing functions
    out << R"(
function drawGrid(canvasId,grid){
  const c=document.getElementById(canvasId).getContext('2d');
  for(let y=0;y<H;y++)for(let x=0;x<W;x++){
    c.fillStyle=TERRAIN_COLORS[grid[y][x]]||'#000';
    c.fillRect(x*CS,y*CS,CS,CS);
  }
}
function drawArgmax(canvasId,data){
  const c=document.getElementById(canvasId).getContext('2d');
  for(let y=0;y<H;y++)for(let x=0;x<W;x++){
    const p=data[y][x];let m=0;
    for(let cl=1;cl<6;cl++)if(p[cl]>p[m])m=cl;
    c.fillStyle=CLASS_COLORS[m];
    c.fillRect(x*CS,y*CS,CS,CS);
  }
}
function drawError(canvasId,guessed,actual){
  const c=document.getElementById(canvasId).getContext('2d');
  for(let y=0;y<H;y++)for(let x=0;x<W;x++){
    const g=guessed[y][x],a=actual[y][x];
    // entropy of ground truth — skip static cells
    let ent=0;
    for(let cl=0;cl<6;cl++)if(a[cl]>1e-12)ent-=a[cl]*Math.log(a[cl]);
    if(ent<0.01){c.fillStyle='#222';c.fillRect(x*CS,y*CS,CS,CS);continue;}
    // KL divergence
    let kl=0;
    for(let cl=0;cl<6;cl++){if(a[cl]>1e-12){const q=Math.max(g[cl],1e-12);kl+=a[cl]*Math.log(a[cl]/q);}}
    // Map KL to quality: 0=perfect(green), high=bad(red). Use exp(-3*kl) like scoring
    const quality=Math.max(0,Math.min(1,Math.exp(-3*kl)));
    const r=Math.round(255*(1-quality));
    const gr=Math.round(255*quality);
    c.fillStyle=`rgb(${r},${gr},40)`;
    c.fillRect(x*CS,y*CS,CS,CS);
  }
}
</script>
)";

    // Emit HTML structure for each round
    for (size_t ri = 0; ri < results.size(); ri++) {
        auto& r = results[ri];
        if (ri > 0) out << "<hr class='round-divider'>\n";
        out << "<div class='round-header'>ROUND " << r.round_number
            << " (" << r.round_id.substr(0, 8) << "...) &mdash; avg: "
            << std::fixed << std::setprecision(2) << r.avg_score << " / 100</div>\n";

        for (size_t si = 0; si < r.seeds.size(); si++) {
            auto& s = r.seeds[si];
            std::string prefix = "r" + std::to_string(ri) + "s" + std::to_string(si);
            std::string cw = std::to_string(W * cell_size);
            std::string ch = std::to_string(H * cell_size);

            out << "<div class='seed-row'>\n";
            out << "  <div class='seed-label'>Seed " << s.seed_index
                << "<br><span class='score'>" << std::fixed << std::setprecision(1)
                << s.score << "</span></div>\n";

            const char* suffixes[] = {"_init", "_truth", "_guess", "_error"};
            for (int ci = 0; ci < 4; ci++) {
                out << "  <canvas id='" << prefix << suffixes[ci]
                    << "' width='" << cw << "' height='" << ch << "'></canvas>\n";
            }
            out << "</div>\n";
        }
    }

    // Draw everything
    out << "<script>\n";
    for (size_t ri = 0; ri < results.size(); ri++) {
        for (size_t si = 0; si < results[ri].seeds.size(); si++) {
            std::string p = "r" + std::to_string(ri) + "s" + std::to_string(si);
            out << "drawGrid('" << p << "_init',allData['" << p << "'].ig);\n";
            out << "drawArgmax('" << p << "_truth',allData['" << p << "'].a);\n";
            out << "drawArgmax('" << p << "_guess',allData['" << p << "'].g);\n";
            out << "drawError('" << p << "_error',allData['" << p << "'].g,allData['" << p << "'].a);\n";
        }
    }

    // Tooltip for all canvases
    out << R"(
const tooltip=document.getElementById('tooltip');
document.querySelectorAll('canvas').forEach(canvas=>{
  canvas.addEventListener('mousemove',e=>{
    const rect=canvas.getBoundingClientRect();
    const x=Math.floor((e.clientX-rect.left)/CS);
    const y=Math.floor((e.clientY-rect.top)/CS);
    if(x<0||x>=W||y<0||y>=H){tooltip.style.display='none';return;}
    // Find data key from canvas id
    const id=canvas.id;
    const key=id.replace(/_init|_truth|_guess|_error/,'');
    const d=allData[key];
    if(!d){tooltip.style.display='none';return;}
    let t=`Cell (${x},${y})\nInitial: ${TERRAIN_NAMES[d.ig[y][x]]||'?'}\n\nGuessed:\n`;
    for(let c=0;c<6;c++)t+=`  ${CLASS_NAMES[c]}: ${(d.g[y][x][c]*100).toFixed(1)}%\n`;
    t+=`\nActual:\n`;
    for(let c=0;c<6;c++)t+=`  ${CLASS_NAMES[c]}: ${(d.a[y][x][c]*100).toFixed(1)}%\n`;
    let kl=0;
    for(let c=0;c<6;c++){if(d.a[y][x][c]>1e-12){const q=Math.max(d.g[y][x][c],1e-12);kl+=d.a[y][x][c]*Math.log(d.a[y][x][c]/q);}}
    t+=`\nKL: ${kl.toFixed(4)}`;
    tooltip.textContent=t;
    tooltip.style.display='block';
    tooltip.style.left=(e.clientX+12)+'px';
    tooltip.style.top=(e.clientY+12)+'px';
  });
  canvas.addEventListener('mouseleave',()=>{tooltip.style.display='none';});
});
</script>
</body></html>
)";

    out.close();
    std::cout << "HTML report: " << output_path << "\n";
}

}  // namespace infra
