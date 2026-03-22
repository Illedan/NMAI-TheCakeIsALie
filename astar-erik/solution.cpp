#include "simulator.h"
#include "hillclimb.h"
#include "cell_mlp.h"
#include "cross_mlp_weights.h"
#include "cross_mlp_local_weights.h"
#include "cross_mlp_diffuse_weights.h"
#include "cross_mlp_collapse_weights.h"
#include "cross_mlp_ext_weights.h"
#include "settle_mlp_weights.h"
#include <queue>

namespace solution {

static int HC_ITERATIONS = 300;
static constexpr int HC_PAD = 3;

// Generic MLP forward pass with given weights
static void mlp_forward_14(const float* feat, int feat_dim, int hidden,
                            const float* w1, const float* b1,
                            const float* w2, const float* b2,
                            const float* w3, const float* b3,
                            double* out, int out_dim) {
    float h1[128], h2[128];  // max hidden=128
    for (int i = 0; i < hidden; i++) {
        float sum = b1[i];
        for (int j = 0; j < feat_dim; j++)
            sum += w1[i * feat_dim + j] * feat[j];
        h1[i] = sum > 0 ? sum : 0;
    }
    for (int i = 0; i < hidden; i++) {
        float sum = b2[i];
        for (int j = 0; j < hidden; j++)
            sum += w2[i * hidden + j] * h1[j];
        h2[i] = sum > 0 ? sum : 0;
    }
    float logits[6];
    float max_l = -1e9f;
    for (int i = 0; i < out_dim; i++) {
        float sum = b3[i];
        for (int j = 0; j < hidden; j++)
            sum += w3[i * hidden + j] * h2[j];
        logits[i] = sum;
        if (sum > max_l) max_l = sum;
    }
    float exp_sum = 0;
    for (int i = 0; i < out_dim; i++) {
        out[i] = std::exp(logits[i] - max_l);
        exp_sum += out[i];
    }
    for (int i = 0; i < out_dim; i++)
        out[i] /= exp_sum;
}

// Cross-round MLP: pre-trained on all ground truth data
// Uses 14 features from initial grid only (no query data needed)
static ProbTensor cross_mlp_predict(const std::vector<std::vector<int>>& grid,
                                     const std::vector<std::vector<int>>& settle_dist) {
    int H = (int)grid.size(), W = (int)grid[0].size();
    ProbTensor pred(H, std::vector<std::array<double, NUM_CLASSES>>(W));

    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            int t = grid[y][x];
            int c = terrain_to_class(t);

            if (t == TERRAIN_OCEAN) {
                pred[y][x] = {1,0,0,0,0,0};
                continue;
            }
            if (c == CLASS_MOUNTAIN) {
                pred[y][x] = {0,0,0,0,0,1};
                continue;
            }

            // Extract 14 features (matching Python training)
            float feat[CROSS_FEAT_DIM];
            for (int i = 0; i < 5; i++) feat[i] = (c == i) ? 1.0f : 0.0f;

            float ns = 0, nf = 0, nr = 0, nm = 0, np = 0;
            int n_land = 0;
            bool has_ocean = false;
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

            feat[5] = ns / 8.0f;
            feat[6] = nf / 8.0f;
            feat[7] = nr / 8.0f;
            feat[8] = sr2 / 16.0f;
            feat[9] = has_ocean ? 1.0f : 0.0f;
            feat[10] = std::min(settle_dist[y][x], 15) / 15.0f;
            feat[11] = nm / 8.0f;
            feat[12] = n_land / 8.0f;
            feat[13] = np / 8.0f;

            // Forward pass through pre-trained MLP
            mlp_forward_14(feat, CROSS_FEAT_DIM, CROSS_HIDDEN,
                          cross_w1, cross_b1, cross_w2, cross_b2,
                          cross_w3, cross_b3, pred[y][x].data(), CROSS_OUT);
        }
    }
    return pred;
}

