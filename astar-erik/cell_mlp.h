#pragma once
#include "infra.h"
#include <vector>
#include <array>
#include <set>
#include <cmath>
#include <random>

// Tiny MLP trained per-round from 50 query samples.
// Learns P(final_class | cell_features) including settlement metadata.
// Features per cell:
//   - initial terrain one-hot (5: empty, settle, port, ruin, forest)
//   - settlement neighbor count (normalized)
//   - forest neighbor count (normalized)
//   - ruin neighbor count (normalized)
//   - settle r2 density
//   - ocean adjacency
//   - BFS distance from initial settlements
//   - nearest settlement: population (or 0)
//   - nearest settlement: food (or 0)
//   - nearest settlement: defense (or 0)
//   - max neighbor settlement population
//   - sum neighbor settlement population
// Total: 16 features

namespace cell_mlp {

static constexpr int FEAT_DIM = 14;
static constexpr int HIDDEN = 32;
static constexpr int OUT_DIM = NUM_CLASSES;  // 6

struct MLP {
    // Layer 1: FEAT_DIM -> HIDDEN
    float w1[HIDDEN][FEAT_DIM];
    float b1[HIDDEN];
    // Layer 2: HIDDEN -> HIDDEN
    float w2[HIDDEN][HIDDEN];
    float b2[HIDDEN];
    // Layer 3: HIDDEN -> OUT_DIM
    float w3[OUT_DIM][HIDDEN];
    float b3[OUT_DIM];

    void init_random(std::mt19937& rng) {
        std::normal_distribution<float> norm(0.0f, 0.1f);
        for (int i = 0; i < HIDDEN; i++) {
            for (int j = 0; j < FEAT_DIM; j++) w1[i][j] = norm(rng) / std::sqrt((float)FEAT_DIM);
            b1[i] = 0;
        }
        for (int i = 0; i < HIDDEN; i++) {
            for (int j = 0; j < HIDDEN; j++) w2[i][j] = norm(rng) / std::sqrt((float)HIDDEN);
            b2[i] = 0;
        }
        for (int i = 0; i < OUT_DIM; i++) {
            for (int j = 0; j < HIDDEN; j++) w3[i][j] = norm(rng) / std::sqrt((float)HIDDEN);
            b3[i] = 0;
        }
    }

    // Forward pass → softmax output
    void forward(const float* x, float* out) const {
        float h1[HIDDEN], h2[HIDDEN];
        // Layer 1
        for (int i = 0; i < HIDDEN; i++) {
            float sum = b1[i];
            for (int j = 0; j < FEAT_DIM; j++) sum += w1[i][j] * x[j];
            h1[i] = sum > 0 ? sum : 0;  // ReLU
        }
        // Layer 2
        for (int i = 0; i < HIDDEN; i++) {
            float sum = b2[i];
            for (int j = 0; j < HIDDEN; j++) sum += w2[i][j] * h1[j];
            h2[i] = sum > 0 ? sum : 0;
        }
        // Layer 3 + softmax
        float logits[OUT_DIM];
        float max_l = -1e9f;
        for (int i = 0; i < OUT_DIM; i++) {
            float sum = b3[i];
            for (int j = 0; j < HIDDEN; j++) sum += w3[i][j] * h2[j];
            logits[i] = sum;
            if (sum > max_l) max_l = sum;
        }
        float exp_sum = 0;
        for (int i = 0; i < OUT_DIM; i++) {
            out[i] = std::exp(logits[i] - max_l);
            exp_sum += out[i];
        }
        for (int i = 0; i < OUT_DIM; i++) out[i] /= exp_sum;
    }

