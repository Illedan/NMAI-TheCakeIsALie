// Fast C++ transition extractor from replay JSON files.
// Outputs binary: [N_transitions, feat_dim, then N * (feat_dim floats + 1 int8 target)]
// Grouped by source class (5 separate files).

#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <filesystem>
#include <queue>
#include <cmath>
#include <algorithm>

// Minimal JSON parsing for replay grid data
// Replays have: {"frames": [{"grid": [[int,...], ...]}, ...]}

namespace fs = std::filesystem;

static int terrain_to_class(int t) {
    if (t == 0 || t == 10 || t == 11) return 0; // Empty
    if (t == 1) return 1; // Settlement
    if (t == 2) return 2; // Port
    if (t == 3) return 3; // Ruin
    if (t == 4) return 4; // Forest
    if (t == 5) return 5; // Mountain
    return 0;
}

// Parse a JSON array of ints: [1, 2, 3, ...]
static std::vector<int> parse_int_array(const std::string& s, size_t& pos) {
    std::vector<int> result;
    while (pos < s.size() && s[pos] != '[') pos++;
    pos++; // skip [
    while (pos < s.size()) {
        while (pos < s.size() && (s[pos] == ' ' || s[pos] == '\n' || s[pos] == '\r')) pos++;
        if (s[pos] == ']') { pos++; break; }
        if (s[pos] == ',') { pos++; continue; }
        int val = 0;
        bool neg = false;
        if (s[pos] == '-') { neg = true; pos++; }
        while (pos < s.size() && s[pos] >= '0' && s[pos] <= '9') {
            val = val * 10 + (s[pos] - '0');
            pos++;
        }
        result.push_back(neg ? -val : val);
    }
    return result;
}

// Parse a 2D grid: [[int,...], [int,...], ...]
static std::vector<std::vector<int>> parse_grid(const std::string& s, size_t& pos) {
    std::vector<std::vector<int>> grid;
    while (pos < s.size() && s[pos] != '[') pos++;
    pos++; // skip outer [
    while (pos < s.size()) {
        while (pos < s.size() && (s[pos] == ' ' || s[pos] == '\n' || s[pos] == '\r')) pos++;
        if (s[pos] == ']') { pos++; break; }
        if (s[pos] == ',') { pos++; continue; }
        if (s[pos] == '[') {
            grid.push_back(parse_int_array(s, pos));
        }
    }
    return grid;
}

