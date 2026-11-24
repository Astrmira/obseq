#define main archived_dyadic_main
#include "../pvldb-s68-review-followup/geometry-pressure/run.cpp"
#undef main

using Kernel = int (*)(const F&, bool&);

int plain_sign(const F& f, bool& fallback) {
    fallback = false;
    const double p = (f[0] - f[4]) * (f[3] - f[5]);
    const double q = (f[1] - f[5]) * (f[2] - f[4]);
    return s(p - q);
}

// GCC noipa prevents specialization of the common caller for either kernel.
[[gnu::noipa]] void pressure(Kernel kernel, int mode, int per_mille, int repeat, uint64_t n) {
    uint64_t fallbacks = 0, mismatches = 0;
    std::array<uint64_t, 3> counts{};
    const auto start = std::chrono::steady_clock::now();
    for (uint64_t i = 0; i < n; ++i) {
        const bool hard = i % 1000 < unsigned(per_mille);
        const double m = (hard ? 100000000. : 1024.) + double(i % 23);
        const F f = hard ? F{m, m-1, m-1, m-2, 0., 0.} : F{m, 0., 0., m, 0., 0.};
        bool fallback;
        const int observed = kernel(f, fallback);
        fallbacks += fallback;
        ++counts[observed + 1];
        mismatches += observed != (hard ? -1 : 1);
    }
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now() - start).count();
    rusage usage;
    getrusage(RUSAGE_SELF, &usage);
    const uint64_t hard_count = (n / 1000) * uint64_t(per_mille);
    assert(fallbacks == (mode == 1 ? hard_count : 0));
    assert(mismatches == (mode == 1 ? 0 : hard_count));
    std::cout << repeat << ',' << mode << ',' << per_mille << ',' << n << ',' << elapsed << ','
              << usage.ru_maxrss << ',' << fallbacks << ',' << mismatches << ','
              << counts[0] << ',' << counts[1] << ',' << counts[2] << '\n';
}

int main(int argc, char** argv) {
    if (argc != 5) return 2;
    assert(std::numeric_limits<double>::is_iec559 && std::fegetround() == FE_TONEAREST);
    const int repeat = std::atoi(argv[1]), mode = std::atoi(argv[2]), per_mille = std::atoi(argv[3]);
    const uint64_t n = std::strtoull(argv[4], nullptr, 10);
    if ((mode != 0 && mode != 1) || (per_mille != 1 && per_mille != 10 && per_mille != 100)
        || n == 0 || n % 1000 != 0) return 2;
    pressure(mode == 0 ? plain_sign : filter_sign, mode, per_mille, repeat, n);
}