    // Backward pass + SGD update. Returns cross-entropy loss.
    float train_step(const float* x, int target, float lr) {
        // Forward with cached activations
        float h1[HIDDEN], h2[HIDDEN], h1_pre[HIDDEN], h2_pre[HIDDEN];
        for (int i = 0; i < HIDDEN; i++) {
            float sum = b1[i];
            for (int j = 0; j < FEAT_DIM; j++) sum += w1[i][j] * x[j];
            h1_pre[i] = sum;
            h1[i] = sum > 0 ? sum : 0;
        }
        for (int i = 0; i < HIDDEN; i++) {
            float sum = b2[i];
            for (int j = 0; j < HIDDEN; j++) sum += w2[i][j] * h1[j];
            h2_pre[i] = sum;
            h2[i] = sum > 0 ? sum : 0;
        }
        float out[OUT_DIM];
        float max_l = -1e9f;
        for (int i = 0; i < OUT_DIM; i++) {
            float sum = b3[i];
            for (int j = 0; j < HIDDEN; j++) sum += w3[i][j] * h2[j];
            out[i] = sum;
            if (sum > max_l) max_l = sum;
        }
        float exp_sum = 0;
        for (int i = 0; i < OUT_DIM; i++) {
            out[i] = std::exp(out[i] - max_l);
            exp_sum += out[i];
        }
        for (int i = 0; i < OUT_DIM; i++) out[i] /= exp_sum;

        float loss = -std::log(std::max(out[target], 1e-7f));

        // Gradient of softmax + cross-entropy: dL/d_logit[i] = out[i] - (i==target)
        float d3[OUT_DIM];
        for (int i = 0; i < OUT_DIM; i++)
            d3[i] = out[i] - (i == target ? 1.0f : 0.0f);

        // Update w3, b3 and compute dh2
        float dh2[HIDDEN] = {};
        for (int i = 0; i < OUT_DIM; i++) {
            for (int j = 0; j < HIDDEN; j++) {
                dh2[j] += w3[i][j] * d3[i];
                w3[i][j] -= lr * d3[i] * h2[j];
            }
            b3[i] -= lr * d3[i];
        }

        // ReLU gradient
        for (int i = 0; i < HIDDEN; i++)
            if (h2_pre[i] <= 0) dh2[i] = 0;

        // Update w2, b2 and compute dh1
        float dh1[HIDDEN] = {};
        for (int i = 0; i < HIDDEN; i++) {
            for (int j = 0; j < HIDDEN; j++) {
                dh1[j] += w2[i][j] * dh2[i];
                w2[i][j] -= lr * dh2[i] * h1[j];
            }
            b2[i] -= lr * dh2[i];
        }

        for (int i = 0; i < HIDDEN; i++)
            if (h1_pre[i] <= 0) dh1[i] = 0;

        // Update w1, b1
        for (int i = 0; i < HIDDEN; i++) {
            for (int j = 0; j < FEAT_DIM; j++)
                w1[i][j] -= lr * dh1[i] * x[j];
            b1[i] -= lr * dh1[i];
        }

        return loss;
    }
};

// Extract features for a cell given initial grid and settlement data
struct CellFeatures {
    float f[FEAT_DIM];
};

// Build feature map for the entire grid
struct FeatureMap {
    std::vector<std::vector<CellFeatures>> features;  // [y][x]
    int H, W;

    void build(const std::vector<std::vector<int>>& grid,
               const std::vector<Settlement>& /*settlements*/) {
        H = (int)grid.size();
        W = (int)grid[0].size();
        features.assign(H, std::vector<CellFeatures>(W));

        // BFS distance from initial settlements
        std::vector<std::vector<int>> dist(H, std::vector<int>(W, 999));
        std::vector<std::pair<int,int>> bfs;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                int t = grid[y][x];
                if (t == TERRAIN_SETTLEMENT || t == TERRAIN_PORT || t == TERRAIN_RUIN) {
                    dist[y][x] = 0;
                    bfs.push_back({y, x});
                }
            }
        for (int qi = 0; qi < (int)bfs.size(); qi++) {
            auto [cy, cx] = bfs[qi];
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    if (dy == 0 && dx == 0) continue;
                    int ny = cy+dy, nx = cx+dx;
                    if (ny >= 0 && ny < H && nx >= 0 && nx < W) {
                        int nd = dist[cy][cx] + 1;
                        if (nd < dist[ny][nx]) {
                            dist[ny][nx] = nd;
                            bfs.push_back({ny, nx});
                        }
                    }
                }
        }

        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                auto& f = features[y][x].f;
                int t = grid[y][x];
                int c = terrain_to_class(t);

