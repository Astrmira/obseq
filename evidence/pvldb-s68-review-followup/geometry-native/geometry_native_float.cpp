#define main archived_dyadic_main
#include "run.cpp"
#undef main

void native_float(const std::vector<F>& seeds, const std::vector<char>& oracle, uint64_t n, int repeat) {
    uint64_t seen = 0, mismatches = 0;
    std::array<uint64_t, 3> counts{};
    const auto start = std::chrono::steady_clock::now();
    for (unsigned scale = 0; seen < n; ++scale) {
        assert(scale < 441);
        const double x = std::ldexp(1., int(scale % 21) - 10), y = std::ldexp(1., int(scale / 21) - 10);
        for (size_t i = 0; i < seeds.size() && seen < n; ++i, ++seen) {
            F f = seeds[i];
            for (int axis = 0; axis < 6; ++axis) f[axis] *= axis % 2 ? y : x;
            const double first = (f[0] - f[4]) * (f[3] - f[5]);
            const double second = (f[1] - f[5]) * (f[2] - f[4]);
            const int sign = s(first - second);
            ++counts[sign + 1];
            mismatches += sign + 1 != oracle[i];
        }
    }
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - start).count();
    rusage usage;
    getrusage(RUSAGE_SELF, &usage);
    std::cout << repeat << ",3," << n << ',' << ns << ',' << usage.ru_maxrss << ','
              << counts[0] << ',' << counts[1] << ',' << counts[2] << ",0," << mismatches << ",0\n";
}

int main(int argc, char** argv) {
    if (argc != 5) return 2;
    assert(std::numeric_limits<double>::is_iec559 && std::fegetround() == FE_TONEAREST);
    assert(std::endian::native == std::endian::little);
    std::ifstream source(argv[1], std::ios::binary), labels(argv[2], std::ios::binary);
    std::vector<F> seeds;
    for (F points; source.read(reinterpret_cast<char*>(points.data()), 48);) {
        seeds.push_back(points);
    }
    const std::vector<char> oracle((std::istreambuf_iterator<char>(labels)), {});
    assert(source.eof() && source.gcount() == 0 && seeds.size() == 243727 && oracle.size() == seeds.size());
    const int mode = std::atoi(argv[3]), repeat = std::atoi(argv[4]);
    constexpr uint64_t n = 100000000;
    if (mode == 0) run<0>(seeds, oracle, n, repeat);
    else if (mode == 1) run<1>(seeds, oracle, n, repeat);
    else if (mode == 2) run<2>(seeds, oracle, n, repeat);
    else if (mode == 3) native_float(seeds, oracle, n, repeat);
    else return 2;
}