int main(int argc, char* argv[]) {
    std::string sim_dir = "/Users/erikkvanli/Repos/NMAI-TheCakeIsALie/astar-island/simulations";
    std::string out_dir = ".";
    if (argc > 1) out_dir = argv[1];

    // Collect replay files
    std::vector<std::string> replay_files;
    for (auto& entry : fs::recursive_directory_iterator(sim_dir)) {
        if (entry.path().extension() == ".json" &&
            entry.path().parent_path().filename() == "replays") {
            replay_files.push_back(entry.path().string());
        }
    }
    std::sort(replay_files.begin(), replay_files.end());
    std::cerr << "Found " << replay_files.size() << " replay files\n";

    // Output: per-source-class binary files
    constexpr int FEAT_DIM = 6;
    // Store features and targets separately to avoid padding issues
    std::vector<float> feats[5];    // flat: [f0,f1,...,f5, f0,f1,...,f5, ...]
    std::vector<uint8_t> targets[5];

    int processed = 0;
    for (auto& path : replay_files) {
        // Read file
        std::ifstream f(path);
        if (!f.is_open()) continue;
        std::stringstream ss;
        ss << f.rdbuf();
        std::string content = ss.str();

        // Quick validation
        if (content.find("\"frames\"") == std::string::npos) continue;

        // Parse all grids from frames
        std::vector<std::vector<std::vector<int>>> frames;
        size_t pos = 0;
        while (true) {
            pos = content.find("\"grid\"", pos);
            if (pos == std::string::npos) break;
            pos += 6;
            // Find the colon
            while (pos < content.size() && content[pos] != ':') pos++;
            pos++;
            while (pos < content.size() && (content[pos] == ' ' || content[pos] == '\n' || content[pos] == '\r')) pos++;
            auto grid = parse_grid(content, pos);
            if (!grid.empty()) {
                frames.push_back(std::move(grid));
            }
        }

        if (frames.size() < 2) continue;

        int H = (int)frames[0].size();
        int W = H > 0 ? (int)frames[0][0].size() : 0;
        if (H == 0 || W == 0) continue;

        // Convert to class grids
        std::vector<std::vector<std::vector<int>>> class_grids(frames.size(),
            std::vector<std::vector<int>>(H, std::vector<int>(W)));
        for (int fi = 0; fi < (int)frames.size(); fi++)
            for (int y = 0; y < H; y++)
                for (int x = 0; x < W; x++)
                    class_grids[fi][y][x] = terrain_to_class(frames[fi][y][x]);

        // BFS distance from initial settlements
        std::vector<std::vector<int>> dist(H, std::vector<int>(W, 999));
        std::queue<std::pair<int,int>> bfs;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                int t = frames[0][y][x];
                if (t == 1 || t == 2 || t == 3) {
                    dist[y][x] = 0;
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
                        int nd = dist[cy][cx] + 1;
                        if (nd < dist[ny][nx]) {
                            dist[ny][nx] = nd;
                            bfs.push({ny, nx});
                        }
                    }
                }
        }

        // Ocean adjacency
        std::vector<std::vector<bool>> has_ocean(H, std::vector<bool>(W, false));
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++)
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        int ny = y+dy, nx = x+dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W && frames[0][ny][nx] == 10)
                            has_ocean[y][x] = true;
                    }

        // Land mask
        std::vector<std::vector<bool>> land(H, std::vector<bool>(W, false));
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                int t = frames[0][y][x];
                if (t != 10 && t != 5) land[y][x] = true;
            }

        // Extract transitions
        for (int fi = 0; fi < (int)class_grids.size() - 1; fi++) {
            auto& curr = class_grids[fi];
            auto& nxt = class_grids[fi + 1];
            for (int y = 0; y < H; y++)
                for (int x = 0; x < W; x++) {
                    if (!land[y][x]) continue;
                    int c = curr[y][x];
                    if (c >= 5) continue;

                    float ns = 0, nf = 0, nr = 0;
                    for (int dy = -1; dy <= 1; dy++)
                        for (int dx = -1; dx <= 1; dx++) {
                            if (dy == 0 && dx == 0) continue;
                            int ny = y+dy, nx = x+dx;
                            if (ny >= 0 && ny < H && nx >= 0 && nx < W) {
                                int nc = curr[ny][nx];
                                if (nc == 1 || nc == 2) ns++;
                                else if (nc == 4) nf++;
                                else if (nc == 3) nr++;
                            }
                        }

                    float sr2 = 0;
                    for (int dy = -2; dy <= 2; dy++)
                        for (int dx = -2; dx <= 2; dx++) {
                            if (std::abs(dy) <= 1 && std::abs(dx) <= 1) continue;
                            int ny = y+dy, nx = x+dx;
                            if (ny >= 0 && ny < H && nx >= 0 && nx < W) {
                                int nc = curr[ny][nx];
                                if (nc == 1 || nc == 2) sr2++;
                            }
                        }

                    feats[c].push_back(ns / 8.0f);
                    feats[c].push_back(nf / 8.0f);
                    feats[c].push_back(nr / 8.0f);
                    feats[c].push_back(sr2 / 16.0f);
                    feats[c].push_back(has_ocean[y][x] ? 1.0f : 0.0f);
                    feats[c].push_back(std::min(dist[y][x], 15) / 15.0f);
                    targets[c].push_back((uint8_t)terrain_to_class(nxt[y][x]));
                }
        }

        processed++;
        if (processed % 20 == 0)
            std::cerr << "  Processed " << processed << "/" << replay_files.size() << "\n";
    }

    std::cerr << "Processed " << processed << " replays\n";

    // Write binary files: [n(int32), fdim(int32), n*fdim floats, n uint8s]
    const char* class_names[] = {"empty", "settlement", "port", "ruin", "forest"};
    for (int c = 0; c < 5; c++) {
        int32_t n = (int32_t)targets[c].size();
        int32_t fdim = FEAT_DIM;
        std::string fname = std::string(out_dir) + "/transitions_" + class_names[c] + ".bin";
        std::ofstream out(fname, std::ios::binary);
        out.write((char*)&n, 4);
        out.write((char*)&fdim, 4);
        out.write((char*)feats[c].data(), n * fdim * sizeof(float));
        out.write((char*)targets[c].data(), n);
        std::cerr << class_names[c] << ": " << n << " transitions\n";
    }

    std::cerr << "Done! Binary files written to " << out_dir << "\n";
    return 0;
}
