# EA&B F8: time order can identify a unique fold pair even when both endpoints are ambiguous

The [NYC Taxi and Limousine Commission Yellow Taxi dictionary](https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_yellow.pdf) defines pickup and dropoff as meter engagement and disengagement. For the explicitly nominated America/New_York wall-clock interpretation, use the source record's two timestamps and assume only that disengagement in UTC cannot precede engagement. This is a domain consistency check under declared assumptions, not a retrospective determination that the meter or timestamps were actually correct.

Across five full official November files, **5,321 of 105,452** records with at least one repeated-hour endpoint have exactly one physically ordered assignment. The native DuckDB endpoint-by-endpoint default yields a negative elapsed time for every one of those, despite a valid pair existing. Always using the first fold at both endpoints fails on those same records. In the other **100,131** selected records, even the elapsed duration has at least two feasible values. Choosing a default does not resolve their source ambiguity.

| Official November | At least one fold endpoint | Alternative instants collapse to one ordered pair | More than one feasible duration |
|---|---:|---:|---:|
| 2014 | 47,915 | 1,238 | 46,677 |
| 2019 | 21,977 | 973 | 21,004 |
| 2022 | 9,722 | 678 | 9,044 |
| 2024 | 11,512 | 1,001 | 10,511 |
| 2025 | 14,326 | 1,431 | 12,895 |

Use complete [published NYC TLC files](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) pinned by SHA-256. Require non-null native timezone-naive microsecond timestamps both inside the file's named calendar month, at least one in its actual transition fold. This is not all pickups or all NYC trips. 91,891 rows have ambiguous pickup, 95,155 ambiguous dropoff, 81,594 both. Zero in this specific selected scope lack a physically ordered pair. Do not infer a population misparse rate, a bound on real trip duration, or exact actual instants for the multiple-solution group.

## Joint rule, not independent fold defaults

For a wall time x, enumerate the set U(x) of UTC instants that round-trip to x, with the original zone and pinned rule version. Form all pairs from U(pickup) × U(dropoff) and retain v ≥ u. Instants may remain ambiguous even if a derived quantity is stable, so deduplicate durations v-u separately. Here the isolated NYC fall hour has two endpoint interpretations exactly an hour apart, following [PEP 495's standard fold convention](https://peps.python.org/pep-0495/). For two endpoints inside that hour with dropoff wall time earlier than pickup, either same-fold assignment violates order; late-pickup/early-drop also violates it. Exactly the remaining early-pickup/late-drop pair is admissible. If dropoff wall time is equal or later within that hour, both same-fold assignments survive plus the early/late pair, producing two feasible durations. With one fold endpoint and normal endpoints on the feasible side of the transition, two assignments remain. Do not use these simplified inequalities for arbitrary zones/gaps; the finite support is the contract.

The independent PyArrow and ZoneInfo path uses both folds and UTC round-trip tests, finds the fold hour using the pinned TZIF, and builds exact pair and duration support. DuckDB 2.0.1 natively scans the same file, uses [timezone localization](https://duckdb.org/docs/stable/sql/functions/timestamptz) plus a one-hour alternative specific to these five folds, and checks candidates by the reverse stock operation. The stock later-fold choices are retained separately from that explicit joint validation. The two implementations agree on the full multiset of (source wall pair, interpretation signature); only aggregate group counts leave memory. Authored example controls are not included in the cohort. This extends the earlier single-pickup ambiguity screen, not an estimate of truth from timing, fares, or source IDs.

Replay with Python zoneinfo, PyArrow 26.0.1 and DuckDB 2.0.1, the five exact monthly files and the exact America/New_York TZIF from tzdb 2026c:

    set -o pipefail
    sha256sum -c SHA256SUMS
    python -B check.py /path/to/tlc/november/files /path/to/zoneinfo/America/New_York | cmp - result.json

The replay checks all source and TZIF hashes. No source rows or TZIF bytes are redistributed.
