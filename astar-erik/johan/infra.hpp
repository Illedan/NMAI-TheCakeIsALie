#pragma once
#include <vector>
#include <array>
#include <string>
#include <cstdint>

// Grid: raw terrain codes
//   0=Empty  1=Settlement  2=Port  3=Ruin  4=Forest  5=Mountain
//   10=Ocean  11=Plains
using Grid = std::vector<std::vector<int>>;

// Probability grid [y][x][6 classes]:
//   0=Empty(+Ocean+Plains)  1=Settlement  2=Port  3=Ruin  4=Forest  5=Mountain
using ProbGrid = std::vector<std::vector<std::array<double, 6>>>;

// ----------------------------------------------------------------
// Parameter vector — 25 doubles, see comments for each index
// ----------------------------------------------------------------
// Empty -> Settlement:
//   rate = es_base * exp(es_ns*ns + es_ns2*ns^2 + es_sr2*sr2)
//   gating: *= (1 - exp(-es_gate*ns))  if es_gate>0
constexpr int P_ES_BASE     = 0;   // base spawn rate
constexpr int P_ES_NS       = 1;   // linear neighbor boost
constexpr int P_ES_NS2      = 2;   // quadratic neighbor boost
constexpr int P_ES_SR2      = 3;   // radius-2 density boost
constexpr int P_ER_RATIO    = 4;   // Empty->Ruin as fraction of settle rate

// Settlement -> Ruin:
//   rate = sr_base*exp(-sr_sup*(ns+nf_wt*nf)) + sr_raid*ns + sr_ruin*nr + sr_sr2*sr2
constexpr int P_SR_BASE     = 5;   // base collapse rate
constexpr int P_SR_SUP      = 6;   // reduction per allied neighbor
constexpr int P_SR_NF_WT    = 7;   // forest weight as support
constexpr int P_SR_SR2      = 8;   // radius-2 raiding
constexpr int P_SR_RAID     = 9;   // per-neighbor raiding
constexpr int P_SR_RUIN     = 10;  // nearby ruins increase collapse

// Settlement -> Port (coastal only):
//   rate = sp_base + sp_ns*ns
constexpr int P_SP_BASE     = 11;
constexpr int P_SP_NS       = 12;

// Forest -> Settlement:
//   rate = fs_base * exp(fs_ns*ns + fs_ns2*ns^2)
constexpr int P_FS_BASE     = 13;
constexpr int P_FS_NS       = 14;
constexpr int P_FS_NS2      = 15;
constexpr int P_FR_RATIO    = 16;  // Forest->Ruin as fraction of settle rate

// Port -> Ruin:
//   rate = pr_base + pr_ns*ns
constexpr int P_PR_BASE     = 17;
constexpr int P_PR_NS       = 18;

// Ruin transitions (probabilities, will be renormalized):
constexpr int P_RUIN_SETTLE = 19;
constexpr int P_RUIN_EMPTY  = 20;
constexpr int P_RUIN_FOREST = 21;
constexpr int P_RUIN_NS     = 22;  // settlement neighbors boost ruin->settle

// Misc:
constexpr int P_DIST_DECAY  = 23;  // spawn rate *= exp(-dist_decay * bfs_dist)
constexpr int P_ES_GATE     = 24;  // if>0: suppress spontaneous spawn

constexpr int N_PARAMS = 25;

std::vector<double> default_params();
std::vector<double> param_lo();
std::vector<double> param_hi();

// ----------------------------------------------------------------
// Monte Carlo simulator
// ----------------------------------------------------------------
// Runs n_sims independent 50-step simulations from initial_grid.
// Returns per-cell class probability (frequency over simulations).
// Thread-count: uses std::thread::hardware_concurrency().
ProbGrid run_mc(const std::vector<double>& params,
                const Grid& initial_grid,
                int n_sims,
                uint32_t seed);

// ----------------------------------------------------------------
// Data loading
// ----------------------------------------------------------------

// Load initial grid from seed_N.json  ({"grid": [...], ...})
Grid load_initial_grid(const std::string& json_path);

// Scan replays_dir for files matching round_id + seed_index,
// return the final frame (step 50) grid from each replay.
std::vector<Grid> load_replay_finals(const std::string& replays_dir,
                                     const std::string& round_id,
                                     int seed_index);

// Load ground-truth ProbGrid from an analysis JSON file.
// Expects {"ground_truth": [[[float,...], ...], ...], ...}
ProbGrid load_ground_truth(const std::string& json_path);

// ----------------------------------------------------------------
// Scoring  (entropy-weighted KL, same formula as the challenge)
// ----------------------------------------------------------------

// Score prediction against empirical distribution from replay finals.
// Returns 0-100.
double score_vs_replays(const ProbGrid& pred,
                        const Grid& initial_grid,
                        const std::vector<Grid>& finals);

// Score prediction against ground truth ProbGrid. Returns 0-100.
double score_vs_truth(const ProbGrid& pred, const ProbGrid& truth);
