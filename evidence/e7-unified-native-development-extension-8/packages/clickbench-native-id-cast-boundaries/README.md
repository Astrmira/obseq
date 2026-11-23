# EA&B E4 F1: precision loss can destroy matches without collapsing any distinct IDs

Use the [official ClickBench publisher partition 0](https://datasets.clickhouse.com/hits_compatible/athena_partitioned/hits_0.parquet), 1,000,000 intact physical rows, exact SHA-256 in PLAN.json. This complements the stock query result-family run; no full-ClickBench prevalence or claim about the publisher's execution pipeline. Both analyzed columns are native signed BIGINT. Source contains no NULLs in these columns. Predeclare odd/even physical row split and add a single authored NULL on each side to independently verify NULL-safe matching. Weights are row-pair multiplicities, not numbers of distinct IDs. No raw IDs, returned keys, URLs or row data published.

Both exactly checked DuckDB releases give the same direct-BIGINT result. An independent Arrow scan and integer-only nearest-even binary64 conversion verify it without accepting an engine's casts as truth.

| Source column | distinct IDs | exact numerical value changes after direct binary64 round-trip | many-to-one rounded buckets | true cross-arm non-NULL pairs | unilateral lost pairs |
|---|---:|---:|---:|---:|---:|
| WatchID | 1,000,000 | 999,005 | 0 | 0 | 0 |
| UserID | 79,842 | 76,893 | 0 | 16,818,332 | 16,231,626 |

When both arms use the same direct binary64 projection, the cast remains **injective on these observed distinct IDs**. It preserves every prior key-equality pair and creates zero false matches, despite changing most integer values. When only the right arm passes through binary64 and is then written back into an integer type, the equality join sees a different key. Now about **96.5%** of the previously correct UserID pairs disappear, with zero new false pairs in this control. The WatchID split has no correct non-NULL pairs to lose. Each authored NULL pair survives all arms and is excluded from the numbers in the table. An adapter that instead implicitly converts the left integer to binary64 would be measuring the symmetric arm, so the comparison must pin the cast and comparison sites. No assertion that all float joins fail, that the publisher tracks this pipeline, or that these counts generalize to another partition or split. A collision statistic alone misses the difference.

## Width-before-float auxiliary control

The actual source-read type matters even if the final storage type is the same. The initial SQL adapter used BIGINT→HUGEINT→DOUBLE rather than direct BIGINT→DOUBLE. Its result did not match the independent int64 oracle; preserve the distinction rather than treating it as an oracle disagreement. In DuckDB 1.4.3 the extra exact widening changes the later float outcome for **18 distinct UserIDs**, all negative, including **two** exactly representable on the direct path. Its unilateral loss rises by **122** pairs. DuckDB 2.0.1 has zero such widening-path differences on the same IDs, and both versions agree on the direct int64 path. This is a narrow observed cross-version result, not a claim that correct rounding is guaranteed for all HugeInts or a newly discovered general engine defect. [DuckDB's typecasting docs](https://duckdb.org/docs/current/sql/data_types/typecasting) explicitly distinguish these input widths and warn that wide integers to floating point can lose precision.

Re-run using the two pinned native combinations DuckDB/PyArrow 1.4.3/22.0.0 and 2.0.1/26.0.1, respectively:

    sha256sum -c SHA256SUMS
    python -B check.py /path/to/hits_0.parquet | cmp - result-143.json
    python -B check.py /path/to/hits_0.parquet | cmp - result-201.json

Switch Python package environment between the last two commands; each checks the original file hash and recorded plan. Reports are about exact semantics, not time.
