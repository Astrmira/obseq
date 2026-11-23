# E5: native dbt source freshness is not complete shard freshness

This first actual dbt coverage checks a narrow existing API rather than creating a new comparison tool. The [published dbt freshness contract](https://docs.getdbt.com/reference/resource-configs/freshness) specifies most-recent source timestamp, error thresholds, optional row filter, and (since v1.10) loaded_at_query. We ran dbt-core 1.10.15 and dbt-duckdb 1.9.6 against DuckDB 2.0.1. No service account, network query, or real-source implication. Installed stock CLI and adapter with scratch-only dependencies; reported one schema spelling failure before any native runs, then changed only that option.

## Indistinguishable global evidence and exact native contrast

Five fixed four-row heartbeat worlds use age in minutes relative to one T0 for the full run. Independently enumerate latest timestamp for each registered shard A/B; declare all fresh only if both are represented and latest age ≤60m. Threshold is well away from real runtime/clock jitter. DBT warnings set at 30m, errors at 60m; none of these plans straddles a threshold. Multiple records per shard and old rows are legal where that shard has a current latest observation.

| Authored world | Stock global MAX | MIN of maxima, observed shards only | Scope-complete MIN of expected maxima | Independent |
|---|---|---|---|---|
| A/B latest both current, older rows retained | pass | pass | pass | fresh |
| B stalled, same global age histogram | pass | error | error | not fresh |
| B completely absent, same global age histogram | pass | pass | error | not fresh |
| A/B current, old unrelated C excluded | pass | pass | pass | fresh |
| Both stale | error | error | error | not fresh |

In the first three worlds, exact global row counts, timestamp histogram and newest value are identical. Actual dbt MAX outputs the same max_loaded_at, not just the same pass status. The projection is insufficient even if one adds **any** statistic depending only on the global timestamp multiset. A WHERE-filtered stock source check for each named shard (two extra native nodes) agrees with the independent purpose when conjoined; missing shard native node reports error. A closer and lower-friction baseline is dbt's already published loaded_at_query interface, not custom comparison machinery: one SQL source query returns the minimum of registered shards' latest timestamps if and only if all expected groups are present, and an intentionally old sentinel otherwise. Merely substituting MIN for MAX after grouping observed shards fails if an entire expected shard is absent. Restricting expected group names also ensures irrelevant telemetry cannot contaminate the declaration. Node artifacts and return codes, including all false passes relative to the different target contract, are preserved; no bug in global MAX claimed.

## Admission boundary

The coverage predicate and fixed shard registry are the important extra part of the evidence; without them there is no universal bound from observed maxima. Once scope is complete, min over per-shard max is necessary and sufficient for the common one-sided age cutoff, not for late-arrival completeness within a shard, incorrect client clocks, missing individual records, or data repairs. Artifacts from separate filtered nodes can come from distinct snapshots; agreeing per-shard nodes alone is not proof of one common source version under concurrent writes. A one-statement loaded_at_query makes the completeness and min criteria co-observed subject to actual adapter transaction semantics. The read-only interval and static authored rows in this run do not prove that property across adapters. The epoch sentinel is a test representation of absence, not a native recommendation to conflate missing and stale. A deployed protocol should name missing shards and bind expected membership and data revision.

## Replay

Runtime dependencies are enumerated in DEPENDENCIES.json, not redistributed. Reproduce with matching versions in deps/ (official PyPI) and run python3 -IB check.py | cmp - result.json. Raw native timestamp receipts naturally vary with reexecution; verify frozen receipts by python3 -IB verify.py | cmp - verification.txt plus SHA256SUMS. This is 25 actual dbt decisions, no result-selected scope or timing claims.