// Regime-specific MLP predict: uses localized, diffuse, or collapse weights
static ProbTensor regime_mlp_predict(const std::vector<std::vector<int>>& grid,
                                      const std::vector<std::vector<int>>& settle_dist,
                                      double d3d1_ratio,
                                      double growth_ratio = 1.0) {
    int H = (int)grid.size(), W = (int)grid[0].size();
    ProbTensor pred(H, std::vector<std::array<double, NUM_CLASSES>>(W));

    // Determine regime weights
    // Collapse: growth_ratio < 0.5
    // Localized: d3d1 < 0.05 (and not collapse)
    // Diffuse: d3d1 > 0.30 (and not collapse)
    // Blend zone: 0.05 < d3d1 < 0.30
    bool is_collapse = (growth_ratio < 0.5);
    double local_w_blend = 1.0;
    if (is_collapse) {
        local_w_blend = 0.0;  // not used for collapse
    } else {
        if (d3d1_ratio > 0.30) local_w_blend = 0.0;
        else if (d3d1_ratio > 0.05) local_w_blend = 1.0 - (d3d1_ratio - 0.05) / 0.25;
    }
    bool do_blend = (!is_collapse && local_w_blend > 0.01 && local_w_blend < 0.99);

    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            int t = grid[y][x];
            int c = terrain_to_class(t);

            if (t == TERRAIN_OCEAN) { pred[y][x] = {1,0,0,0,0,0}; continue; }
            if (c == CLASS_MOUNTAIN) { pred[y][x] = {0,0,0,0,0,1}; continue; }

            float feat[14];
            for (int i = 0; i < 5; i++) feat[i] = (c == i) ? 1.0f : 0.0f;

            float ns = 0, nf = 0, nr = 0, nm = 0, np = 0;
            int n_land = 0;
            bool has_ocean = false;
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

            feat[5] = ns / 8.0f;
            feat[6] = nf / 8.0f;
            feat[7] = nr / 8.0f;
            feat[8] = sr2 / 16.0f;
            feat[9] = has_ocean ? 1.0f : 0.0f;
            feat[10] = std::min(settle_dist[y][x], 15) / 15.0f;
            feat[11] = nm / 8.0f;
            feat[12] = n_land / 8.0f;
            feat[13] = np / 8.0f;

            if (is_collapse) {
                mlp_forward_14(feat, COLLAPSE_FEAT_DIM, COLLAPSE_HIDDEN,
                              collapse_w1, collapse_b1, collapse_w2, collapse_b2,
                              collapse_w3, collapse_b3, pred[y][x].data(), COLLAPSE_OUT);
            } else if (do_blend) {
                double local_out[6], diffuse_out[6];
                mlp_forward_14(feat, LOCAL_FEAT_DIM, LOCAL_HIDDEN,
                              local_w1, local_b1, local_w2, local_b2,
                              local_w3, local_b3, local_out, LOCAL_OUT);
                mlp_forward_14(feat, DIFFUSE_FEAT_DIM, DIFFUSE_HIDDEN,
                              diffuse_w1, diffuse_b1, diffuse_w2, diffuse_b2,
                              diffuse_w3, diffuse_b3, diffuse_out, DIFFUSE_OUT);
                for (int i = 0; i < NUM_CLASSES; i++)
                    pred[y][x][i] = local_w_blend * local_out[i]
                                  + (1.0 - local_w_blend) * diffuse_out[i];
            } else if (local_w_blend > 0.5) {
                mlp_forward_14(feat, LOCAL_FEAT_DIM, LOCAL_HIDDEN,
                              local_w1, local_b1, local_w2, local_b2,
                              local_w3, local_b3, pred[y][x].data(), LOCAL_OUT);
            } else {
                mlp_forward_14(feat, DIFFUSE_FEAT_DIM, DIFFUSE_HIDDEN,
                              diffuse_w1, diffuse_b1, diffuse_w2, diffuse_b2,
                              diffuse_w3, diffuse_b3, pred[y][x].data(), DIFFUSE_OUT);
            }
        }
    }
    return pred;
}

// Extended cross-round MLP with global features (17 features)
static ProbTensor cross_ext_mlp_predict(const std::vector<std::vector<int>>& grid,
                                          const std::vector<std::vector<int>>& settle_dist) {
    int H = (int)grid.size(), W = (int)grid[0].size();
    ProbTensor pred(H, std::vector<std::array<double, NUM_CLASSES>>(W));

    // Compute global features once
    int g_settle = 0, g_land = 0, g_forest = 0;
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int t = grid[y][x];
            int c = terrain_to_class(t);
            if (t != TERRAIN_OCEAN && c != CLASS_MOUNTAIN) {
                g_land++;
                if (c == CLASS_SETTLEMENT || c == CLASS_PORT) g_settle++;
                else if (c == CLASS_FOREST) g_forest++;
            }
        }
    float settle_density = (float)g_settle / std::max(g_land, 1);
    float forest_ratio = (float)g_forest / std::max(g_land, 1);
    float settle_count_norm = std::min((float)g_settle / 80.0f, 1.0f);

    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            int t = grid[y][x];
            int c = terrain_to_class(t);

            if (t == TERRAIN_OCEAN) { pred[y][x] = {1,0,0,0,0,0}; continue; }
            if (c == CLASS_MOUNTAIN) { pred[y][x] = {0,0,0,0,0,1}; continue; }

            float feat[17];
            for (int i = 0; i < 5; i++) feat[i] = (c == i) ? 1.0f : 0.0f;

            float ns = 0, nf = 0, nr = 0, nm = 0, np = 0;
            int n_land = 0;
            bool has_ocean = false;
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

            feat[5] = ns / 8.0f;
            feat[6] = nf / 8.0f;
            feat[7] = nr / 8.0f;
            feat[8] = sr2 / 16.0f;
            feat[9] = has_ocean ? 1.0f : 0.0f;
            feat[10] = std::min(settle_dist[y][x], 15) / 15.0f;
            feat[11] = nm / 8.0f;
            feat[12] = n_land / 8.0f;
            feat[13] = np / 8.0f;
            // Global features
            feat[14] = settle_density;
            feat[15] = forest_ratio;
            feat[16] = settle_count_norm;

            mlp_forward_14(feat, CROSSEXT_FEAT_DIM, CROSSEXT_HIDDEN,
                          crossext_w1, crossext_b1, crossext_w2, crossext_b2,
                          crossext_w3, crossext_b3, pred[y][x].data(), CROSSEXT_OUT);
        }
    }
    return pred;
}

