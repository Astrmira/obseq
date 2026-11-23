# E3 F2: dropping nullable payloads changes native episode connectivity

Use the exact existing [November 2025 Yellow Taxi trip data](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-11.parquet), described by [NYC TLC](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page). This is an authored episode query on real released records, not a TLC workload or a driver-level claim. From 4,181,444 physical rows, admit 273,682 events with nonnull vendor, pickup zone 132 or 138, and recorded pickup timestamps in the nominal November month. Group by vendor and pickup zone; order by the stored, naive civil timestamp and exact physical file-row identity. It does not reconstruct UTC/DST or a vehicle or passenger sequence. Missing passenger count is a nonkey payload, not part of this activity stream's eligibility.

The rule starts an episode after a gap strictly greater than a fixed threshold. Comparison: (A) compute episodes from all records, then project known passenger counts; (B) drop unknown counts first, then compute episodes. Both present exactly the same 272,696 known rows, but they partition them differently. The admitted data have 986 unknown passenger counts. There are seven vendor-zone groups; six contain known passenger counts.

| Gap | All-event episodes | All-unknown episodes omitted on projection | Original surviving episodes split by early drop | New boundaries between surviving events | Drop-first total |
|---:|---:|---:|---:|---:|---:|
| 60 s | 35,174 | 298 | 75 | 75 | 34,951 |
| 300 s | 6,407 | 23 | 71 | 76 | 6,460 |

All-event versus drop-first total decreases by 223 at 60 s but increases by 53 at 300 s. An episode count can obscure wrong grouping: pure dropping cannot merge two original episodes, yet simultaneous omission and splitting have opposing count effects. At 60 s, 720 known rows belong to episodes that split; at 300 s, 5,730 do. The result is not a missing-data population estimate or a bug in the tools. The deliberately changed operation order is the failure mode for an all-events contract.

**Exact bridge receipt.** For each pair of consecutive known events, the path of all intervening adjacent events connects the pair at threshold t iff every adjacent gap is ≤t, equivalently its maximum is ≤t. The observed endpoint-to-endpoint gap after dropping rows cannot stand in for that maximum: it sums the original gaps. A certified maximum per surviving adjacency, bound to immutable source, partition, total order and eligibility, is sufficient to replay grouping for any threshold on this fixed survivor set. It does not identify exact original episode ordinals, count omitted all-unknown episodes, prove the original body to an untrusted reader or supply a numeric passenger aggregate. Native DuckDB computes and independently checks all 272,690 such maxima against a literal sequential PyArrow/Python oracle; then reconstructs the authoritative survivor partition at both thresholds. Both full native episode label vectors independently match the Python references by exact row identity, not just totals.

Replay from directory:
```sh
set -o pipefail
sha256sum -c SHA256SUMS
PYTHONPATH=/tmp/pvl-eab-submission/e1/input/duck143:/tmp/pvl-eab-submission/e4/deps \
  python3 -B check.py /tmp/pvl-eab-submission/e4/inputs/2025-11.parquet | cmp - RESULTS.json
```
Pinned DuckDB 1.4.3 and PyArrow 26.0.1. No raw rows or bridge maxima exported. No new input acquisition, timing, or Git changes.
