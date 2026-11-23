# O3: a coupled representative on unmodified NYC TLC records

This is a real-input semantic extension to E6, **not an overhead measurement** or an official TLC benchmark. It uses the already admitted [November 2025 Yellow Taxi Parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-11.parquet), documented by the [TLC](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page). No rows exported. The analytics query is authored: for each source pickup zone, choose one coherent dropoff-zone/passenger-count/payment-type tuple from trips with the minimum finite positive recorded distance. No inference about a trip's true physical distance or source quality. Denominator and predicate were fixed before replay. Supply any path to the exact SHA-identical source bytes.

With 4,181,444 physical rows, 4,072,024 pass the eligibility test. Of 260 groups, 190 have multiple minimizing source rows and 186 have multiple distinct minimizing payloads. The largest minimizing group has 542 rows. [DuckDB's native ARG_MIN](https://duckdb.org/docs/stable/sql/functions/aggregates) receives a struct including the physical row ordinal and all three observable payloads; NULL fields remain fields of that struct. Independent Arrow Parquet streaming reads every projected input row, tests finite binary64 distance equivalently to DuckDB and enumerates the ties; the ordinal is meaningful only for the exact file revision.

ASC and DESC on the aggregate argument legally refine the same minimum-score family. Both and the unspecified native output pass independent checks on every group. ASC versus DESC differs by provenance in 190 groups and by observable payload in 185. Unqualified ARG_MIN agrees with ASC on this execution; this is not evidence of run-to-run variation. A fixed output comparison is stricter than the explicitly admitted contract. If physical ordinal is not part of the requested output contract, test existential coherent payload membership; if it is claimed, require that precise ordinal to be a minimizing source witness with that payload.

At each zone the Cartesian product of independently valid payload-field projections equals the coherent family iff no tuples are missing from that product. On this file the marginal-only check accepts 66,849 distinct infeasible zone/payload combinations across 122 zones. A separate native SQL query independently minimizing each field among score-minimum rows satisfies all three marginals everywhere but fails the coherent tuple check in 120 zones. This is a controlled incorrect implementation of the *coupled query*, not a DuckDB bug or a population defect rate.

Reproduction:
```sh
sha256sum -c SHA256SUMS
python3 -B check.py PINNED_NOVEMBER_TLC_PARQUET | cmp - RESULTS.json
```
DuckDB 1.4.3, PyArrow 26.0.1. No installation or raw material is needed in the published packet; a replay requires the source and these runtimes. This does not replace E6's frozen timed authored suite or extrapolate scalability.