// Settle MLP: 17 features (14 local + 3 global: log_growth, d3d1, ruin_frac)
static ProbTensor settle_mlp_predict(const std::vector<std::vector<int>>& grid,
                                      const std::vector<std::vector<int>>& settle_dist,
                                      double growth_ratio, double d3d1_ratio,
                                      double ruin_frac = 0.01) {
    int H = (int)grid.size(), W = (int)grid[0].size();

    float global_feats[3] = {
        (float)(std::log(1.0 + growth_ratio) / std::log(16.0)),  // log-scaled, 0-1
        (float)std::min(d3d1_ratio, 1.0),
        (float)std::min(ruin_frac * 10.0, 1.0),  // scale ruin_frac to 0-1
    };
    ProbTensor pred(H, std::vector<std::array<double, NUM_CLASSES>>(W));

    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            int t = grid[y][x];
            int c = terrain_to_class(t);

            if (t == TERRAIN_OCEAN) { pred[y][x] = {1,0,0,0,0,0}; continue; }
            if (c == CLASS_MOUNTAIN) { pred[y][x] = {0,0,0,0,0,1}; continue; }

            float feat[SETTLE_FEAT_DIM];
            for (int i = 0; i < 5; i++) feat[i] = (c == i) ? 1.0f : 0.0f;

            float ns = 0, nf = 0, nr = 0, nm = 0, np = 0;
            int n_land = 0;
            bool has_ocean = false;
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

            feat[5] = ns / 8.0f;
            feat[6] = nf / 8.0f;
            feat[7] = nr / 8.0f;
            feat[8] = sr2 / 16.0f;
            feat[9] = has_ocean ? 1.0f : 0.0f;
            feat[10] = std::min(settle_dist[y][x], 15) / 15.0f;
            feat[11] = nm / 8.0f;
            feat[12] = n_land / 8.0f;
            feat[13] = np / 8.0f;
            // Global features: log_growth, d3d1, ruin_frac
            feat[14] = global_feats[0];
            feat[15] = global_feats[1];
            feat[16] = global_feats[2];

            mlp_forward_14(feat, SETTLE_FEAT_DIM, SETTLE_HIDDEN,
                          settle_w1, settle_b1, settle_w2, settle_b2,
                          settle_w3, settle_b3, pred[y][x].data(), SETTLE_OUT);
        }
    }
    return pred;
}

void set_fast_mode(bool fast) {
    if (fast) {
        HC_ITERATIONS = 500;
    } else {
        HC_ITERATIONS = 500;
    }
}

// Score a potential viewport position based on initial grid content
static double score_tile(const std::vector<std::vector<int>>& grid,
                         int vx, int vy, int vw, int vh) {
    int H = (int)grid.size(), W = (int)grid[0].size();
    double score = 0;
    int ocean_count = 0;
    bool has_coastal = false;
    int settle_count = 0, forest_count = 0;

    for (int y = vy; y < vy + vh && y < H; y++) {
        for (int x = vx; x < vx + vw && x < W; x++) {
            int t = grid[y][x];
            if (t == TERRAIN_OCEAN) { ocean_count++; continue; }
            if (t == TERRAIN_MOUNTAIN) continue;
            if (t == TERRAIN_SETTLEMENT || t == TERRAIN_PORT) {
                settle_count++; score += 3.0;
            } else if (t == TERRAIN_FOREST) {
                forest_count++; score += 1.5;
            } else if (t == TERRAIN_RUIN) {
                score += 2.0;
            } else {
                score += 0.5;
            }
            for (int dy = -1; dy <= 1 && !has_coastal; dy++)
                for (int dx = -1; dx <= 1 && !has_coastal; dx++) {
                    int ny = y+dy, nx = x+dx;
                    if (ny >= 0 && ny < H && nx >= 0 && nx < W
                        && grid[ny][nx] == TERRAIN_OCEAN)
                        has_coastal = true;
                }
        }
    }

    double ocean_frac = (double)ocean_count / (vw * vh);
    if (ocean_frac > 0.5) return 0;
    score *= (1.0 - ocean_frac);
    if (has_coastal) score *= 1.3;
    if (settle_count > 0 && forest_count > 0) score *= 1.2;
    return score;
}

static std::pair<int, int> find_best_tile(
    const std::vector<std::vector<int>>& grid) {
    int H = (int)grid.size(), W = (int)grid[0].size();
    int vw = std::min(MAX_VIEWPORT, W);
    int vh = std::min(MAX_VIEWPORT, H);

    int bx = 1, by = 1;
    double best = -1;
    // Start at 1 to skip ocean border row/column
    for (int vy = 1; vy <= H - vh - 1; vy++)
        for (int vx = 1; vx <= W - vw - 1; vx++) {
            double s = score_tile(grid, vx, vy, vw, vh);
            if (s > best) { best = s; bx = vx; by = vy; }
        }
    return {bx, by};
}

// Public wrappers for cross-seed tile selection
std::pair<int, int> find_best_query_tile(const std::vector<std::vector<int>>& grid) {
    return find_best_tile(grid);
}

double score_query_tile(const std::vector<std::vector<int>>& grid, int vx, int vy) {
    int W = (int)grid[0].size(), H = (int)grid.size();
    int vw = std::min(MAX_VIEWPORT, W);
    int vh = std::min(MAX_VIEWPORT, H);
    return score_tile(grid, vx, vy, vw, vh);
}

