#pragma once
#include <string>
#include <vector>
#include <array>
#include <map>
#include <cmath>
#include <random>
#include <fstream>
#include <sstream>
#include <iostream>
#include <filesystem>
#include <cassert>
#include <algorithm>
#include <numeric>

// ============================================================
// Class indices for the 6 prediction classes
// ============================================================
constexpr int CLASS_EMPTY      = 0;  // Ocean(10), Plains(11), Empty(0)
constexpr int CLASS_SETTLEMENT = 1;  // Active settlement
constexpr int CLASS_PORT       = 2;  // Coastal settlement with harbour
constexpr int CLASS_RUIN       = 3;  // Collapsed settlement
constexpr int CLASS_FOREST     = 4;  // Forest
constexpr int CLASS_MOUNTAIN   = 5;  // Mountain (static)
constexpr int NUM_CLASSES      = 6;

// Internal terrain codes from the simulation
constexpr int TERRAIN_EMPTY      = 0;
constexpr int TERRAIN_SETTLEMENT = 1;
constexpr int TERRAIN_PORT       = 2;
constexpr int TERRAIN_RUIN       = 3;
constexpr int TERRAIN_FOREST     = 4;
constexpr int TERRAIN_MOUNTAIN   = 5;
constexpr int TERRAIN_OCEAN      = 10;
constexpr int TERRAIN_PLAINS     = 11;

// Map terrain code -> class index
inline int terrain_to_class(int terrain) {
    switch (terrain) {
        case TERRAIN_EMPTY:      return CLASS_EMPTY;
        case TERRAIN_SETTLEMENT: return CLASS_SETTLEMENT;
        case TERRAIN_PORT:       return CLASS_PORT;
        case TERRAIN_RUIN:       return CLASS_RUIN;
        case TERRAIN_FOREST:     return CLASS_FOREST;
        case TERRAIN_MOUNTAIN:   return CLASS_MOUNTAIN;
        case TERRAIN_OCEAN:      return CLASS_EMPTY;
        case TERRAIN_PLAINS:     return CLASS_EMPTY;
        default:                 return CLASS_EMPTY;
    }
}

constexpr int MAP_W = 40;
constexpr int MAP_H = 40;
constexpr int NUM_SEEDS = 5;
constexpr int MAX_QUERIES = 50;
constexpr int MAX_VIEWPORT = 15;
constexpr double PROB_FLOOR = 0.0001;

// ============================================================
// Data structures
// ============================================================

struct Settlement {
    int x, y;
    bool has_port;
    bool alive;
    double population, food, wealth, defense;
    int owner_id;
};

struct Frame {
    int step;
    std::vector<std::vector<int>> grid;  // [y][x]
    std::vector<Settlement> settlements;
};

struct Replay {
    std::string round_id;
    int seed_index;
    int sim_seed;
    int width, height;
    std::vector<Frame> frames;
};

struct InitialState {
    std::vector<std::vector<int>> grid;  // [y][x]
    std::vector<Settlement> settlements;
};

struct RoundInfo {
    std::string round_id;
    int round_number;
    int map_width, map_height;
    int seeds_count;
    std::string timestamp;
};

// Probability tensor: [y][x][class]
using ProbTensor = std::vector<std::vector<std::array<double, NUM_CLASSES>>>;

struct Analysis {
    ProbTensor prediction;
    ProbTensor ground_truth;
    double score;
    int width, height;
    std::vector<std::vector<int>> initial_grid;
};

// ============================================================
// Viewport query result (for local simulation from replays)
// ============================================================
struct ViewportResult {
    std::vector<std::vector<int>> grid;  // viewport_h x viewport_w
    std::vector<Settlement> settlements;
    int vx, vy, vw, vh;
};

// ============================================================
// Infrastructure functions
// ============================================================

