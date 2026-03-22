#include "infra.h"
#include "simulator.h"

// ============================================================
// Tune mode: run MC on a padded sub-region, output per-cell distributions
// Called by tune_params.py with: ./astar --tune input.json output.json
// ============================================================

static int run_tune(const std::string& input_path, const std::string& output_path) {
    std::string raw = infra::read_file(input_path);

    // Minimal JSON parser helpers
    auto find_val = [&](const std::string& key) -> size_t {
        std::string needle = "\"" + key + "\"";
        size_t pos = raw.find(needle);
        if (pos == std::string::npos) return std::string::npos;
        pos = raw.find(':', pos + needle.size());
        return pos + 1;
    };

    auto parse_double = [&](const std::string& key) -> double {
        size_t pos = find_val(key);
        if (pos == std::string::npos) return 1.0;
        while (pos < raw.size() && (raw[pos] == ' ' || raw[pos] == '\t')) pos++;
        return std::stod(raw.substr(pos, 20));
    };

    auto parse_int = [&](const std::string& key) -> int {
        size_t pos = find_val(key);
        if (pos == std::string::npos) return 0;
        while (pos < raw.size() && (raw[pos] == ' ' || raw[pos] == '\t')) pos++;
        return std::stoi(raw.substr(pos, 10));
    };

    // Parse 2D grid
    auto parse_2d_array = [](const std::string& s, size_t start) -> std::pair<std::vector<std::vector<int>>, size_t> {
        std::vector<std::vector<int>> result;
        size_t i = start;
        while (i < s.size() && s[i] != '[') i++;
        i++;
        while (i < s.size()) {
            while (i < s.size() && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t')) i++;
            if (s[i] == ']') { i++; break; }
            if (s[i] == ',') { i++; continue; }
            if (s[i] == '[') {
                i++;
                std::vector<int> row;
                while (i < s.size() && s[i] != ']') {
                    while (i < s.size() && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t' || s[i] == ',')) i++;
                    if (s[i] == ']') break;
                    int val = 0;
                    bool neg = false;
                    if (s[i] == '-') { neg = true; i++; }
                    while (i < s.size() && s[i] >= '0' && s[i] <= '9') {
                        val = val * 10 + (s[i] - '0');
                        i++;
                    }
                    row.push_back(neg ? -val : val);
                }
                i++;
                result.push_back(std::move(row));
            }
        }
        return {result, i};
    };

    // Parse grid
    size_t grid_pos = find_val("grid");
    auto [grid, _] = parse_2d_array(raw, grid_pos);

    int num_sims = parse_int("num_sims");
    if (num_sims <= 0) num_sims = 1000;

    // Parse params -> set simulator::tune
    // Find "params" object
    size_t params_pos = raw.find("\"params\"");
    if (params_pos != std::string::npos) {
        // Find the { after "params":
        size_t brace = raw.find('{', params_pos);
        size_t end_brace = raw.find('}', brace);
        std::string params_str = raw.substr(brace, end_brace - brace + 1);

        auto parse_param = [&](const std::string& s, const std::string& key) -> double {
            std::string needle = "\"" + key + "\"";
            size_t p = s.find(needle);
            if (p == std::string::npos) return 1.0;
            p = s.find(':', p);
            p++;
            while (p < s.size() && (s[p] == ' ' || s[p] == '\t')) p++;
            return std::stod(s.substr(p, 20));
        };

        auto pp = [&](const std::string& key, double def) {
            auto v = parse_param(params_str, key);
            return (v == 1.0) ? def : v;  // 1.0 = not found sentinel
        };
        // Parse all parametric model fields (use defaults if not in JSON)
        simulator::tune.es_base      = pp("es_base", simulator::tune.es_base);
        simulator::tune.es_ns_coeff  = pp("es_ns_coeff", simulator::tune.es_ns_coeff);
        simulator::tune.es_ns2_coeff = pp("es_ns2_coeff", simulator::tune.es_ns2_coeff);
        simulator::tune.es_sr2_coeff = pp("es_sr2_coeff", simulator::tune.es_sr2_coeff);
        simulator::tune.er_ratio     = pp("er_ratio", simulator::tune.er_ratio);
        simulator::tune.sr_base      = pp("sr_base", simulator::tune.sr_base);
        simulator::tune.sr_support   = pp("sr_support", simulator::tune.sr_support);
        simulator::tune.sr_nf_weight = pp("sr_nf_weight", simulator::tune.sr_nf_weight);
        simulator::tune.sr_sr2_coeff = pp("sr_sr2_coeff", simulator::tune.sr_sr2_coeff);
        simulator::tune.sp_base      = pp("sp_base", simulator::tune.sp_base);
        simulator::tune.sp_ns_coeff  = pp("sp_ns_coeff", simulator::tune.sp_ns_coeff);
        simulator::tune.fs_base      = pp("fs_base", simulator::tune.fs_base);
        simulator::tune.fs_ns_coeff  = pp("fs_ns_coeff", simulator::tune.fs_ns_coeff);
        simulator::tune.fs_ns2_coeff = pp("fs_ns2_coeff", simulator::tune.fs_ns2_coeff);
        simulator::tune.fr_ratio     = pp("fr_ratio", simulator::tune.fr_ratio);
        simulator::tune.pr_base      = pp("pr_base", simulator::tune.pr_base);
        simulator::tune.pr_ns_coeff  = pp("pr_ns_coeff", simulator::tune.pr_ns_coeff);
        simulator::tune.ruin_settle  = pp("ruin_settle", simulator::tune.ruin_settle);
        simulator::tune.ruin_empty   = pp("ruin_empty", simulator::tune.ruin_empty);
        simulator::tune.ruin_forest  = pp("ruin_forest", simulator::tune.ruin_forest);
        simulator::tune.ruin_port    = pp("ruin_port", simulator::tune.ruin_port);
        simulator::tune.ruin_ns_coeff = pp("ruin_ns_coeff", simulator::tune.ruin_ns_coeff);
        simulator::tune.mf_var_boost = pp("mf_var_boost", simulator::tune.mf_var_boost);
    }

    // Parse tile and pad regions
    // "tile": {"x":..., "y":..., "w":..., "h":...}
    // "pad": {"x":..., "y":..., "w":..., "h":...}
    auto parse_rect = [&](const std::string& key) -> std::array<int,4> {
        size_t pos = raw.find("\"" + key + "\"");
        if (pos == std::string::npos) return {0,0,0,0};
        size_t brace = raw.find('{', pos);
        size_t end_brace = raw.find('}', brace);
        std::string s = raw.substr(brace, end_brace - brace + 1);
        auto pf = [&](const std::string& f) -> int {
            std::string n = "\"" + f + "\"";
            size_t p = s.find(n);
            if (p == std::string::npos) return 0;
            p = s.find(':', p) + 1;
            while (p < s.size() && s[p] == ' ') p++;
            return std::stoi(s.substr(p, 10));
        };
        return {pf("x"), pf("y"), pf("w"), pf("h")};
    };

    auto tile = parse_rect("tile");
    auto pad = parse_rect("pad");

    int H = (int)grid.size(), W = H > 0 ? (int)grid[0].size() : 0;

    // Extract padded sub-grid for simulation
    int px = pad[0], py = pad[1], pw = pad[2], ph = pad[3];
    std::vector<std::vector<int>> sub_grid(ph, std::vector<int>(pw));
    for (int y = 0; y < ph; y++)
        for (int x = 0; x < pw; x++)
            sub_grid[y][x] = grid[py + y][px + x];

    std::cerr << "Tune: grid " << W << "x" << H
              << ", pad " << pw << "x" << ph << " at (" << px << "," << py << ")"
              << ", tile " << tile[2] << "x" << tile[3] << " at (" << tile[0] << "," << tile[1] << ")"
              << ", sims=" << num_sims << "\n";

    // Run mean-field on sub-grid
    ProbTensor mc = simulator::mean_field(sub_grid);

    // Output distributions for tile cells only (in global coords)
    std::ofstream out(output_path);
    out << std::fixed << std::setprecision(6);
    out << "[\n";
    bool first = true;
    for (int gy = tile[1]; gy < tile[1] + tile[3] && gy < H; gy++) {
        for (int gx = tile[0]; gx < tile[0] + tile[2] && gx < W; gx++) {
            int ly = gy - py, lx = gx - px;
            if (ly < 0 || ly >= ph || lx < 0 || lx >= pw) continue;
            if (!first) out << ",\n";
            first = false;
            out << "{\"y\":" << gy << ",\"x\":" << gx << ",\"probs\":[";
            for (int c = 0; c < NUM_CLASSES; c++) {
                out << mc[ly][lx][c];
                if (c < NUM_CLASSES - 1) out << ",";
            }
            out << "]}";
        }
    }
    out << "\n]\n";

    return 0;
}

// ============================================================
// Online mode: reads solver_input.json, writes prediction.json
// Called by online.py with: ./astar --online input.json output.json
//
// solver_input.json format:
// {
//   "grid": [[int, ...], ...],        // 40x40 initial terrain
//   "settlements": [...],              // (unused currently)
//   "queries": [                       // pre-fetched query results
//     { "vx":int, "vy":int, "vw":int, "vh":int, "grid":[[int,...], ...] }
//   ]
// }
//
// Output: 40x40x6 probability tensor as JSON array
// ============================================================

static int run_online(const std::string& input_path, const std::string& output_path) {
    std::string raw = infra::read_file(input_path);

    // Minimal JSON parse for the solver input
    // Extract "grid" and "queries" arrays
    auto find_key = [&](const std::string& key) -> size_t {
        std::string needle = "\"" + key + "\"";
        size_t pos = raw.find(needle);
        if (pos == std::string::npos) return std::string::npos;
        pos = raw.find(':', pos + needle.size());
        return pos + 1;
    };

    // Parse grid using infra's JSON utilities
    // We need to manually parse the 2D int array from JSON
    auto parse_2d_array = [](const std::string& s, size_t start) -> std::pair<std::vector<std::vector<int>>, size_t> {
        std::vector<std::vector<int>> result;
        size_t i = start;
        while (i < s.size() && s[i] != '[') i++;
        i++; // skip outer [

        while (i < s.size()) {
            while (i < s.size() && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t')) i++;
            if (s[i] == ']') { i++; break; }
            if (s[i] == ',') { i++; continue; }
            if (s[i] == '[') {
                i++; // skip inner [
                std::vector<int> row;
                while (i < s.size() && s[i] != ']') {
                    while (i < s.size() && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t' || s[i] == ',')) i++;
                    if (s[i] == ']') break;
                    int val = 0;
                    bool neg = false;
                    if (s[i] == '-') { neg = true; i++; }
                    while (i < s.size() && s[i] >= '0' && s[i] <= '9') {
                        val = val * 10 + (s[i] - '0');
                        i++;
                    }
                    row.push_back(neg ? -val : val);
                }
                i++; // skip ]
                result.push_back(std::move(row));
            }
        }
        return {result, i};
    };

    // Parse initial grid
    size_t grid_pos = find_key("grid");
    auto [grid, grid_end] = parse_2d_array(raw, grid_pos);

    int H = (int)grid.size();
    int W = H > 0 ? (int)grid[0].size() : 0;
    std::cerr << "Grid: " << W << "x" << H << "\n";

    // Parse queries
    struct QueryData {
        int vx, vy, vw, vh;
        std::vector<std::vector<int>> qgrid;
    };
    std::vector<QueryData> queries;

    // Find "queries" array
    size_t qpos = raw.find("\"queries\"");
    if (qpos != std::string::npos) {
        qpos = raw.find('[', qpos);
        qpos++; // skip outer [

        while (qpos < raw.size()) {
            while (qpos < raw.size() && (raw[qpos] == ' ' || raw[qpos] == '\n' || raw[qpos] == '\r' || raw[qpos] == '\t' || raw[qpos] == ',')) qpos++;
            if (raw[qpos] == ']') break;
            if (raw[qpos] == '{') {
                // Parse one query object
                QueryData qd;
                // Find vx, vy, vw, vh
                // Find "grid" within this query object
                size_t obj_start = qpos;
                // Find matching }
                int depth = 0;
                size_t obj_end = qpos;
                for (size_t k = qpos; k < raw.size(); k++) {
                    if (raw[k] == '{') depth++;
                    else if (raw[k] == '}') { depth--; if (depth == 0) { obj_end = k + 1; break; } }
                }

                std::string obj_str = raw.substr(obj_start, obj_end - obj_start);

                // Parse fields from this object substring
                auto parse_field_in = [&](const std::string& s, const std::string& key) -> int {
                    std::string needle = "\"" + key + "\"";
                    size_t p = s.find(needle);
                    if (p == std::string::npos) return 0;
                    p = s.find(':', p);
                    p++;
                    while (p < s.size() && (s[p] == ' ' || s[p] == '\t')) p++;
                    int val = 0;
                    while (p < s.size() && s[p] >= '0' && s[p] <= '9') {
                        val = val * 10 + (s[p] - '0');
                        p++;
                    }
                    return val;
                };

                qd.vx = parse_field_in(obj_str, "vx");
                qd.vy = parse_field_in(obj_str, "vy");
                qd.vw = parse_field_in(obj_str, "vw");
                qd.vh = parse_field_in(obj_str, "vh");

                // Find "grid" in the object
                size_t gp = obj_str.find("\"grid\"");
                if (gp != std::string::npos) {
                    gp = obj_str.find(':', gp) + 1;
                    auto [qgrid, _] = parse_2d_array(obj_str, gp);
                    qd.qgrid = std::move(qgrid);
                }

                queries.push_back(std::move(qd));
                qpos = obj_end;
            }
        }
    }

    std::cerr << "Queries: " << queries.size() << "\n";

    // Parse tune_params if present
    size_t tp_pos = raw.find("\"tune_params\"");
    if (tp_pos != std::string::npos) {
        size_t brace = raw.find('{', tp_pos);
        size_t end_brace = raw.find('}', brace);
        std::string ps = raw.substr(brace, end_brace - brace + 1);
        auto pp = [&](const std::string& key, double def) -> double {
            std::string n = "\"" + key + "\"";
            size_t p = ps.find(n);
            if (p == std::string::npos) return def;
            p = ps.find(':', p) + 1;
            while (p < ps.size() && ps[p] == ' ') p++;
            return std::stod(ps.substr(p, 20));
        };
        simulator::tune.es_base      = pp("es_base", simulator::tune.es_base);
        simulator::tune.es_ns_coeff  = pp("es_ns_coeff", simulator::tune.es_ns_coeff);
        simulator::tune.es_ns2_coeff = pp("es_ns2_coeff", simulator::tune.es_ns2_coeff);
        simulator::tune.es_sr2_coeff = pp("es_sr2_coeff", simulator::tune.es_sr2_coeff);
        simulator::tune.er_ratio     = pp("er_ratio", simulator::tune.er_ratio);
        simulator::tune.sr_base      = pp("sr_base", simulator::tune.sr_base);
        simulator::tune.sr_support   = pp("sr_support", simulator::tune.sr_support);
        simulator::tune.sr_nf_weight = pp("sr_nf_weight", simulator::tune.sr_nf_weight);
        simulator::tune.sr_sr2_coeff = pp("sr_sr2_coeff", simulator::tune.sr_sr2_coeff);
        simulator::tune.sr_raid      = pp("sr_raid", simulator::tune.sr_raid);
        simulator::tune.sr_ruin_coeff = pp("sr_ruin_coeff", simulator::tune.sr_ruin_coeff);
        simulator::tune.sp_base      = pp("sp_base", simulator::tune.sp_base);
        simulator::tune.sp_ns_coeff  = pp("sp_ns_coeff", simulator::tune.sp_ns_coeff);
        simulator::tune.fs_base      = pp("fs_base", simulator::tune.fs_base);
        simulator::tune.fs_ns_coeff  = pp("fs_ns_coeff", simulator::tune.fs_ns_coeff);
        simulator::tune.fs_ns2_coeff = pp("fs_ns2_coeff", simulator::tune.fs_ns2_coeff);
        simulator::tune.fr_ratio     = pp("fr_ratio", simulator::tune.fr_ratio);
        simulator::tune.pr_base      = pp("pr_base", simulator::tune.pr_base);
        simulator::tune.pr_ns_coeff  = pp("pr_ns_coeff", simulator::tune.pr_ns_coeff);
        simulator::tune.ruin_settle  = pp("ruin_settle", simulator::tune.ruin_settle);
        simulator::tune.ruin_empty   = pp("ruin_empty", simulator::tune.ruin_empty);
        simulator::tune.ruin_forest  = pp("ruin_forest", simulator::tune.ruin_forest);
        simulator::tune.ruin_port    = pp("ruin_port", simulator::tune.ruin_port);
        simulator::tune.ruin_ns_coeff = pp("ruin_ns_coeff", simulator::tune.ruin_ns_coeff);
        simulator::tune.mf_var_boost = pp("mf_var_boost", simulator::tune.mf_var_boost);
        std::cerr << "Tune params loaded (24 parametric coefficients)\n";
    }

    // Build InitialState
    InitialState initial;
    initial.grid = grid;

    // Create query function that replays pre-fetched results
    // The query_fn passes through the actual viewport position from each query
    int query_idx = 0;
    auto query_fn = [&](int /*vx*/, int /*vy*/, int /*vw*/, int /*vh*/) -> ViewportResult {
        ViewportResult vr;
        if (query_idx < (int)queries.size()) {
            auto& q = queries[query_idx++];
            vr.vx = q.vx; vr.vy = q.vy;
            vr.vw = q.vw; vr.vh = q.vh;
            vr.grid = q.qgrid;
        }
        return vr;
    };

    std::mt19937 rng(42);

    // Shared state: load from file if exists, save after if we have queries
    solution::SharedState shared;
    std::string corr_file = output_path + ".correction";

    // Try to load existing shared state (for seeds without queries)
    {
        std::ifstream cf(corr_file);
        if (cf.good()) {
            for (int c = 0; c < NUM_CLASSES; c++) cf >> shared.correction[c];
            cf >> shared.hc_fit >> shared.d3d1_ratio >> shared.growth_ratio;
            // Load per-distance corrections if present
            int has_dc = 0;
            if (cf >> has_dc && has_dc) {
                shared.has_dist_correction = true;
                for (int db = 0; db < solution::N_DIST_BUCKETS; db++)
                    for (int c = 0; c < NUM_CLASSES; c++)
                        cf >> shared.dist_correction[db][c];
            }
            // Try to load HC-tuned TuneParams
            std::string marker;
            if (cf >> marker && marker == "TUNE") {
                cf >> simulator::tune.es_base >> simulator::tune.es_ns_coeff
                   >> simulator::tune.es_ns2_coeff >> simulator::tune.es_sr2_coeff
                   >> simulator::tune.er_ratio >> simulator::tune.sr_base
                   >> simulator::tune.sr_support >> simulator::tune.sr_nf_weight
                   >> simulator::tune.sr_sr2_coeff >> simulator::tune.sr_raid
                   >> simulator::tune.sr_ruin_coeff >> simulator::tune.sp_base
                   >> simulator::tune.sp_ns_coeff >> simulator::tune.fs_base
                   >> simulator::tune.fs_ns_coeff >> simulator::tune.fs_ns2_coeff
                   >> simulator::tune.fr_ratio >> simulator::tune.pr_base
                   >> simulator::tune.pr_ns_coeff >> simulator::tune.ruin_settle
                   >> simulator::tune.ruin_empty >> simulator::tune.ruin_forest
                   >> simulator::tune.ruin_port >> simulator::tune.ruin_ns_coeff
                   >> simulator::tune.mf_var_boost >> simulator::tune.dist_decay
                   >> simulator::tune.es_ns_gate;
                std::cerr << "Loaded HC-tuned params from shared file\n";
            }
            std::cerr << "Loaded correction from " << corr_file
                      << " fit=" << shared.hc_fit << " d3d1=" << shared.d3d1_ratio << "\n";
        }
    }

    ProbTensor prediction = solution::predict(initial, 0, (int)queries.size(), query_fn, rng, &shared);

    // Save shared state if we had queries (for other seeds to use)
    if (!queries.empty()) {
        std::string dir = output_path.substr(0, output_path.rfind('/'));
        std::string shared_path = dir + "/shared_correction.txt";
        std::ofstream cf(shared_path);
        cf << std::fixed << std::setprecision(8);
        for (int c = 0; c < NUM_CLASSES; c++) cf << shared.correction[c] << " ";
        cf << shared.hc_fit << " " << shared.d3d1_ratio << " " << shared.growth_ratio << "\n";
        // Save per-distance corrections
        cf << shared.has_dist_correction << "\n";
        if (shared.has_dist_correction) {
            for (int db = 0; db < solution::N_DIST_BUCKETS; db++)
                for (int c = 0; c < NUM_CLASSES; c++)
                    cf << shared.dist_correction[db][c] << " ";
            cf << "\n";
        }
        // Save HC-tuned TuneParams so other seeds use the same model
        cf << "TUNE\n";
        cf << simulator::tune.es_base << " " << simulator::tune.es_ns_coeff << " "
           << simulator::tune.es_ns2_coeff << " " << simulator::tune.es_sr2_coeff << " "
           << simulator::tune.er_ratio << " " << simulator::tune.sr_base << " "
           << simulator::tune.sr_support << " " << simulator::tune.sr_nf_weight << " "
           << simulator::tune.sr_sr2_coeff << " " << simulator::tune.sr_raid << " "
           << simulator::tune.sr_ruin_coeff << " " << simulator::tune.sp_base << " "
           << simulator::tune.sp_ns_coeff << " " << simulator::tune.fs_base << " "
           << simulator::tune.fs_ns_coeff << " " << simulator::tune.fs_ns2_coeff << " "
           << simulator::tune.fr_ratio << " " << simulator::tune.pr_base << " "
           << simulator::tune.pr_ns_coeff << " " << simulator::tune.ruin_settle << " "
           << simulator::tune.ruin_empty << " " << simulator::tune.ruin_forest << " "
           << simulator::tune.ruin_port << " " << simulator::tune.ruin_ns_coeff << " "
           << simulator::tune.mf_var_boost << " " << simulator::tune.dist_decay << " "
           << simulator::tune.es_ns_gate << "\n";
        std::cerr << "Saved correction to " << shared_path << "\n";
    }

    // Write prediction as JSON: [[[p0,p1,...,p5], ...], ...]
    std::ofstream out(output_path);
    out << std::fixed << std::setprecision(6);
    out << "[\n";
    for (int y = 0; y < H; y++) {
        out << "  [";
        for (int x = 0; x < W; x++) {
            out << "[";
            for (int c = 0; c < NUM_CLASSES; c++) {
                out << prediction[y][x][c];
                if (c < NUM_CLASSES - 1) out << ",";
            }
            out << "]";
            if (x < W - 1) out << ",";
        }
        out << "]";
        if (y < H - 1) out << ",";
        out << "\n";
    }
    out << "]\n";

    std::cout << "Prediction written to " << output_path << "\n";
    return 0;
}

// ============================================================
// Local mode: test against downloaded replays
// ============================================================

static int run_local(const std::string& base_dir, const std::string& view_dir, int max_rounds = 0) {
    std::filesystem::create_directories(view_dir);

    std::cout << "Scanning " << base_dir << " for rounds...\n";
    auto rounds = infra::discover_rounds(base_dir);
    std::cout << "Found " << rounds.size() << " round(s)";
    if (max_rounds > 0 && max_rounds < (int)rounds.size()) {
        rounds.resize(max_rounds);
        std::cout << " (testing " << max_rounds << ")";
    }
    std::cout << "\n\n";

    if (rounds.empty()) {
        std::cerr << "No rounds found. Check --base path.\n";
        return 1;
    }

    std::mt19937 rng(42);
    double total_score = 0;
    int total_seeds = 0;

    std::vector<infra::RoundResult> all_results;

    for (auto& round : rounds) {
        // Reset simulator params to defaults between rounds
        simulator::tune = simulator::TuneParams();

        std::cout << "========================================\n";
        std::cout << "Round " << round.info.round_number
                  << " (" << round.info.round_id.substr(0, 8) << "...)\n";
        std::cout << "  Map: " << round.info.map_width << "x" << round.info.map_height
                  << ", Seeds: " << round.info.seeds_count << "\n";
        std::cout << "========================================\n";

        infra::RoundResult rr;
        rr.round_number = round.info.round_number;
        rr.round_id = round.info.round_id;
        double round_score_sum = 0;
        int round_seed_count = 0;

        solution::SharedState shared;

        for (int seed = 0; seed < round.info.seeds_count && seed < NUM_SEEDS; seed++) {
            if (round.analysis_files[seed].empty()) {
                std::cout << "  Seed " << seed << ": no analysis, skipping\n";
                continue;
            }

            std::string is_path = round.initial_states_dir + "/seed_" + std::to_string(seed) + ".json";
            InitialState initial = infra::load_initial_state(is_path);
            Analysis analysis = infra::load_analysis(round.analysis_files[seed]);

            // Seed 0 gets all 50 queries; others get 0 and use shared correction
            int budget = (seed == 0) ? MAX_QUERIES : 0;
            int queries_used = 0;

            // Use replays for query data when available (spatially correlated, like online)
            // Fall back to sample_from_ground_truth (independent samples) if no replays
            bool use_replays = (seed < (int)round.replay_files.size()
                               && round.replay_files[seed].size() >= 5);
            if (use_replays)
                std::cerr << "  Using " << round.replay_files[seed].size() << " replays for queries\n";

            auto query_fn = [&](int vx, int vy, int vw, int vh) -> ViewportResult {
                queries_used++;
                if (use_replays)
                    return infra::query_local(round.replay_files[seed], vx, vy, vw, vh, rng);
                return infra::sample_from_ground_truth(analysis.ground_truth, vx, vy, vw, vh, rng);
            };

            ProbTensor prediction = solution::predict(initial, seed, budget, query_fn, rng, &shared);
            double score = infra::score_prediction(prediction, analysis.ground_truth);
            total_score += score;
            total_seeds++;
            round_score_sum += score;
            round_seed_count++;

            std::cout << "  Seed " << seed << ": score=" << std::fixed << std::setprecision(2)
                      << score << " (queries used: " << queries_used << ")\n";

            infra::SeedResult sr;
            sr.seed_index = seed;
            sr.score = score;
            sr.initial_grid = initial.grid;
            sr.guessed = std::move(prediction);
            sr.actual = std::move(analysis.ground_truth);
            rr.seeds.push_back(std::move(sr));
        }

        rr.avg_score = round_seed_count > 0 ? round_score_sum / round_seed_count : 0;
        all_results.push_back(std::move(rr));
        std::cout << "\n";
    }

    std::string html_path = view_dir + "/report.html";
    infra::generate_html_report(html_path, all_results);

    if (total_seeds > 0) {
        std::cout << "========================================\n";
        std::cout << "OVERALL: " << std::fixed << std::setprecision(2)
                  << (total_score / total_seeds) << " avg score across "
                  << total_seeds << " seeds\n";
        std::cout << "========================================\n";
    }

    // Per-cell loss analysis: aggregate KL divergence across all rounds/seeds
    {
        // By terrain type
        std::array<double, 12> loss_by_initial_terrain = {};
        std::array<int, 12> count_by_initial_terrain = {};
        // By ground truth dominant class
        std::array<double, NUM_CLASSES> loss_by_gt_class = {};
        std::array<int, NUM_CLASSES> count_by_gt_class = {};
        // By BFS distance from initial settlement
        std::array<double, 10> loss_by_dist = {};
        std::array<int, 10> count_by_dist = {};
        // Top worst cells per round
        struct CellLoss {
            int round, seed, y, x;
            double kl;
            int initial_terrain;
            int gt_class;
            std::array<double, NUM_CLASSES> pred_probs;
            std::array<double, NUM_CLASSES> gt_probs;
        };
        std::vector<CellLoss> worst_cells;

        for (auto& rr : all_results) {
            for (auto& sr : rr.seeds) {
                int H = (int)sr.actual.size(), W = (int)sr.actual[0].size();
                // Compute settle_dist for this seed
                std::vector<std::vector<int>> sdist(H, std::vector<int>(W, 99));
                std::deque<std::pair<int,int>> bfs_q;
                for (int y = 0; y < H; y++)
                    for (int x = 0; x < W; x++)
                        if (sr.initial_grid[y][x] == TERRAIN_SETTLEMENT ||
                            sr.initial_grid[y][x] == TERRAIN_PORT) {
                            sdist[y][x] = 0;
                            bfs_q.push_back({y, x});
                        }
                while (!bfs_q.empty()) {
                    auto [cy, cx] = bfs_q.front(); bfs_q.pop_front();
                    for (int dy = -1; dy <= 1; dy++)
                        for (int dx = -1; dx <= 1; dx++) {
                            if (dy == 0 && dx == 0) continue;
                            int ny = cy+dy, nx = cx+dx;
                            if (ny < 0 || ny >= H || nx < 0 || nx >= W) continue;
                            if (sr.initial_grid[ny][nx] == TERRAIN_OCEAN ||
                                sr.initial_grid[ny][nx] == TERRAIN_MOUNTAIN) continue;
                            if (sdist[ny][nx] > sdist[cy][cx] + 1) {
                                sdist[ny][nx] = sdist[cy][cx] + 1;
                                bfs_q.push_back({ny, nx});
                            }
                        }
                }

                for (int y = 0; y < H; y++)
                    for (int x = 0; x < W; x++) {
                        int t = sr.initial_grid[y][x];
                        if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
                        double kl = infra::kl_divergence(sr.actual[y][x], sr.guessed[y][x]);
                        // By initial terrain
                        if (t >= 0 && t < 12) {
                            loss_by_initial_terrain[t] += kl;
                            count_by_initial_terrain[t]++;
                        }
                        // By GT dominant class
                        int gt_cls = 0;
                        double gt_max = 0;
                        for (int c = 0; c < NUM_CLASSES; c++)
                            if (sr.actual[y][x][c] > gt_max) { gt_max = sr.actual[y][x][c]; gt_cls = c; }
                        loss_by_gt_class[gt_cls] += kl;
                        count_by_gt_class[gt_cls]++;
                        // By distance
                        int d = std::min(sdist[y][x], 9);
                        loss_by_dist[d] += kl;
                        count_by_dist[d]++;
                        // Track worst
                        if (kl > 0.5) {
                            worst_cells.push_back({rr.round_number, sr.seed_index, y, x, kl,
                                                   t, gt_cls, sr.guessed[y][x], sr.actual[y][x]});
                        }
                    }
            }
        }

        std::cout << "\n========== PER-CELL LOSS ANALYSIS ==========\n";
        std::cout << "\nBy initial terrain type:\n";
        const char* terrain_names[] = {"Empty", "Settlement", "Port", "Ruin", "Forest",
                                        "Mountain", "?", "?", "?", "?", "Ocean", "Plains"};
        for (int t = 0; t < 12; t++) {
            if (count_by_initial_terrain[t] == 0) continue;
            std::cout << "  " << terrain_names[t] << ": avg_kl=" << std::fixed << std::setprecision(4)
                      << (loss_by_initial_terrain[t] / count_by_initial_terrain[t])
                      << " total=" << loss_by_initial_terrain[t]
                      << " n=" << count_by_initial_terrain[t] << "\n";
        }

        std::cout << "\nBy ground truth dominant class:\n";
        const char* class_names[] = {"Empty", "Settlement", "Port", "Ruin", "Forest", "Mountain"};
        for (int c = 0; c < NUM_CLASSES; c++) {
            if (count_by_gt_class[c] == 0) continue;
            std::cout << "  " << class_names[c] << ": avg_kl=" << std::fixed << std::setprecision(4)
                      << (loss_by_gt_class[c] / count_by_gt_class[c])
                      << " total=" << loss_by_gt_class[c]
                      << " n=" << count_by_gt_class[c] << "\n";
        }

        std::cout << "\nBy BFS distance from initial settlement:\n";
        for (int d = 0; d < 10; d++) {
            if (count_by_dist[d] == 0) continue;
            std::cout << "  dist=" << d << ": avg_kl=" << std::fixed << std::setprecision(4)
                      << (loss_by_dist[d] / count_by_dist[d])
                      << " total=" << loss_by_dist[d]
                      << " n=" << count_by_dist[d] << "\n";
        }

        // Sort worst cells and show top 20
        std::sort(worst_cells.begin(), worst_cells.end(),
                  [](const CellLoss& a, const CellLoss& b) { return a.kl > b.kl; });
        std::cout << "\nTop 20 worst cells (KL > 0.5):\n";
        for (int i = 0; i < std::min(20, (int)worst_cells.size()); i++) {
            auto& c = worst_cells[i];
            std::cout << "  R" << c.round << " s" << c.seed << " (" << c.x << "," << c.y
                      << ") kl=" << std::fixed << std::setprecision(3) << c.kl
                      << " init=" << terrain_names[c.initial_terrain]
                      << " gt=" << class_names[c.gt_class] << " | pred=[";
            for (int j = 0; j < NUM_CLASSES; j++)
                std::cout << (j?",":"") << std::setprecision(2) << c.pred_probs[j];
            std::cout << "] gt=[";
            for (int j = 0; j < NUM_CLASSES; j++)
                std::cout << (j?",":"") << std::setprecision(2) << c.gt_probs[j];
            std::cout << "]\n";
        }
        std::cout << "Total cells with KL > 0.5: " << worst_cells.size() << "\n";
    }

    return 0;
}

// ============================================================
// Plan mode: output 3-phase tile positions as JSON
// Usage: ./astar --plan initial_state.json output.json
// ============================================================

static std::pair<int, int> plan_find_best_tile(
    const std::vector<std::vector<int>>& grid) {
    int H = (int)grid.size(), W = (int)grid[0].size();
    int vw = std::min(MAX_VIEWPORT, W);
    int vh = std::min(MAX_VIEWPORT, H);
    int bx = 0, by = 0;
    double best = -1;
    for (int vy = 0; vy <= H - vh; vy++)
        for (int vx = 0; vx <= W - vw; vx++) {
            // Inline score_tile logic
            double score = 0;
            int ocean_count = 0;
            bool has_coastal = false;
            int settle_count = 0, forest_count = 0;
            for (int y = vy; y < vy + vh && y < H; y++)
                for (int x = vx; x < vx + vw && x < W; x++) {
                    int t = grid[y][x];
                    if (t == TERRAIN_OCEAN) { ocean_count++; continue; }
                    if (t == TERRAIN_MOUNTAIN) continue;
                    if (t == TERRAIN_SETTLEMENT || t == TERRAIN_PORT) { settle_count++; score += 3.0; }
                    else if (t == TERRAIN_FOREST) { forest_count++; score += 1.5; }
                    else if (t == TERRAIN_RUIN) score += 2.0;
                    else score += 0.5;
                    if (!has_coastal)
                        for (int dy = -1; dy <= 1 && !has_coastal; dy++)
                            for (int dx = -1; dx <= 1 && !has_coastal; dx++) {
                                int ny = y+dy, nx = x+dx;
                                if (ny >= 0 && ny < H && nx >= 0 && nx < W && grid[ny][nx] == TERRAIN_OCEAN)
                                    has_coastal = true;
                            }
                }
            double ocean_frac = (double)ocean_count / (vw * vh);
            if (ocean_frac > 0.5) continue;
            score *= (1.0 - ocean_frac);
            if (has_coastal) score *= 1.3;
            if (settle_count > 0 && forest_count > 0) score *= 1.2;
            if (score > best) { best = score; bx = vx; by = vy; }
        }
    return {bx, by};
}

static std::pair<int, int> plan_find_entropy_tile(
    const ProbTensor& mc_pred,
    const std::vector<std::vector<int>>& grid,
    const std::vector<std::pair<int,int>>& exclude_tiles,
    int vw, int vh) {
    int H = (int)mc_pred.size(), W = (int)mc_pred[0].size();

    // Mark cells covered by exclude_tiles
    std::vector<std::vector<bool>> covered(H, std::vector<bool>(W, false));
    for (auto& [ex, ey] : exclude_tiles)
        for (int y = ey; y < std::min(ey + vh, H); y++)
            for (int x = ex; x < std::min(ex + vw, W); x++)
                covered[y][x] = true;

    int bx = 0, by = 0;
    double best = -1;
    for (int vy = 0; vy <= H - vh; vy++) {
        for (int vx = 0; vx <= W - vw; vx++) {
            double entropy_sum = 0;
            int count = 0;
            for (int y = vy; y < vy + vh; y++)
                for (int x = vx; x < vx + vw; x++) {
                    int t = grid[y][x];
                    if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
                    if (covered[y][x]) continue;
                    double h = 0;
                    for (int c = 0; c < NUM_CLASSES; c++) {
                        double p = mc_pred[y][x][c];
                        if (p > 0.001) h -= p * std::log(p);
                    }
                    entropy_sum += h;
                    count++;
                }
            if (count > 0) {
                double avg = entropy_sum / count;
                if (avg > best) { best = avg; bx = vx; by = vy; }
            }
        }
    }
    return {bx, by};
}

static int run_plan(const std::string& input_path, const std::string& output_path) {
    InitialState initial = infra::load_initial_state(input_path);
    int H = (int)initial.grid.size(), W = (int)initial.grid[0].size();
    int vw = std::min(MAX_VIEWPORT, W);
    int vh = std::min(MAX_VIEWPORT, H);

    // Phase 1: best tile — matches solution.cpp find_best_tile()
    auto [t1x, t1y] = plan_find_best_tile(initial.grid);

    // Quick mean-field with default params for entropy-based placement
    ProbTensor mc = simulator::mean_field(initial.grid);

    // Phase 2: diverse tile (max distance*entropy from phase 1)
    int cx1 = t1x + vw/2, cy1 = t1y + vh/2;
    int t2x = 0, t2y = 0;
    double best2 = -1;
    // Dummy obs_total (nothing observed yet)
    for (int vy2 = 0; vy2 <= H - vh; vy2++)
        for (int vx2 = 0; vx2 <= W - vw; vx2++) {
            int cx2 = vx2 + vw/2, cy2 = vy2 + vh/2;
            double dist = std::sqrt((cx2-cx1)*(cx2-cx1) + (cy2-cy1)*(cy2-cy1));
            double entropy_sum = 0;
            int count = 0;
            for (int y = vy2; y < vy2 + vh; y++)
                for (int x = vx2; x < vx2 + vw; x++) {
                    int t = initial.grid[y][x];
                    if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
                    double h = 0;
                    for (int c = 0; c < NUM_CLASSES; c++) {
                        double p = mc[y][x][c];
                        if (p > 0.001) h -= p * std::log(p);
                    }
                    entropy_sum += h;
                    count++;
                }
            if (count > 0) {
                double avg_ent = entropy_sum / count;
                double score = avg_ent * (1.0 + 0.10 * dist);
                if (score > best2) { best2 = score; t2x = vx2; t2y = vy2; }
            }
        }

    // Remaining entropy tiles
    std::vector<std::pair<int,int>> exclude = {{t1x, t1y}, {t2x, t2y}};
    auto [t3x, t3y] = plan_find_entropy_tile(mc, initial.grid, exclude, vw, vh);
    exclude.push_back({t3x, t3y});
    auto [t4x, t4y] = plan_find_entropy_tile(mc, initial.grid, exclude, vw, vh);
    exclude.push_back({t4x, t4y});
    auto [t5x, t5y] = plan_find_entropy_tile(mc, initial.grid, exclude, vw, vh);

    // Output: 25 phase1 + 5 diverse + 5+5+5+5 entropy = 50 total
    // Matches solution.cpp: phase1=25, then 5 diverse, then 5*4 entropy
    std::ofstream out(output_path);
    out << "{\n";
    out << "  \"tiles\": [\n";
    out << "    {\"x\":" << t1x << ",\"y\":" << t1y << ",\"w\":" << vw << ",\"h\":" << vh << ",\"queries\":25,\"label\":\"Phase1-HC\"},\n";
    out << "    {\"x\":" << t2x << ",\"y\":" << t2y << ",\"w\":" << vw << ",\"h\":" << vh << ",\"queries\":5,\"label\":\"Phase2-diverse\"},\n";
    out << "    {\"x\":" << t3x << ",\"y\":" << t3y << ",\"w\":" << vw << ",\"h\":" << vh << ",\"queries\":5,\"label\":\"Phase2-entropy1\"},\n";
    out << "    {\"x\":" << t4x << ",\"y\":" << t4y << ",\"w\":" << vw << ",\"h\":" << vh << ",\"queries\":5,\"label\":\"Phase2-entropy2\"},\n";
    out << "    {\"x\":" << t5x << ",\"y\":" << t5y << ",\"w\":" << vw << ",\"h\":" << vh << ",\"queries\":5,\"label\":\"Phase2-entropy3\"}\n";
    out << "  ]\n";
    out << "}\n";
    std::cerr << "Plan: " << t1x << "," << t1y << " -> " << t2x << "," << t2y
              << " -> " << t3x << "," << t3y << " -> " << t4x << "," << t4y
              << " -> " << t5x << "," << t5y << "\n";
    return 0;
}

// ============================================================
// Interactive mode: real-time query protocol with Python
// Usage: ./astar --interactive <output_dir> <num_seeds>
// Reads seed initial states from output_dir/seed_N_initial.json
// Protocol (line-based on stdout/stdin):
//   C++ -> Python: QUERY <vx> <vy> <vw> <vh>
//   Python -> C++: <JSON line with "grid":[[...]]>
//   C++ -> Python: PREDICT <seed_idx>  (prediction written to file)
//   C++ -> Python: DONE
// ============================================================

static int run_interactive(const std::string& output_dir, int num_seeds) {
    // Helper: parse 2D grid from JSON string
    auto parse_grid_from_json = [](const std::string& s) -> std::vector<std::vector<int>> {
        std::vector<std::vector<int>> result;
        // Find first '['
        size_t i = s.find('[');
        if (i == std::string::npos) return result;

        // Check if this is inside a "grid" key
        size_t gp = s.find("\"grid\"");
        if (gp != std::string::npos) {
            i = s.find('[', gp);
        }
        i++; // skip outer [

        while (i < s.size()) {
            while (i < s.size() && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t')) i++;
            if (s[i] == ']') break;
            if (s[i] == ',') { i++; continue; }
            if (s[i] == '[') {
                i++; // skip inner [
                std::vector<int> row;
                while (i < s.size() && s[i] != ']') {
                    while (i < s.size() && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t' || s[i] == ',')) i++;
                    if (s[i] == ']') break;
                    int val = 0;
                    bool neg = false;
                    if (s[i] == '-') { neg = true; i++; }
                    while (i < s.size() && s[i] >= '0' && s[i] <= '9') {
                        val = val * 10 + (s[i] - '0');
                        i++;
                    }
                    row.push_back(neg ? -val : val);
                }
                i++; // skip ]
                result.push_back(std::move(row));
            }
        }
        return result;
    };

    // Load all seeds' initial states
    std::vector<InitialState> seeds(num_seeds);
    for (int s = 0; s < num_seeds; s++) {
        std::string path = output_dir + "/seed_" + std::to_string(s) + "_initial.json";
        seeds[s] = infra::load_initial_state(path);
        std::cerr << "Loaded seed " << s << " initial state\n";
    }

    int H = (int)seeds[0].grid.size();
    int W = H > 0 ? (int)seeds[0].grid[0].size() : 0;
    std::cerr << "Grid: " << W << "x" << H << ", " << num_seeds << " seeds\n";

    // Interactive query function for seed 0
    int query_count = 0;
    auto query_fn = [&](int vx, int vy, int vw, int vh) -> ViewportResult {
        // Request query from Python
        std::cout << "QUERY " << vx << " " << vy << " " << vw << " " << vh << std::endl;

        // Read response (one JSON line)
        std::string line;
        if (!std::getline(std::cin, line)) {
            std::cerr << "ERROR: stdin closed during query " << query_count << "\n";
            return ViewportResult{};
        }

        ViewportResult vr;
        vr.vx = vx; vr.vy = vy; vr.vw = vw; vr.vh = vh;
        vr.grid = parse_grid_from_json(line);

        // Check for viewport override (resubmit mode sends stored positions)
        // Format: {"grid":[[...]], "vx":N, "vy":N, "vw":N, "vh":N}
        {
            auto find_int = [&](const std::string& key) -> int {
                std::string pat = "\"" + key + "\":";
                size_t p = line.find(pat);
                if (p == std::string::npos) return -1;
                p += pat.size();
                while (p < line.size() && line[p] == ' ') p++;
                return std::stoi(line.substr(p));
            };
            int ovx = find_int("vx"), ovy = find_int("vy");
            int ovw = find_int("vw"), ovh = find_int("vh");
            if (ovx >= 0 && ovy >= 0) {
                if (ovx != vx || ovy != vy) {
                    std::cerr << "VIEWPORT OVERRIDE: asked=(" << vx << "," << vy
                              << ") using stored=(" << ovx << "," << ovy << ")\n";
                }
                vr.vx = ovx; vr.vy = ovy;
                if (ovw > 0) vr.vw = ovw;
                if (ovh > 0) vr.vh = ovh;
            }
        }

        if (vr.grid.empty()) {
            std::cerr << "WARNING: empty grid in query response " << query_count << "\n";
            vr.grid.assign(vr.vh, std::vector<int>(vr.vw, TERRAIN_OCEAN));
        }

        query_count++;
        std::cerr << "Query " << query_count << ": (" << vr.vx << "," << vr.vy
                  << ") " << vr.vw << "x" << vr.vh << " -> "
                  << vr.grid.size() << "x" << (vr.grid.empty() ? 0 : vr.grid[0].size()) << "\n";
        return vr;
    };

    std::mt19937 rng(42);
    solution::SharedState shared;

    // Tell Python how many queries we'll need
    // (Python reads this to know the budget)
    // Python already knows the budget from the API, so we just start querying

    // ---- Seed 0: query seed (interactive queries) ----
    std::cerr << "\n=== Seed 0 (query seed) ===\n";
    // Budget: 50 queries (Python controls actual budget)
    ProbTensor pred0 = solution::predict(seeds[0], 0, 50, query_fn, rng, &shared);
    std::cerr << "Seed 0: " << query_count << " queries used, hc_fit=" << shared.hc_fit << "\n";

    // Write prediction
    {
        std::string path = output_dir + "/seed_0_prediction.json";
        std::ofstream out(path);
        out << std::fixed << std::setprecision(6) << "[\n";
        for (int y = 0; y < H; y++) {
            out << "  [";
            for (int x = 0; x < W; x++) {
                out << "[";
                for (int c = 0; c < NUM_CLASSES; c++) {
                    out << pred0[y][x][c];
                    if (c < NUM_CLASSES - 1) out << ",";
                }
                out << "]";
                if (x < W - 1) out << ",";
            }
            out << "]";
            if (y < H - 1) out << ",";
            out << "\n";
        }
        out << "]\n";
        std::cerr << "Wrote " << path << "\n";
    }
    std::cout << "PREDICT 0" << std::endl;

    // Save shared state (correction factors + tuned params)
    {
        std::string shared_path = output_dir + "/shared_correction.txt";
        std::ofstream cf(shared_path);
        cf << std::fixed << std::setprecision(8);
        for (int c = 0; c < NUM_CLASSES; c++) cf << shared.correction[c] << " ";
        cf << shared.hc_fit << " " << shared.d3d1_ratio << " " << shared.growth_ratio << "\n";
        cf << shared.has_dist_correction << "\n";
        if (shared.has_dist_correction) {
            for (int db = 0; db < solution::N_DIST_BUCKETS; db++)
                for (int c = 0; c < NUM_CLASSES; c++)
                    cf << shared.dist_correction[db][c] << " ";
            cf << "\n";
        }
        cf << "TUNE\n";
        cf << simulator::tune.es_base << " " << simulator::tune.es_ns_coeff << " "
           << simulator::tune.es_ns2_coeff << " " << simulator::tune.es_sr2_coeff << " "
           << simulator::tune.er_ratio << " " << simulator::tune.sr_base << " "
           << simulator::tune.sr_support << " " << simulator::tune.sr_nf_weight << " "
           << simulator::tune.sr_sr2_coeff << " " << simulator::tune.sr_raid << " "
           << simulator::tune.sr_ruin_coeff << " " << simulator::tune.sp_base << " "
           << simulator::tune.sp_ns_coeff << " " << simulator::tune.fs_base << " "
           << simulator::tune.fs_ns_coeff << " " << simulator::tune.fs_ns2_coeff << " "
           << simulator::tune.fr_ratio << " " << simulator::tune.pr_base << " "
           << simulator::tune.pr_ns_coeff << " " << simulator::tune.ruin_settle << " "
           << simulator::tune.ruin_empty << " " << simulator::tune.ruin_forest << " "
           << simulator::tune.ruin_port << " " << simulator::tune.ruin_ns_coeff << " "
           << simulator::tune.mf_var_boost << " " << simulator::tune.dist_decay << " "
           << simulator::tune.es_ns_gate << "\n";
        std::cerr << "Saved shared state to " << shared_path << "\n";
    }

    // ---- Seeds 1-4: no queries, use shared state ----
    for (int s = 1; s < num_seeds; s++) {
        std::cerr << "\n=== Seed " << s << " (shared state) ===\n";
        // Reset simulator params, then load from shared
        simulator::tune = simulator::TuneParams();

        // Load tuned params from shared file (same as old --online mode)
        {
            std::string shared_path = output_dir + "/shared_correction.txt";
            std::ifstream cf(shared_path);
            solution::SharedState ss;
            for (int c = 0; c < NUM_CLASSES; c++) cf >> ss.correction[c];
            cf >> ss.hc_fit >> ss.d3d1_ratio >> ss.growth_ratio;
            int has_dc = 0;
            if (cf >> has_dc && has_dc) {
                ss.has_dist_correction = true;
                for (int db = 0; db < solution::N_DIST_BUCKETS; db++)
                    for (int c = 0; c < NUM_CLASSES; c++)
                        cf >> ss.dist_correction[db][c];
            }
            std::string marker;
            if (cf >> marker && marker == "TUNE") {
                cf >> simulator::tune.es_base >> simulator::tune.es_ns_coeff
                   >> simulator::tune.es_ns2_coeff >> simulator::tune.es_sr2_coeff
                   >> simulator::tune.er_ratio >> simulator::tune.sr_base
                   >> simulator::tune.sr_support >> simulator::tune.sr_nf_weight
                   >> simulator::tune.sr_sr2_coeff >> simulator::tune.sr_raid
                   >> simulator::tune.sr_ruin_coeff >> simulator::tune.sp_base
                   >> simulator::tune.sp_ns_coeff >> simulator::tune.fs_base
                   >> simulator::tune.fs_ns_coeff >> simulator::tune.fs_ns2_coeff
                   >> simulator::tune.fr_ratio >> simulator::tune.pr_base
                   >> simulator::tune.pr_ns_coeff >> simulator::tune.ruin_settle
                   >> simulator::tune.ruin_empty >> simulator::tune.ruin_forest
                   >> simulator::tune.ruin_port >> simulator::tune.ruin_ns_coeff
                   >> simulator::tune.mf_var_boost >> simulator::tune.dist_decay
                   >> simulator::tune.es_ns_gate;
            }
            shared = ss;
        }

        auto no_query = [](int, int, int, int) -> ViewportResult { return {}; };
        ProbTensor pred = solution::predict(seeds[s], s, 0, no_query, rng, &shared);

        // Write prediction
        std::string path = output_dir + "/seed_" + std::to_string(s) + "_prediction.json";
        std::ofstream out(path);
        out << std::fixed << std::setprecision(6) << "[\n";
        for (int y = 0; y < H; y++) {
            out << "  [";
            for (int x = 0; x < W; x++) {
                out << "[";
                for (int c = 0; c < NUM_CLASSES; c++) {
                    out << pred[y][x][c];
                    if (c < NUM_CLASSES - 1) out << ",";
                }
                out << "]";
                if (x < W - 1) out << ",";
            }
            out << "]";
            if (y < H - 1) out << ",";
            out << "\n";
        }
        out << "]\n";
        std::cerr << "Wrote " << path << "\n";
        std::cout << "PREDICT " << s << std::endl;
    }

    std::cout << "DONE" << std::endl;
    return 0;
}

int main(int argc, char* argv[]) {
    std::string base_dir = "../astar-island";
    std::string view_dir = "view";
    std::string online_input, online_output;
    std::string tune_input, tune_output;
    std::string plan_input, plan_output;
    std::string interactive_dir;
    int interactive_seeds = 0;
    int max_rounds = 0;  // 0 = all

    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "--base" && i+1 < argc) base_dir = argv[++i];
        else if (arg == "--view" && i+1 < argc) view_dir = argv[++i];
        else if (arg == "--quick") { max_rounds = 3; solution::set_fast_mode(true); }
        else if (arg == "--fast") { solution::set_fast_mode(true); }
        else if (arg == "--rounds" && i+1 < argc) max_rounds = std::stoi(argv[++i]);
        else if (arg == "--online" && i+2 < argc) {
            online_input = argv[++i];
            online_output = argv[++i];
        }
        else if (arg == "--tune" && i+2 < argc) {
            tune_input = argv[++i];
            tune_output = argv[++i];
        }
        else if (arg == "--plan" && i+2 < argc) {
            plan_input = argv[++i];
            plan_output = argv[++i];
        }
        else if (arg == "--interactive" && i+2 < argc) {
            interactive_dir = argv[++i];
            interactive_seeds = std::stoi(argv[++i]);
        }
    }

    if (!tune_input.empty()) {
        return run_tune(tune_input, tune_output);
    }

    if (!plan_input.empty()) {
        return run_plan(plan_input, plan_output);
    }

    if (!interactive_dir.empty()) {
        return run_interactive(interactive_dir, interactive_seeds);
    }

    if (!online_input.empty()) {
        return run_online(online_input, online_output);
    }

    return run_local(base_dir, view_dir, max_rounds);
}
