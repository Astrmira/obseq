# E3 F7: real date changes survive exact aggregate checks

Use three existing [NOAA OISST v2.1 daily analyses](https://www.ncei.noaa.gov/products/optimum-interpolation-sst), Jan 1, Jan 2 and Feb 1 2025. Only their original packed SST Int16 bands and mask bits, as exposed by native GDAL 3.10.3, are used. Source layout, grid, projection, NoData −999 and position-specific masks are verified identical across these samples. Compare Jan1→Jan2 and Jan2→Feb1 on full fixed aligned 2×2, 4×4, and 8×8 nonoverlapping pixel tiles. This is not a geodesic area, measurement in physical degrees Celsius, or sample of stale production incidents. The dates genuinely differ; the experiment hypothesizes reusing old tiles when a proposed invariant passes, without modifying either input.

A tile is dirty iff at least one valid physical position changes packed value. Dirty positions are the independent exact oracle. The tested summaries are valid mass and sum (equal mean when mass is the same and positive), sum of squares, min/max, and the entire exact positionless bag of valid codes. Independently verify every mass, sum and squared-sum tile for all scales/dates via native aligned GDAL Warp SUM on three explicit numeric planes, a pure positive unit-weight grid. Squares are exact below the integer precision bound for this workload; no general floating Warp accuracy. Bag comparison is exact sorted integers, not a sketch/hash.

| Transition | Tile | Dirty tiles | Missed by mass+sum | Also same squares and extrema | Also same exact bag |
|---|---:|---:|---:|---:|---:|
| Jan 1→Jan 2 | 2×2 | 155,916 | 1,498 | 44 | 44 |
| Jan 1→Jan 2 | 4×4 | 42,095 | 201 | 17 | 17 |
| Jan 1→Jan 2 | 8×8 | 11,436 | 66 | 6 | 5 |
| Jan 2→Feb 1 | 2×2 | 171,812 | 455 | 91 | 91 |
| Jan 2→Feb 1 | 4×4 | 44,727 | 119 | 11 | 8 |
| Jan 2→Feb 1 | 8×8 | 11,694 | 15 | 0 | 0 |

Every dirty matched-sum tile has both positive and negative per-position deltas. Equality of even the complete bag implies equality of every permutation-invariant statistic, but not positional identity. The actual 91 late-pair 2×2 bag collisions hide 194 changed pixel locations; early 8×8 bag collisions hide 10. This is not a fault for a pipeline *only* consuming that verified aggregate. It is a false admission when stale contents are served to a coordinate-addressed downstream observer.

Spatially attaching the same summary to smaller child tiles can materially reduce misses. On the first pair, 66 coarse 8×8 mass+sum misses reduce to seven when all four 4×4 summaries must match; two still pass even exact unpositioned bags per 4×4 child. On the second pair, 15 reduce to two with 4×4 mass+sum, and one survives even checking every 2×2 mass+sum. Finer equality implies coarser equality under additive summaries or bags; conversely, within-child rearrangements remain possible wherever multiple positions share a bucket. That zero bag survivors happened at 2×2 inside these 8×8 tiles cannot establish a universal threshold. For positional reuse, bind row/coordinate identity and exact relevant state, or a proved positional delta receipt. These counts support an information boundary, not a performance or workload incidence estimate.

Replay SHA and native exact result from this folder:
```sh
set -o pipefail
sha256sum -c SHA256SUMS
sha256sum -c SOURCES.sha256
/usr/bin/python3 -IB check.py /tmp/r93-source.nc /tmp/r94-20250102.nc /tmp/r94-20250201.nc | cmp - RESULTS.json
```
No data redistribution, acquisitions, benchmarking or Git writes.
