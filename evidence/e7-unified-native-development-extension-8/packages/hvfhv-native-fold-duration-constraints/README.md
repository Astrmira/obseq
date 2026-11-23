# HVFHV: can published duration resolve a local-time fold?

The [NYC TLC High Volume FHV data dictionary](https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_hvfhs.pdf) describes `trip_time` as passenger-trip time in seconds. We test whether it is consistent with an elapsed duration between recorded pickup and dropoff values. The original November 2025 Parquet (20,818,240 rows) stores both endpoint columns as Parquet INT64, microsecond unit, isAdjustedToUTC=false; Arrow exposes zone-free microseconds. The duration is int64. We scan the fixed 00:00–04:00 pickup interval on the November 2 fall transition and the following ordinary Sunday November 9. Both cohorts come from the same pinned monthly object; no time conversion of source fields is presumed.

| Local slice and endpoint state | Trips | No compatible pair | One compatible pair | Multiple compatible pairs | Unique due to duration |
|---|---:|---:|---:|---:|---:|
| Nov 2, neither endpoint repeats | 80,121 | 13,670 | 66,451 | 0 | 0 |
| Nov 2, one endpoint repeats | 24,707 | 4,460 | 20,247 | 0 | 20,247 |
| Nov 2, both endpoints repeat | 66,321 | 11,908 | 10,166 | 44,247 | 114 |
| Nov 9, ordinary matched hours | 123,660 | 20,839 | 102,821 | 0 | 0 |

All admitted rows have nonnegative reported duration, endpoints within the date guard, and at least one forward UTC pairing before enforcing duration. "Unique due to duration" counts only cases that had more than one such forward pairing and end with exactly one. For repeats under the contemporary one-hour fold, same-fold early and same-fold late pairs share their elapsed duration, so the recorded duration cannot distinguish them. Cross-fold pairs differ by exactly 3,600 seconds relative to the wall difference. Agreement with an elapsed time cannot establish how the provider computed its field.

The non-fold comparison matters: in the ordinary slice HV0003 has **20,839/84,008** exact duration mismatches; HV0005 has **0/39,652**. A duration mismatch is therefore not reliable evidence that a fold candidate is wrong. The detailed receipt retains provider, endpoint multiplicities, forward and matched pair sizes, raw wall subtraction agreement and missing/negative categories. No trip identities, exact pickup values, actual fold truth, provider methodology, or population rates are inferred.

The independent PyArrow + Python implementation round-trips each of both possible fold bits under a pinned TZif. Native DuckDB 2.0.1 uses actual ICU local-to-UTC, examines the adjacent hour candidates and filters by exact roundtrip and nonnegative integer elapsed microseconds. Both engines agree on the full stratified relation. The ±one hour construction is scoped to the two New York local dates and adjacent guard, not arbitrary timezones or historical transitions.

Replay with DuckDB 2.0.1 and PyArrow 26.0.1, the described public file and the pinned New York TZif:

    set -e -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B check.py /path/to/fhvhv_tripdata_2025-11.parquet /path/to/America/New_York | cmp - RESULT.json

No raw trips redistributed; the official source URL and digest are recorded.