                // One-hot terrain (5 classes, skip mountain)
                for (int i = 0; i < 5; i++) f[i] = (c == i) ? 1.0f : 0.0f;

                // Neighbor counts + owner features
                float ns = 0, nf = 0, nr = 0, nm = 0, np = 0;
                int n_land = 0;  // non-mountain, non-ocean neighbors (connectivity)
                bool has_ocean = false;
                // Settlement population/food/defense/wealth not available from API
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        if (dy == 0 && dx == 0) continue;
                        int ny = y+dy, nx = x+dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W) {
                            int nc = terrain_to_class(grid[ny][nx]);
                            if (nc == CLASS_SETTLEMENT || nc == CLASS_PORT) ns++;
                            else if (nc == CLASS_FOREST) nf++;
                            else if (nc == CLASS_RUIN) nr++;
                            if (nc == CLASS_MOUNTAIN) nm++;
                            if (grid[ny][nx] == TERRAIN_OCEAN) has_ocean = true;
                            if (grid[ny][nx] == TERRAIN_PLAINS) np++;
                            if (grid[ny][nx] != TERRAIN_OCEAN && nc != CLASS_MOUNTAIN) n_land++;
                        }
                    }

                // r2 settle density
                float sr2 = 0;
                for (int dy = -2; dy <= 2; dy++)
                    for (int dx = -2; dx <= 2; dx++) {
                        if (std::abs(dy) <= 1 && std::abs(dx) <= 1) continue;
                        int ny = y+dy, nx = x+dx;
                        if (ny >= 0 && ny < H && nx >= 0 && nx < W) {
                            int nc = terrain_to_class(grid[ny][nx]);
                            if (nc == CLASS_SETTLEMENT || nc == CLASS_PORT) sr2++;
                        }
                    }

                f[5] = ns / 8.0f;
                f[6] = nf / 8.0f;
                f[7] = nr / 8.0f;
                f[8] = sr2 / 16.0f;
                f[9] = has_ocean ? 1.0f : 0.0f;
                f[10] = std::min(dist[y][x], 15) / 15.0f;
                f[11] = nm / 8.0f;  // mountain neighbor fraction
                f[12] = n_land / 8.0f;  // land connectivity
                f[13] = np / 8.0f;  // plains neighbor fraction
            }
        }
    }
};

// Train MLP from viewport query observations
struct TrainResult {
    MLP model;
    double final_loss;
    int n_samples;
};