// Find the viewport position with highest average prediction entropy
static std::pair<int, int> find_highest_entropy_tile(
    const ProbTensor& mc_pred,
    const std::vector<std::vector<int>>& initial_grid,
    const std::vector<std::vector<int>>& obs_total,
    int vw, int vh) {
    int H = (int)mc_pred.size(), W = (int)mc_pred[0].size();

    int bx = 1, by = 1;
    double best = -1;
    // Start at 1 to skip ocean border
    for (int vy = 1; vy <= H - vh - 1; vy++) {
        for (int vx = 1; vx <= W - vw - 1; vx++) {
            double entropy_sum = 0;
            int count = 0;
            for (int y = vy; y < vy + vh; y++) {
                for (int x = vx; x < vx + vw; x++) {
                    int t = initial_grid[y][x];
                    if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
                    if (obs_total[y][x] >= 5) continue;
                    double h = 0;
                    for (int c = 0; c < NUM_CLASSES; c++) {
                        double p = mc_pred[y][x][c];
                        if (p > 0.001) h -= p * std::log(p);
                    }
                    entropy_sum += h;
                    count++;
                }
            }
            if (count > vw * vh / 4) {  // require at least 25% land
                double avg = entropy_sum / count;
                if (avg > best) { best = avg; bx = vx; by = vy; }
            }
        }
    }
    return {bx, by};
}

// Helper: run queries to a tile and accumulate observations
static void query_tile(int tx, int ty, int vw, int vh, int n_queries,
                       int H, int W,
                       QueryFn& query_fn,
                       std::vector<std::vector<std::array<int, NUM_CLASSES>>>& obs_counts,
                       std::vector<std::vector<int>>& obs_total,
                       std::vector<std::vector<std::vector<int>>>* hc_grids = nullptr,
                       int* hc_vx = nullptr, int* hc_vy = nullptr,
                       int* hc_vw = nullptr, int* hc_vh = nullptr,
                       ::cell_mlp::RegionObs* region_out = nullptr) {
    for (int q = 0; q < n_queries; q++) {
        ViewportResult vr = query_fn(tx, ty, vw, vh);

        for (int y = 0; y < vr.vh; y++)
            for (int x = 0; x < vr.vw; x++) {
                int gy = vr.vy + y, gx = vr.vx + x;
                int cls = terrain_to_class(vr.grid[y][x]);
                if (gy < H && gx < W) {
                    obs_counts[gy][gx][cls]++;
                    obs_total[gy][gx]++;
                }
            }

        // Build class-converted grid for both HC and MLP training
        std::vector<std::vector<int>> obs_grid(vr.vh, std::vector<int>(vr.vw));
        for (int y = 0; y < vr.vh; y++)
            for (int x = 0; x < vr.vw; x++)
                obs_grid[y][x] = terrain_to_class(vr.grid[y][x]);

        if (hc_grids) {
            hc_grids->push_back(obs_grid);
            if (q == 0 && hc_vx) {
                *hc_vx = vr.vx; *hc_vy = vr.vy;
                *hc_vw = vr.vw; *hc_vh = vr.vh;
            }
        }

        if (region_out) {
            if (q == 0) {
                region_out->vx = vr.vx; region_out->vy = vr.vy;
                region_out->vw = vr.vw; region_out->vh = vr.vh;
            }
            region_out->grids.push_back(std::move(obs_grid));
        }
    }
}

