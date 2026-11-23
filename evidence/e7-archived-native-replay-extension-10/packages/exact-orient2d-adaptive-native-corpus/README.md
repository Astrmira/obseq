# E6 O4: exact binary64 orientation with audited adaptive fallback

Use 243,727 consecutive boundary wedges from digest-pinned, unchanged
Natural Earth country geometry and the Liechtenstein OSM polygon layers.
Native GDAL 3.10.3 extraction keeps the exact delivered binary64 coordinates,
including genuine repeated/degenerate constructions. No interpretation as
geodesic orientation or claim about these boundary data's spatial accuracy.
The physical polygon feature distribution is not a trial distribution.

The target is the sign of the determinant of the **exact values represented
by the delivered floats**. Reuse [Shewchuk's first orient2d error bound](https://www.cs.cmu.edu/~quake/robust.html)
with the absolute sum of the two products as a conservative permanent.
A strict certified sign accepts immediately; any other result falls back
to dyadic integer arithmetic after aligning the two coordinate denominators.
On the admitted bounded grid (absolute coordinate ≤10^8, power-of-two
denominator ≤2^200), any nonzero coordinate difference and its nonzero
product stay away from binary64 underflow and overflow. No claim is made
for arbitrary floating environments, CRS input uncertainty, floating
infinities, signed-bit equivalence, or polygon Boolean operations.
A separate exact Fraction predicate in a different origin checks a fixed
stride of the native data and 300 constructed cancellation/zero controls.

Across the entire native 243,727-wedge sequence, 53 signs require the
conservative fallback, and **zero** plain binary64 sign mismatches and
zero native GEOS 3.13.1 orientation-index mismatches are observed against
the exact oracle. These are explicit zeros, not borrowed fault rates.
In the 300 authored nonzero/zero cases, ordinary floating orientation
does lose signs while the tested GEOS and exact filtered predicates
agree. GEOS is an actual C API run via `GEOSOrientationIndex_r` (see
[official API](https://libgeos.org/doxygen/geos__c_8h.html)), not a timed competitor.

| Case stream | Labels | Filter fallback | Filtered median | Always exact median |
|---|---:|---:|---:|---:|
| Original ring panel | 243,727 | 53 | 84.662 ms | 552.531 ms |
| Tiled native geometry | 1,000,000 | 225 | 352.972 ms | 2,355.427 ms |
| Tiled, every 64th replaced by a hard authored case | 1,000,000 | 15,842 | 451.245 ms | 2,439.149 ms |

Timing: same Python worker and input dispatch, including output allocation,
median of three alternating passes per variant. Every label in a timed
output buffer is compared exactly against the other route. GEOS calls,
GDAL extraction, file hashing/loading and validation are outside timers.
The 1M native stream repeats the 243,727 actual wedges, not a million
new geometries; the pressure schedule is authored. 1k and 100k scale
receipts are included. Whole worker peak RSS at 1M was 99,504 KiB,
including imported libraries and preloaded native records; not
per-stage incremental RSS. No cold-I/O, end-to-end geospatial pipeline,
public engine performance, or 100M-row extrapolation.

Replay with GDAL Python 3.10.3 and GEOS 3.13.1 already installed:

    sha256sum -c SHA256SUMS
    python3 -IB prep.py PINNED_INPUTS_DIR NEW_SCRATCH_WEDGES_BINARY | cmp - SOURCE.json
    python3 -IB check.py | cmp - RESULT.json
    python3 -IB run.py NEW_SCRATCH_WEDGES_BINARY 243727

Last command repeats the semantic check and remeasures, without assuming
identical timings. No coordinates, original files, or external I/O shared.