inline TrainResult train_from_queries(
    const FeatureMap& fmap,
    const std::vector<std::vector<std::vector<int>>>& observations,  // [query][y][x] = class
    int obs_vx, int obs_vy, int obs_vw, int obs_vh,
    std::mt19937& rng,
    int epochs = 15,
    float lr = 0.01f)
{
    MLP model;
    model.init_random(rng);

    // Collect training samples
    struct Sample {
        const float* features;
        int target;
    };
    std::vector<Sample> samples;

    for (auto& obs : observations) {
        for (int y = 0; y < obs_vh && y < (int)obs.size(); y++) {
            for (int x = 0; x < obs_vw && x < (int)obs[y].size(); x++) {
                int gy = obs_vy + y, gx = obs_vx + x;
                if (gy >= fmap.H || gx >= fmap.W) continue;
                int t = terrain_to_class(fmap.features[gy][gx].f[0] > 0.5f ? TERRAIN_OCEAN : 0);
                // Check if ocean or mountain (skip)
                bool is_ocean = (fmap.features[gy][gx].f[0] == 1.0f &&
                                 fmap.features[gy][gx].f[1] == 0.0f &&
                                 fmap.features[gy][gx].f[2] == 0.0f &&
                                 fmap.features[gy][gx].f[3] == 0.0f &&
                                 fmap.features[gy][gx].f[4] == 0.0f &&
                                 fmap.features[gy][gx].f[9] == 1.0f);
                // Simpler: just check if all neighbor features are zero and it's "empty"
                // Actually, just use the initial grid info already encoded
                int cls = obs[y][x];
                if (cls == CLASS_MOUNTAIN) continue;

                samples.push_back({fmap.features[gy][gx].f, cls});
            }
        }
    }

    if (samples.empty()) return {model, 999.0, 0};

    // Shuffle indices
    std::vector<int> indices(samples.size());
    for (int i = 0; i < (int)indices.size(); i++) indices[i] = i;

    double total_loss = 0;
    for (int ep = 0; ep < epochs; ep++) {
        std::shuffle(indices.begin(), indices.end(), rng);
        total_loss = 0;
        float ep_lr = lr * (1.0f - 0.5f * ep / epochs);  // decay LR
        for (int idx : indices) {
            total_loss += model.train_step(samples[idx].features, samples[idx].target, ep_lr);
        }
        total_loss /= samples.size();
    }

    return {model, total_loss, (int)samples.size()};
}

// Multi-region training: accepts observations from multiple viewport positions
struct RegionObs {
    std::vector<std::vector<std::vector<int>>> grids;  // [query][y][x] = class
    int vx, vy, vw, vh;
};

inline TrainResult train_from_multi_queries(
    const FeatureMap& fmap,
    const std::vector<RegionObs>& regions,
    std::mt19937& rng,
    int epochs = 15,
    float lr = 0.01f)
{
    MLP model;
    model.init_random(rng);

    struct Sample {
        const float* features;
        int target;
    };
    std::vector<Sample> samples;

    for (auto& region : regions) {
        for (auto& obs : region.grids) {
            for (int y = 0; y < region.vh && y < (int)obs.size(); y++) {
                for (int x = 0; x < region.vw && x < (int)obs[y].size(); x++) {
                    int gy = region.vy + y, gx = region.vx + x;
                    if (gy >= fmap.H || gx >= fmap.W) continue;
                    int cls = obs[y][x];
                    if (cls == CLASS_MOUNTAIN) continue;
                    samples.push_back({fmap.features[gy][gx].f, cls});
                }
            }
        }
    }

    if (samples.empty()) return {model, 999.0, 0};

    std::vector<int> indices(samples.size());
    for (int i = 0; i < (int)indices.size(); i++) indices[i] = i;

    double total_loss = 0;
    for (int ep = 0; ep < epochs; ep++) {
        std::shuffle(indices.begin(), indices.end(), rng);
        total_loss = 0;
        float ep_lr = lr * (1.0f - 0.5f * ep / epochs);
        for (int idx : indices) {
            total_loss += model.train_step(samples[idx].features, samples[idx].target, ep_lr);
        }
        total_loss /= samples.size();
    }

    return {model, total_loss, (int)samples.size()};
}

// Generate full-map prediction from trained MLP
inline ProbTensor predict_full_map(
    const MLP& model,
    const FeatureMap& fmap,
    const std::vector<std::vector<int>>& initial_grid)
{
    int H = fmap.H, W = fmap.W;
    ProbTensor pred(H, std::vector<std::array<double, NUM_CLASSES>>(W));

    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            int t = initial_grid[y][x];
            if (t == TERRAIN_OCEAN) {
                pred[y][x] = {1,0,0,0,0,0};
                continue;
            }
            if (t == TERRAIN_MOUNTAIN) {
                pred[y][x] = {0,0,0,0,0,1};
                continue;
            }

            float out[NUM_CLASSES];
            model.forward(fmap.features[y][x].f, out);
            for (int c = 0; c < NUM_CLASSES; c++)
                pred[y][x][c] = (double)out[c];
        }
    }
    return pred;
}

}  // namespace cell_mlp
