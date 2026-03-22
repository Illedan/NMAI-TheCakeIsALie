#include "infra.hpp"
#include <iostream>
#include <algorithm>
#include <random>

// ----------------------------------------------------------------
// Config — edit these
// ----------------------------------------------------------------
static const std::string BASE_DIR  = "../../astar-island";
static const int         ROUND_NUM = 12;  // <-- change this

// Round registry: {uuid, initial_states_subdir, analysis_prefix}
// analysis files: BASE_DIR/analysis/{prefix}seed_N_{uuid}.json
struct RoundInfo { std::string uuid, initial_subdir, analysis_prefix; };
static const RoundInfo ROUNDS[] = {
    {},  // 0-indexed padding
    {"71451d74-be9f-471f-aacd-a41f3b68a9cd", "20260320_120420_71451d74", "round_1_analysis_seed_"},   //  1
    {"76909e29-f664-4b2f-b16b-61b7507277e9", "20260320_120419_76909e29", "round_2_analysis_seed_"},   //  2
    {"f1dac9a9-5cf1-49a9-8f17-d6cb5d5ba5cb", "20260320_120418_f1dac9a9", "round_3_analysis_seed_"},   //  3
    {"8e839974-b13b-407b-a5e7-fc749d877195", "20260320_120417_8e839974", "round_4_analysis_seed_"},   //  4
    {"fd3c92ff-3178-4dc9-8d9b-acf389b3982b", "20260320_120416_fd3c92ff", "round_5_analysis_seed_"},   //  5
    {"ae78003a-4efe-425a-881a-d16a39bca0ad", "20260320_120414_ae78003a", "round_6_analysis_seed_"},   //  6
    {"36e581f1-73f8-453f-ab98-cbe3052b701b", "20260320_133930_36e581f1", "round_7_analysis_seed_"},   //  7
    {"c5cdf100-a876-4fb7-b5d8-757162c97989", "20260320_164120_c5cdf100", "round_8_analysis_seed_"},   //  8
    {"2a341ace-0f57-4309-9b89-e59fe0f09179", "20260320_204043_2a341ace", "round_9_analysis_seed_"},   //  9
    {"75e625c3-60cb-4392-af3e-c86a98bde8c2", "20260320_232944_75e625c3", "round_10_analysis_seed_"},  // 10
    {"324fde07-1670-4202-b199-7aa92ecb40ee", "20260321_023201_324fde07", "round_11_analysis_seed_"},  // 11
    {"795bfb1f-54bd-4f39-a526-9868b36f7ebd", "20260321_054923_795bfb1f", "round_12_analysis_seed_"},  // 12
    {"7b4bda99-6165-4221-97cc-27880f5e6d95", "20260321_085513_7b4bda99", "round_13_analysis_seed_"},  // 13
    {"d0a2c894-2162-4d49-86cf-435b9013f3b8", "20260321_115322_d0a2c894", "round_14_analysis_seed_"},  // 14
    {"cc5442dd-bc5d-418b-911b-7eb960cb0390", "20260321_143924_cc5442dd", "round_15_analysis_seed_"},  // 15
    {"8f664aed-8839-4c85-bed0-77a2cac7c6f5", "20260321_173223_8f664aed", "03_21_18_analysis_seed_"},  // 16
    {"3eb0c25d-28fa-48ca-b8e1-fc249e3918e9", "20260321_204033_3eb0c25d", "03_21_00_analysis_seed_"},  // 17
    {"b0f9d1bf-4b71-4e6e-816c-19c718d29056", "20260321_234212_b0f9d1bf", "03_22_00_analysis_seed_"},  // 18
};

static const std::string ROUND_ID     = ROUNDS[ROUND_NUM].uuid;
static const std::string INITIAL_DIR  = BASE_DIR + "/initial_states/" + ROUNDS[ROUND_NUM].initial_subdir;
static const std::string ANALYSIS_PRE = BASE_DIR + "/analysis/" + ROUNDS[ROUND_NUM].analysis_prefix;
static const std::string ANALYSIS_SUF = "_" + ROUNDS[ROUND_NUM].uuid + ".json";

static const int N_SIMS     = 20;  // MC sims per candidate per seed
static const int POPULATION = 80;
static const int ELITE_K    = 16;
static const int N_ITERS    = 20;

// ----------------------------------------------------------------
// CEM with diagonal Gaussian
// ----------------------------------------------------------------
struct CEM {
    std::vector<double> mu    = default_params();
    std::vector<double> sigma = []{ auto s = param_hi(); auto lo = param_lo();
                                    for (int i=0;i<N_PARAMS;i++) s[i]=(s[i]-lo[i])/4;
                                    return s; }();
    std::vector<double> lo = param_lo();
    std::vector<double> hi = param_hi();

    std::vector<double> sample(std::mt19937& rng) const {
        std::vector<double> p(N_PARAMS);
        for (int i = 0; i < N_PARAMS; i++) {
            std::normal_distribution<double> nd(mu[i], sigma[i]);
            p[i] = std::max(lo[i], std::min(hi[i], nd(rng)));
        }
        return p;
    }

    void update(const std::vector<std::vector<double>>& elites) {
        int K = (int)elites.size();
        for (int i = 0; i < N_PARAMS; i++) {
            double m = 0; for (auto& e : elites) m += e[i]; m /= K;
            double v = 0; for (auto& e : elites) v += (e[i]-m)*(e[i]-m); v /= K;
            mu[i]    = m;
            sigma[i] = std::max(std::sqrt(v), (hi[i]-lo[i]) * 0.005);
        }
    }
};

// ----------------------------------------------------------------
// Main
// ----------------------------------------------------------------
int main() {
    // Load all 5 seeds
    std::vector<Grid>     initials(5);
    std::vector<ProbGrid> truths(5);
    for (int s = 0; s < 5; s++) {
        initials[s] = load_initial_grid(INITIAL_DIR + "/seed_" + std::to_string(s) + ".json");
        truths[s]   = load_ground_truth(ANALYSIS_PRE + std::to_string(s) + ANALYSIS_SUF);
    }

    std::mt19937 rng(42);
    CEM cem;

    for (int iter = 0; iter < N_ITERS; iter++) {
        std::vector<std::vector<double>> candidates(POPULATION);
        for (auto& c : candidates) c = cem.sample(rng);

        std::vector<std::pair<double,int>> scored(POPULATION);
        for (int ci = 0; ci < POPULATION; ci++) {
            double total = 0;
            for (int s = 0; s < 5; s++)
                total += score_vs_truth(run_mc(candidates[ci], initials[s], N_SIMS, rng()), truths[s]);
            scored[ci] = {total / 5, ci};
        }

        std::sort(scored.begin(), scored.end(), [](auto& a, auto& b){ return a.first > b.first; });
        double mean = 0; for (auto& sc : scored) mean += sc.first; mean /= POPULATION;
        std::cerr << "iter " << iter << "  best=" << scored[0].first << "  mean=" << mean << "\n";

        std::vector<std::vector<double>> elites(ELITE_K);
        for (int k = 0; k < ELITE_K; k++) elites[k] = candidates[scored[k].second];
        cem.update(elites);
    }

    // Final scores using the posterior mean
    std::cerr << "\n--- Final (posterior mean) ---\n";
    double avg = 0;
    for (int s = 0; s < 5; s++) {
        double st = score_vs_truth(run_mc(cem.mu, initials[s], 500, rng()), truths[s]);
        std::cerr << "  seed " << s << "  vs_truth=" << st << "\n";
        avg += st;
    }
    std::cerr << "  avg=" << avg/5 << "\n";
}
