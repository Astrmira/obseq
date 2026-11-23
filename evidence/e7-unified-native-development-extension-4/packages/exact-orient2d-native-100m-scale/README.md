# E6 O4: fixed-point and certified orientation through 100 million evaluations

Native C++ scalability companion to the exact native-source orientation panel.
Use the identical 243,727 native binary64 boundary wedges from digest-pinned
GDAL inputs. Source panel binary SHA-256:
45d8fd37248476e4f83f0ba6314d49514e308329697e38b763f18e03c7243f19.
An input point can be encoded in signed 128 bits after power-of-two
scaling by exactly 2^58; the code checks exact integral scaling and round
trip. This is true of those admitted coordinates, not arbitrary binary64.
Product magnitudes use exact independent 128×128→256 multiplication
from four 64-bit limb products. Exact sign checks stay within the
admitted bounded grid. An adaptive implementation first applies the
same [published orient2d bound](https://www.cs.cmu.edu/~quake/robust.html),
then invokes the identical exact fallback when the float result is
uncertified. Compile without fast math, disable FP contraction and
check round-to-nearest IEEE binary64 at runtime.

Before timing, every original wedge's C++ fixed-point and filtered
labels agree individually. The complete label buffer's SHA-256 equals
the previously sealed, independently calculated Python dyadic label
buffer; verify against the predecessor's 243727.json. Each of 2,997
authored fallback triples is also checked individually using its known
exact sign. One benchmark repeats the original native input pool;
another additionally replaces every 64th evaluation with a checked
authored hard case. These are not 100M distinct source geometries.
Both scopes return the same sign counts at every repetition.

Measured medians: tiled source 1.814 s fixed-point vs 0.395 s filtered;
pressure 1.901 s vs 0.400 s. Fallback counts 21,744 and 1,583,907
respectively.

Each of the 16 timed calls in RAW.csv performs **100,000,000 individual
evaluations**. Median of four alternating-order calls per method and
workload, same native binary and typed preloaded data. Exact fixed-point
and filter costs exclude input decoding, normalization, panel admission
and validation; they include iteration, predicate and counter update.
Runtime source outputs only counts. Whole worker peak 28,800 KiB.
No native GEOS or Python speed comparison, external I/O, production
hard-case incidence, or full geospatial pipeline claim.

    sha256sum -c SHA256SUMS
    python3 -IB check.py | cmp - RESULT.json
    c++ -std=c++20 -O3 -fno-fast-math -ffp-contract=off run.cpp -o LOCAL_BINARY
    LOCAL_BINARY PINNED_NATIVE_WEDGE_BINARY NEW_LOCAL_LABEL_FILE

To generate the inputs, follow the predecessor's GDAL extraction and
verify its source SHA before running. New timings will vary. No raw
coordinates, input geometry, label buffer or installed artifact
distributed; the signed-predicate label SHA and counts are included.