namespace infra {

// JSON parsing (minimal, no external deps)
std::string read_file(const std::string& path);

// Load data from disk
Replay load_replay(const std::string& path);
InitialState load_initial_state(const std::string& path);
Analysis load_analysis(const std::string& path);
RoundInfo load_round_info(const std::string& dir);

// Discover available rounds
struct RoundData {
    RoundInfo info;
    std::string initial_states_dir;
    // replay files indexed by [seed_index]
    std::vector<std::vector<std::string>> replay_files;  // [seed][list of replays]
    // analysis files indexed by [seed_index]
    std::vector<std::string> analysis_files;
};
std::vector<RoundData> discover_rounds(const std::string& base_dir);

// Local replay-based query: pick a random replay for this seed,
// return the final frame's viewport
ViewportResult query_local(const std::vector<std::string>& replay_files,
                           int vx, int vy, int vw, int vh,
                           std::mt19937& rng);

// Sample a viewport from ground truth probabilities (for local testing)
// Each cell is randomly sampled from its probability distribution
ViewportResult sample_from_ground_truth(const ProbTensor& ground_truth,
                                        int vx, int vy, int vw, int vh,
                                        std::mt19937& rng);

// Normalize probabilities with floor
void normalize_with_floor(ProbTensor& tensor);
void normalize_with_floor(ProbTensor& tensor, const std::vector<std::vector<int>>& initial_grid);

// Scoring
double kl_divergence(const std::array<double, NUM_CLASSES>& p,
                     const std::array<double, NUM_CLASSES>& q);
double entropy(const std::array<double, NUM_CLASSES>& p);
double score_prediction(const ProbTensor& prediction, const ProbTensor& ground_truth);

// HTML viewer - single combined report
struct SeedResult {
    int seed_index;
    double score;
    std::vector<std::vector<int>> initial_grid;
    ProbTensor guessed;
    ProbTensor actual;
};

struct RoundResult {
    int round_number;
    std::string round_id;
    double avg_score;
    std::vector<SeedResult> seeds;
};

void generate_html_report(const std::string& output_path,
                          const std::vector<RoundResult>& results);

}  // namespace infra

// ============================================================
// Solution interface — implemented in solution.cpp
// ============================================================
namespace solution {

// Called once per seed. Given initial state and query budget, produce predictions.
// query_fn simulates a viewport query (uses replays locally).
using QueryFn = std::function<ViewportResult(int vx, int vy, int vw, int vh)>;

// Correction factors learned from observations (shared across seeds)
using CorrectionFactors = std::array<double, NUM_CLASSES>;

// Distance-based class profile: class probabilities at each BFS distance
static constexpr int MAX_DIST_PROFILE = 8;
using DistProfile = std::array<std::array<double, NUM_CLASSES>, MAX_DIST_PROFILE>;

// Per-distance correction factors (5 distance buckets: 0, 1, 2, 3, 4+)
static constexpr int N_DIST_BUCKETS = 5;
using DistCorrection = std::array<CorrectionFactors, N_DIST_BUCKETS>;

// Shared state from query seed to non-query seeds
struct SharedState {
    CorrectionFactors correction = {1,1,1,1,1,1};
    DistCorrection dist_correction = {};
    bool has_dist_correction = false;
    double hc_fit = 0;
    double d3d1_ratio = 1.0;  // settlement localization: d3/d1 settle fraction
    double growth_ratio = 1.0;  // observed growth: obs_settle_frac / init_settle_frac
    DistProfile dist_profile = {};  // class probs by distance from initial settlements
    bool has_dist_profile = false;
    // Trained MLP shared across seeds (opaque pointer, cast in solution.cpp)
    void* trained_mlp = nullptr;
    bool has_mlp = false;
    // Shared observations from query seed for pseudo-Dirichlet on non-query seeds
    std::vector<std::vector<std::array<int, NUM_CLASSES>>> shared_obs_counts;
    std::vector<std::vector<int>> shared_obs_total;
    bool has_shared_obs = false;
    // Settlement stats from viewport queries (5 global features for settle MLP)
    float settle_feats[5] = {0.2f, 0.05f, 1.0f, 0.3f, 0.1f};  // defaults
    bool has_settle_stats = false;
};

ProbTensor predict(const InitialState& initial,
                   int seed_index,
                   int queries_available,
                   QueryFn query_fn,
                   std::mt19937& rng,
                   SharedState* shared = nullptr);

void set_fast_mode(bool fast);

// Tile scoring for choosing which seed to query
std::pair<int, int> find_best_query_tile(const std::vector<std::vector<int>>& grid);
double score_query_tile(const std::vector<std::vector<int>>& grid, int vx, int vy);

}  // namespace solution
