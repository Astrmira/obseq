# E3 F3: a path-bound Parquet Dataset can mix editions

Use the original SHA-pinned ClickBench hits_0 Parquet input (AdvEngineID, signed Int16), from the [publisher workload](https://github.com/ClickHouse/ClickBench/blob/main/duckdb/queries.sql#L1-L3). Both scratch editions are lawful native PyArrow projects, deliberately constructed rather than represented as published revisions. Edition A selects the first 32,768 genuine zero values; B selects the first 32,768 actual occurrences without that restriction. No source file is changed. Stock uncompressed/undictionaried Parquet produces the same logical schema, total row count, file length and every one of eight row-group page locations and lengths. Both have coherent readable starting states. Their full hashes and footer maxima differ. There are 959 positive values in B, exactly computed by typed Python and fresh native DuckDB.

In a single-threaded control flow, warm a version A PyArrow Dataset with the predicate AdvEngineID>0 and hold an independently opened ParquetFile. Then rebind only the scratch path alias atomically to B, with no concurrent writes or source mutation. Results from PyArrow 26.0.1 after the rebind:

| Observation | Positives |
|---|---:|
| Reused Dataset, native predicate | 0 |
| Same, requesting cache_metadata=False | 0 |
| Reused Dataset, scan without predicate then count identical B payload | 959 |
| Fresh Dataset at B, native predicate | 959 |
| Fresh DuckDB scan at B, native predicate | 959 |
| Already-open independent ParquetFile at A | 0, consistently A |

After that sequence, direct fragment.metadata inspection matches every B row-group bound, but the reused Dataset still returns zero from a further filtered count and scan. This demonstrates an observable stale scope in the given call sequence; it does not identify the internal cache mechanism. The [native PyArrow API](https://arrow.apache.org/docs/python/generated/pyarrow.dataset.Dataset.html) documents statistics pushdown and optional caching, not mixed-version snapshot semantics. This is an intentionally changed mutable locator outside immutable-snapshot assumptions, not a claim about every storage/catalog or about unwanted behavior for callers who intentionally request A.

**Practical admission:** matching schema, total row count, object length and page locations does not bind the version. Checking a fresh-looking metadata view separately from the already constructed consumer is also insufficient. Bind a stable immutable object edition to both metadata derivation and payload scan; build a new admitted consumer on edition change. A held coherent A handle is a valid *A* snapshot, not a verified alias-current read. Disabling that one scanner cache flag on an already warmed Dataset did not reauthorize it here. This is not a concurrency, parser, performance, or production prevalence test.

Replay:
```sh
set -o pipefail
sha256sum -c SHA256SUMS
PYTHONPATH=/tmp/pvl-eab-submission/e1/input/duck143:/tmp/pvl-eab-submission/e4/deps \
  python3 -B check.py /workspace/shared/eab-job-authority/hits_0.parquet /workspace/shared | cmp - RESULTS.json
```
DuckDB 1.4.3, PyArrow 26.0.1, scratch indexes/aliases removed by the fixture. No new downloads, no raw output or Git writes.