ProbTensor predict(const InitialState& initial,
                   int /*seed_index*/,
                   int queries_available,
                   QueryFn query_fn,
                   std::mt19937& rng,
                   SharedState* shared) {
    int H = (int)initial.grid.size(), W = (int)initial.grid[0].size();
    int vw = std::min(MAX_VIEWPORT, W);
    int vh = std::min(MAX_VIEWPORT, H);

    std::vector<std::vector<std::array<int, NUM_CLASSES>>> obs_counts(
        H, std::vector<std::array<int, NUM_CLASSES>>(W, {0,0,0,0,0,0}));
    std::vector<std::vector<int>> obs_total(H, std::vector<int>(W, 0));

    std::vector<std::vector<std::vector<int>>> hc_grids;
    int hc_vx = 0, hc_vy = 0, hc_vw = 0, hc_vh = 0;

    // Collect all query observations for MLP training (multi-region)
    std::vector<::cell_mlp::RegionObs> all_regions;

    ProbTensor mc_pred;
    double growth_ratio = 1.0;
    double hc_fit = 100.0;  // HC model fit quality (100 = perfect)
    double d3d1_ratio = 1.0;  // settlement localization ratio
    solution::DistProfile dist_prof = {};
    std::vector<simulator::TuneParams> top_k_params;  // top-K from HC/EDA


    // Pre-compute BFS distance from initial settlements (needed for d3/d1 and decay)
    std::vector<std::vector<int>> settle_dist(H, std::vector<int>(W, 999));
    {
        std::queue<std::pair<int,int>> bfs;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                int t = initial.grid[y][x];
                if (t == TERRAIN_SETTLEMENT || t == TERRAIN_PORT || t == TERRAIN_RUIN) {
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

    if (queries_available > 0) {
        // Phase 1: queries on best tile (for HC if enough queries)
        bool run_hc = (queries_available >= 15);
        // In local mode: save some queries for phase 2 diversity
        // In online mode: all queries come from same position, so use all for phase 1
        int phase1 = run_hc ? std::min(25, queries_available) : queries_available;
        int remaining = queries_available - phase1;
        auto [tx, ty] = find_best_tile(initial.grid);

        ::cell_mlp::RegionObs phase1_region;
        query_tile(tx, ty, vw, vh, phase1, H, W,
                   query_fn, obs_counts, obs_total,
                   &hc_grids, &hc_vx, &hc_vy, &hc_vw, &hc_vh,
                   &phase1_region);
        all_regions.push_back(phase1_region);

        // Compute growth ratio + run HC (only if enough queries)
        if (run_hc && !hc_grids.empty()) {
            int init_s = 0, land = 0, obs_s_total = 0;
            for (int y = 0; y < hc_vh; y++)
                for (int x = 0; x < hc_vw; x++) {
                    int gy = hc_vy + y, gx = hc_vx + x;
                    if (gy >= H || gx >= W) continue;
                    int t = initial.grid[gy][gx];
                    if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
                    land++;
                    int ic = terrain_to_class(t);
                    if (ic == CLASS_SETTLEMENT || ic == CLASS_PORT) init_s++;
                }
            for (auto& obs : hc_grids)
                for (int y = 0; y < (int)obs.size() && y < hc_vh; y++)
                    for (int x = 0; x < (int)obs[y].size() && x < hc_vw; x++) {
                        int c = obs[y][x];
                        if (c == CLASS_SETTLEMENT || c == CLASS_PORT) obs_s_total++;
                    }
            double init_frac = land > 0 ? (double)init_s / land : 0;
            double obs_frac = land > 0 ? (double)obs_s_total / (land * hc_grids.size()) : 0;
            growth_ratio = (init_frac > 0.01) ? obs_frac / init_frac : 1.0;

            // Compute d3/d1 ratio AND full distance-based class profile
            {
                std::array<std::array<int, NUM_CLASSES>, MAX_DIST_PROFILE> class_at_d = {};
                std::array<int, MAX_DIST_PROFILE> total_at_d = {};
                for (auto& obs : hc_grids) {
                    for (int y = 0; y < (int)obs.size() && y < hc_vh; y++)
                        for (int x = 0; x < (int)obs[y].size() && x < hc_vw; x++) {
                            int gy = hc_vy + y, gx = hc_vx + x;
                            if (gy >= H || gx >= W) continue;
                            int t = initial.grid[gy][gx];
                            if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
                            int d = std::min(settle_dist[gy][gx], MAX_DIST_PROFILE - 1);
                            total_at_d[d]++;
                            int c = obs[y][x];
                            if (c >= 0 && c < NUM_CLASSES)
                                class_at_d[d][c]++;
                        }
                }
                // Compute fractions
                for (int d = 0; d < MAX_DIST_PROFILE; d++) {
                    if (total_at_d[d] > 0) {
                        for (int c = 0; c < NUM_CLASSES; c++)
                            dist_prof[d][c] = (double)class_at_d[d][c] / total_at_d[d];
                    }
                }
                double frac_d1 = dist_prof[1][CLASS_SETTLEMENT] + dist_prof[1][CLASS_PORT];
                double frac_d3 = dist_prof[3][CLASS_SETTLEMENT] + dist_prof[3][CLASS_PORT];
                d3d1_ratio = (frac_d1 > 0.01) ? frac_d3 / frac_d1 : 1.0;
                if (shared) {
                    shared->d3d1_ratio = d3d1_ratio;
                    shared->dist_profile = dist_prof;
                    shared->has_dist_profile = true;
                }
            }

            // Distance-based settlement rate decay for localized rounds
            double dist_decay_val = 0.0;
            if (d3d1_ratio < 0.3) {
                double locality = 1.0 - d3d1_ratio / 0.3;
                if (d3d1_ratio < 0.05) {
                    dist_decay_val = 0.30 * locality;  // steep for extreme localization
                } else {
                    dist_decay_val = 0.08 * locality;
                }
            }

            // Select regime-specific starting params based on growth ratio
            simulator::TuneParams regime_start;
            if (growth_ratio < 0.5) {
                regime_start = simulator::collapse_defaults();
            } else if (growth_ratio > 1.2) {
                regime_start = simulator::growth_defaults();
            } else {
                regime_start = simulator::TuneParams();
            }

            // Phase A: Quick HC to find a good starting point
            auto hc_result = hillclimb::optimize(
                hc_grids, hc_vx, hc_vy, hc_vw, hc_vh,
                initial.grid, 300, HC_PAD, rng,
                &regime_start, 0, dist_decay_val);

            // Phase B: EDA refinement seeded from HC result
            auto eda_result = hillclimb::optimize_eda(
                hc_grids, hc_vx, hc_vy, hc_vw, hc_vh,
                initial.grid,
                64,    // population size
                30,    // generations
                0.5,   // kill ratio (bottom 50%)
                rng, HC_PAD, dist_decay_val,
                &hc_result.best);

            // Pick the better result
            if (!eda_result.top_k_scores.empty() && !hc_result.top_k_scores.empty()
                && eda_result.top_k_scores[0] > hc_result.top_k_scores[0]) {
                hc_result = eda_result;
            }

            simulator::TuneParams tuned = hc_result.best;
            simulator::tune = tuned;
            top_k_params = hc_result.top_k;

            // Evaluate HC fit quality: score the tuned model against empirical
            ProbTensor hc_eval = simulator::mean_field(initial.grid);
            hc_fit = 0;
            {
                int n_obs_cells = 0;
                double total_kl = 0, total_w = 0;
                for (int y = 0; y < hc_vh; y++)
                    for (int x = 0; x < hc_vw; x++) {
                        int gy = hc_vy + y, gx = hc_vx + x;
                        if (gy >= H || gx >= W) continue;
                        int t = initial.grid[gy][gx];
                        if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
                        n_obs_cells++;
                        // Compute empirical distribution
                        std::array<double, NUM_CLASSES> emp = {0,0,0,0,0,0};
                        int n = obs_total[gy][gx];
                        if (n == 0) continue;
                        for (int c = 0; c < NUM_CLASSES; c++)
                            emp[c] = (double)obs_counts[gy][gx][c] / n;
                        // KL(emp || model)
                        double h = 0;
                        for (int c = 0; c < NUM_CLASSES; c++) {
                            double pi = std::max(emp[c], 0.001);
                            h -= pi * std::log(pi);
                        }
                        double w = std::max(h, 0.01);
                        double kl = 0;
                        for (int c = 0; c < NUM_CLASSES; c++) {
                            double pi = std::max(emp[c], 0.01);
                            double qi = std::max(hc_eval[gy][gx][c], 0.01);
                            kl += pi * std::log(pi / qi);
                        }
                        total_kl += w * kl;
                        total_w += w;
                    }
                hc_fit = total_w > 0 ? 100.0 * std::exp(-3.0 * total_kl / total_w) : 0;
            }

            std::cerr << "HC: es=" << tuned.es_base
                      << " ns=" << tuned.es_ns_coeff
                      << " sr=" << tuned.sr_base
                      << " sp=" << tuned.sp_base
                      << " fs=" << tuned.fs_base
                      << " rs=" << tuned.ruin_settle
                      << " re=" << tuned.ruin_empty
                      << " vb=" << tuned.mf_var_boost
                      << " dd=" << tuned.dist_decay
                      << " ng=" << tuned.es_ns_gate
                      << " gr=" << growth_ratio
                      << " fit=" << hc_fit
                      << " d3d1=" << d3d1_ratio
                      << "\n";

            // Share hc_fit and growth_ratio with other seeds
            if (shared) {
                shared->hc_fit = hc_fit;
                shared->growth_ratio = growth_ratio;
            }
        }

        // Phase 2+: diversity + entropy-based tiles
        if (remaining > 0) {
            mc_pred = simulator::mean_field(initial.grid);

            // First batch: query the tile with least overlap with phase 1
            // (force spatial diversity for better correction factors)
            if (remaining >= 5) {
                int batch = std::min(5, remaining);
                remaining -= batch;
                // Find tile that maximizes distance from phase 1 tile center
                // weighted by entropy (diversity + informativeness)
                int cx1 = tx + vw/2, cy1 = ty + vh/2;
                int bx2 = 1, by2 = 1;
                double best2 = -1;
                for (int vy2 = 1; vy2 <= H - vh - 1; vy2++) {
                    for (int vx2 = 1; vx2 <= W - vw - 1; vx2++) {
                        // Distance from phase 1 center
                        int cx2 = vx2 + vw/2, cy2 = vy2 + vh/2;
                        double dist = std::sqrt((cx2-cx1)*(cx2-cx1) + (cy2-cy1)*(cy2-cy1));

                        // Entropy of unobserved cells
                        double entropy_sum = 0;
                        int count = 0;
                        for (int y = vy2; y < vy2 + vh; y++)
                            for (int x = vx2; x < vx2 + vw; x++) {
                                int t = initial.grid[y][x];
                                if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
                                if (obs_total[y][x] >= 5) continue;
                                double h = 0;
                                for (int c = 0; c < NUM_CLASSES; c++) {
                                    double p = mc_pred[y][x][c];
                                    if (p > 0.001) h -= p * std::log(p);
                                }
                                entropy_sum += h;
                                count++;
                            }
                        if (count > vw * vh / 4) {  // require at least 25% land
                            double avg_ent = entropy_sum / count;
                            double score = avg_ent * (1.0 + 0.10 * dist);  // entropy + diversity bonus
                            if (score > best2) { best2 = score; bx2 = vx2; by2 = vy2; }
                        }
                    }
                }
                ::cell_mlp::RegionObs p2_region;
                query_tile(bx2, by2, vw, vh, batch, H, W,
                           query_fn, obs_counts, obs_total,
                           nullptr, nullptr, nullptr, nullptr, nullptr,
                           &p2_region);
                all_regions.push_back(p2_region);
            }

            // Remaining batches: pure entropy chasing
            while (remaining > 0) {
                int batch = std::min(5, remaining);
                remaining -= batch;
                auto [ex, ey] = find_highest_entropy_tile(mc_pred, initial.grid, obs_total, vw, vh);
                ::cell_mlp::RegionObs ent_region;
                query_tile(ex, ey, vw, vh, batch, H, W,
                           query_fn, obs_counts, obs_total,
                           nullptr, nullptr, nullptr, nullptr, nullptr,
                           &ent_region);
                all_regions.push_back(ent_region);
            }
        }
    }

    // Load shared state if we didn't compute it ourselves
    bool has_dist_prof = false;
    if (queries_available == 0 && shared) {
        if (shared->hc_fit > 0) hc_fit = shared->hc_fit;
        d3d1_ratio = shared->d3d1_ratio;
        growth_ratio = shared->growth_ratio;
        if (d3d1_ratio < 0.3) {
            double locality = 1.0 - d3d1_ratio / 0.3;
            if (d3d1_ratio < 0.05) {
                simulator::tune.dist_decay = 0.30 * locality;
            } else {
                simulator::tune.dist_decay = 0.08 * locality;
            }
        }
        if (shared->has_dist_profile) {
            dist_prof = shared->dist_profile;
            has_dist_prof = true;
        }
    } else if (queries_available > 0) {
        // dist_prof was computed above during d3d1 computation
        has_dist_prof = true;
    }

    // Final prediction: use MC for accuracy (MF used only during HC for speed)
    {
        std::mt19937 mc_rng(12345);
        mc_pred = simulator::monte_carlo(initial.grid, 3000, mc_rng);
    }

    // Train cell MLP from query observations and blend with MF prediction
    {
        ::cell_mlp::FeatureMap fmap;
        fmap.build(initial.grid, initial.settlements);

        ::cell_mlp::MLP* mlp_to_use = nullptr;
        double mlp_loss = 999;

        if (queries_available >= 15 && !all_regions.empty()) {
            // Train MLP on all query regions (multi-viewport)
            auto mlp_result = ::cell_mlp::train_from_multi_queries(
                fmap, all_regions, rng, 30, 0.008f);

            if (mlp_result.n_samples > 100) {
                // Store for sharing with other seeds
                static ::cell_mlp::MLP shared_mlp;
                shared_mlp = mlp_result.model;
                mlp_to_use = &shared_mlp;
                mlp_loss = mlp_result.final_loss;

                if (shared) {
                    shared->trained_mlp = (void*)&shared_mlp;
                    shared->has_mlp = true;
                }

                std::cerr << "MLP: loss=" << mlp_loss
                          << " n=" << mlp_result.n_samples << "\n";
            }
        } else if (shared && shared->has_mlp && shared->trained_mlp) {
            // Use MLP from query seed
            mlp_to_use = (::cell_mlp::MLP*)shared->trained_mlp;
            mlp_loss = 0.5;  // assume reasonable
        }

        if (mlp_to_use) {
            ProbTensor mlp_pred = ::cell_mlp::predict_full_map(
                *mlp_to_use, fmap, initial.grid);

            // Blend: MLP gets more weight when MF fit is poor
            double mlp_w = std::max(0.1, std::min(0.4, (100.0 - hc_fit) / 100.0));
            // Non-query seeds: slightly less MLP weight since features differ
            if (queries_available == 0) mlp_w *= 0.7;
            double mf_w = 1.0 - mlp_w;

            for (int y = 0; y < H; y++)
                for (int x = 0; x < W; x++) {
                    int t = initial.grid[y][x];
                    if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
                    for (int c = 0; c < NUM_CLASSES; c++)
                        mc_pred[y][x][c] = mf_w * mc_pred[y][x][c] + mlp_w * mlp_pred[y][x][c];
                }
        }
    }

    // Estimate ruin_frac from MF prediction (avg ruin probability over land cells)
    double ruin_frac = 0.01;
    {
        double ruin_sum = 0;
        int land_count = 0;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                int t = initial.grid[y][x];
                if (t == TERRAIN_OCEAN || terrain_to_class(t) == CLASS_MOUNTAIN) continue;
                ruin_sum += mc_pred[y][x][CLASS_RUIN];
                land_count++;
            }
        if (land_count > 0) ruin_frac = ruin_sum / land_count;
    }

    // Blend with cross-round MLP prior (settle MLP with log_growth + d3d1 + ruin_frac)
    {
        ProbTensor cross_pred = settle_mlp_predict(initial.grid, settle_dist, growth_ratio, d3d1_ratio, ruin_frac);
        double cross_w = 0.80 + 0.12 * std::max(0.0, (80.0 - hc_fit) / 20.0);
        cross_w = std::min(cross_w, 0.92);
        // For very localized rounds, reduce MLP weight — HC-tuned sim with dist_decay
        // is more specific to this round's pattern
        if (d3d1_ratio < 0.1 && d3d1_ratio >= 0 && growth_ratio > 0.5) {
            cross_w *= 0.7;
        }
        double mf_w = 1.0 - cross_w;
        for (int y = 0; y < H; y++)
            for (int x = 0; x < W; x++) {
                int t = initial.grid[y][x];
                if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
                for (int c = 0; c < NUM_CLASSES; c++)
                    mc_pred[y][x][c] = mf_w * mc_pred[y][x][c] + cross_w * cross_pred[y][x][c];
            }
    }

    std::cerr << "MF gr=" << growth_ratio << " d3d1=" << d3d1_ratio
              << " ruin=" << ruin_frac << "\n";

    // Compute correction factors (global + per-distance)
    CorrectionFactors correction = {1,1,1,1,1,1};
    solution::DistCorrection dist_correction;
    for (auto& dc : dist_correction) dc = {1,1,1,1,1,1};
    bool have_dist_correction = false;

    std::array<double, NUM_CLASSES> mc_sum = {0,0,0,0,0,0};
    std::array<double, NUM_CLASSES> obs_sum = {0,0,0,0,0,0};
    int calib_cells = 0;

    // Also accumulate per-distance stats
    std::array<std::array<double, NUM_CLASSES>, solution::N_DIST_BUCKETS> mc_sum_d = {};
    std::array<std::array<double, NUM_CLASSES>, solution::N_DIST_BUCKETS> obs_sum_d = {};
    std::array<int, solution::N_DIST_BUCKETS> calib_cells_d = {};

    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            if (obs_total[y][x] < 5) continue;
            int t = initial.grid[y][x];
            if (t == TERRAIN_OCEAN || t == TERRAIN_MOUNTAIN) continue;
            calib_cells++;
            double inv_n = 1.0 / obs_total[y][x];
            int db = std::min(settle_dist[y][x], solution::N_DIST_BUCKETS - 1);
            calib_cells_d[db]++;
            for (int c = 0; c < NUM_CLASSES; c++) {
                mc_sum[c] += mc_pred[y][x][c];
                obs_sum[c] += obs_counts[y][x][c] * inv_n;
                mc_sum_d[db][c] += mc_pred[y][x][c];
                obs_sum_d[db][c] += obs_counts[y][x][c] * inv_n;
            }
        }

    if (calib_cells > 10) {
        for (int c = 0; c < NUM_CLASSES; c++) {
            double mc_avg = mc_sum[c] / calib_cells;
            if (mc_avg > 0.002)
                correction[c] = std::max(0.1, std::min(15.0,
                    (obs_sum[c] / calib_cells) / mc_avg));
        }

        // Override correction when HC overfit causes settlement correction < 1 despite high growth
        if (growth_ratio > 1.5 && correction[CLASS_SETTLEMENT] < 1.0) {
            correction[CLASS_SETTLEMENT] = 1.0;
            correction[CLASS_EMPTY] = std::min(correction[CLASS_EMPTY], 1.0);
        }

        // Save unclamped global corrections for per-distance blending
        CorrectionFactors unclamped_correction = correction;

        // Smooth extreme corrections — avoid over-trusting viewport-local statistics
        for (int c = 0; c < NUM_CLASSES; c++) {
            if (c == CLASS_MOUNTAIN) continue;
            double lo = 0.6, hi = 1.8;
            if (c == CLASS_RUIN) lo = 0.8;
            correction[c] = std::max(lo, std::min(hi, correction[c]));
        }

        // Compute per-distance corrections (blend with unclamped global)
        for (int db = 0; db < solution::N_DIST_BUCKETS; db++) {
            if (calib_cells_d[db] >= 5) {
                for (int c = 0; c < NUM_CLASSES; c++) {
                    double mc_avg_d = mc_sum_d[db][c] / calib_cells_d[db];
                    if (mc_avg_d > 0.002) {
                        double raw = (obs_sum_d[db][c] / calib_cells_d[db]) / mc_avg_d;
                        raw = std::max(0.1, std::min(10.0, raw));
                        // Close to initial settlements: trust distance-specific more
                        double dist_w = (db <= 1) ? 0.85 : 0.6;
                        // Use unclamped global for blending, then clamp the result
                        double blended = dist_w * raw + (1.0 - dist_w) * unclamped_correction[c];
                        dist_correction[db][c] = std::max(0.1, std::min(10.0, blended));
                    } else {
                        dist_correction[db][c] = correction[c];
                    }
                }
                have_dist_correction = true;
            } else {
                dist_correction[db] = correction;
            }
        }

        if (shared) {
            shared->correction = correction;
            shared->dist_correction = dist_correction;
            shared->has_dist_correction = have_dist_correction;
        }
        // Share observations for non-query seeds
        if (shared && queries_available > 0) {
            shared->shared_obs_counts = obs_counts;
            shared->shared_obs_total = obs_total;
            shared->has_shared_obs = true;
        }
    } else if (shared) {
        correction = shared->correction;
        if (shared->has_dist_correction) {
            dist_correction = shared->dist_correction;
            have_dist_correction = true;
        }
    }

    // settle_dist already computed above

    // Build prediction: blend model with observations
    ProbTensor pred(H, std::vector<std::array<double, NUM_CLASSES>>(W));

    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            int n_obs = obs_total[y][x];

            // Select correction factors (per-distance if available, else global)
            int db = std::min(settle_dist[y][x], solution::N_DIST_BUCKETS - 1);
            const CorrectionFactors& corr = have_dist_correction ? dist_correction[db] : correction;

            if (n_obs >= 5) {
                // Observed cell: blend empirical + model (Dirichlet posterior)
                double mc_w = std::max(15.0, 70.0 * (hc_fit / 80.0));
                // For localized rounds, trust observations more (model is less reliable)
                if (d3d1_ratio < 0.1 && d3d1_ratio >= 0) mc_w *= 0.5;
                double total = mc_w + n_obs;
                for (int c = 0; c < NUM_CLASSES; c++) {
                    double mc_c = mc_pred[y][x][c] * corr[c];
                    pred[y][x][c] = (mc_w * mc_c + obs_counts[y][x][c]) / total;
                }
            } else {
                // Unobserved: model with correction
                for (int c = 0; c < NUM_CLASSES; c++)
                    pred[y][x][c] = mc_pred[y][x][c] * corr[c];

                double total = 0;
                for (int c = 0; c < NUM_CLASSES; c++) total += pred[y][x][c];
                if (total > 0)
                    for (int c = 0; c < NUM_CLASSES; c++)
                        pred[y][x][c] /= total;
            }
        }
    }

    infra::normalize_with_floor(pred, initial.grid);
    return pred;
}

}  // namespace solution
