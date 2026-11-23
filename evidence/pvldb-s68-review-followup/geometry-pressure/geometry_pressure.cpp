#define main archived_dyadic_main
#include "run.cpp"
#undef main

int float_sign(const F& f) {
    const double first = (f[0] - f[4]) * (f[3] - f[5]);
    const double second = (f[1] - f[5]) * (f[2] - f[4]);
    return s(first - second);
}

template<int mode> void pressure(int per_mille, int repeat, uint64_t n) {
    uint64_t fallbacks = 0, mismatches = 0;
    std::array<uint64_t, 3> counts{};
    const auto start = std::chrono::steady_clock::now();
    for (uint64_t i = 0; i < n; ++i) {
        const bool hard = i % 1000 < unsigned(per_mille);
        const double m = (hard ? 100000000. : 1024.) + double(i % 23);
        // The hard construction has determinant m(m-2)-(m-1)^2 = -1.
        const F f = hard ? F{m, m-1, m-1, m-2, 0., 0.} : F{m, 0., 0., m, 0., 0.};
        const int label = hard ? -1 : 1;
        int observed;
        if constexpr (mode == 0) {
            observed = float_sign(f);
        } else if constexpr (mode == 1) {
            bool fallback;
            observed = filter_sign(f, fallback);
            fallbacks += fallback;
        } else {
            observed = fixed_exact(f);
        }
        ++counts[observed + 1];
        mismatches += observed != label;
    }
    const auto nanos = std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now() - start).count();
    rusage usage;
    getrusage(RUSAGE_SELF, &usage);
    if constexpr (mode != 0) assert(mismatches == 0);
    if constexpr (mode == 1) assert(fallbacks == (n / 1000) * uint64_t(per_mille));
    std::cout << repeat << ',' << mode << ',' << per_mille << ',' << n << ',' << nanos << ','
              << usage.ru_maxrss << ',' << fallbacks << ',' << mismatches << ','
              << counts[0] << ',' << counts[1] << ',' << counts[2] << '\n';
}

int main(int argc, char** argv) {
    if (argc != 5) return 2;
    assert(std::numeric_limits<double>::is_iec559 && std::fegetround() == FE_TONEAREST);
    const int repeat = std::atoi(argv[1]), mode = std::atoi(argv[2]), per_mille = std::atoi(argv[3]);
    const uint64_t n = std::strtoull(argv[4], nullptr, 10);
    assert(n % 1000 == 0);
    if (mode == 0) pressure<0>(per_mille, repeat, n);
    else if (mode == 1) pressure<1>(per_mille, repeat, n);
    else if (mode == 2) pressure<2>(per_mille, repeat, n);
    else return 2;
}
