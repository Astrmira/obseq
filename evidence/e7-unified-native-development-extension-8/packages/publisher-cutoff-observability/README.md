# E4: distinguish a boundary tie from observable ambiguity on stock benchmarks

A cutoff peer class can be split without making any published value ambiguous. Conversely, a projected result can distinguish legal members even when the ordering key is absent. This audit reports the physical peer class and the observable projection separately, not a rate of spontaneous nondeterminism.

| Stock workload and admitted scope | Scope units | Candidates strictly ahead | Slots in cutoff class | Physical peers | Distinct peer projections | Legal output changes |
|---|---:|---:|---:|---:|---:|---|
| ClickBench Q24, first intact publisher partition | 69,354 eligible rows | 8 | 2 | 4 | 2 | Source IDs and projected bag |
| ClickBench Q25, same partition | 69,354 eligible rows | 8 | 2 | 19 | 1 | Source IDs only |
| ClickBench Q26, same partition | 69,354 eligible rows | 8 | 2 | 2 | 1 | Neither; all cutoff peers fit |
| H2O GroupBy Q8, 10M generated file | 95,001 eligible groups | Per group | Per group | 1 in all 95,001 groups | 1 per group | None at the measured cutoff |

ClickBench query numbers are zero-based. Execute all three source statements in [publisher workload SQL](https://github.com/ClickHouse/ClickBench/blob/main/duckdb/queries.sql) on intact [hits_0.parquet](https://datasets.clickhouse.com/hits_compatible/athena_partitioned/hits_0.parquet). The DuckDB binary physical string ordering on this file is the measured axis; there is no collation change and no attempt to infer full 100-partition behavior. Q24 rechecks the prior scope witness as a positive control. Q25 is a matched differential: opposite physical row-ID refinements straddle a larger peer class, but because the key is also the entirety of the projection, they necessarily emit the same bag. Q26 uses the composite order (EventTime, SearchPhrase); on this partition its two cutoff peers exactly fill the remaining slots, so there is no membership ambiguity. The first packet mislabeled the SearchPhrase-only query as Q26. This revision corrects that index against the publisher SQL and separately executes the actual Q26. A source-membership checker must either omit row identity for this published contract or accept arbitrary distinct peer IDs if testing the stronger physical contract.

Use [DuckDB Labs' pinned H2O implementation](https://github.com/duckdblabs/db-benchmark/tree/3b074bc3190468803b3a890301f87ce455114d20) Q8 (`largest two v3 by id6`) with the unmodified DuckDB SQL and the originally generated `G1_1e7_1e2_5_0.csv`. A separate Python standard-library CSV stream counts occurrences of each group's top two distinct parsed scores; the exact native projected bag agrees for all 190,002 rows. All 95,001 groups, including the SQL NULL group key, have at least two eligible rows and a unique rank-two cutoff. These are exact binary64 comparisons after stock numeric import; no epsilon or rounding is applied. This zero is specific to this fixture and does not show that all H2O cohorts have no ties.

Results record only aggregate counts and exact input digests. Reproduce with the named DuckDB version and the pinned inputs (source data not redistributed):

    sha256sum -c SHA256SUMS
    python3 -B check.py /path/G1_1e7_1e2_5_0.csv /path/hits_0.parquet | cmp - RESULT.json
