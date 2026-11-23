# EA&B E6: verify legal top-k without a golden selection

On 31,391,900 eligible rows from four public NYC Yellow Taxi March files, we compared an exact typed verifier against stock DuckDB ORDER BY/LIMIT. The verifier admitted all 24 native outputs, including five cells with different legal tie selections, and rejected all 53 typed fault controls. Merely checking that fewer than k rows beat the cutoff accepted all five controls that omitted a strict winner without changing the cutoff. Across eight fixed file/k cells, median verifier wall time was 10–87% of a native rerun. This measures checking an existing candidate against one known file, not end-to-end execution.

## Exact contract

Use the [official NYC Taxi & Limousine Commission trip records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page), March 2014, 2019, 2025, and 2026 Yellow Taxi Parquet files (31,392,462 total rows; full hashes in INPUTS.sha256). Scope exactly the named month via a half-open interval of the native, zone-free microsecond pickup timestamps. Some source files contain dates outside the scope. Rank by pickup timestamp descending, with no secondary rule. A result carries file-relative physical row ID and exact timestamp. An ID is meaningful only within that exact immutable source, and does not survive file rewrites/reordering.

For full k>0, let t be the minimum selected timestamp. Require distinct IDs, verify every projected timestamp and scope via its source ID, check descending order, and compare:

    count of all scoped rows with score > t
      == count of distinct candidate rows with score > t.

Because the verified strict candidate set is a subset of the source strict set, equality holds exactly when every strict winner is selected. All remaining k slots may use any verified distinct rows at t. If the result is shorter than k, require exact eligible source count = candidate length; k=0 requires an empty result. The inequality count(source > t) < k does not establish coverage: it accepts a strict winner replaced by a spare row at t, even with source-authentic rows, cardinality, displayed order and cutoff unchanged. There was a spare cutoff peer in five cells; the other three did not receive a fabricated control of this kind.

Both arms are native DuckDB. The guard uses a filtered aggregate count and the [Parquet file-relative row number](https://duckdb.org/docs/stable/data/parquet/overview), not a new file reader. The untouched rerun SQL uses ORDER BY/LIMIT with [DuckDB's TopN optimization](https://duckdb.org/2024/11/14/optimizers). An independent PyArrow 26.0.1 and NumPy source scan checks every decision using exact integer microseconds and physically separate validation. To construct legal alternatives use opposing secondary row-ID orders; in five cells these select different sets, not just reordered rows. This is not a rate of naturally emerging nondeterminism. The contract is not for arbitrary payload types, engine-specific collations, dynamic sources, or other relational operators.

| March source | k | stock rerun median (ms) | exact guard median (ms) | guard/rerun |
|---|---:|---:|---:|---:|
| 2014 | 32 | 417.480 | 330.179 | .791 |
| 2014 | 1024 | 851.175 | 393.840 | .463 |
| 2019 | 32 | 245.240 | 213.247 | .870 |
| 2019 | 1024 | 584.605 | 230.535 | .394 |
| 2025 | 32 | 99.089 | 24.934 | .252 |
| 2025 | 1024 | 345.603 | 35.195 | .102 |
| 2026 | 32 | 115.064 | 48.131 | .418 |
| 2026 | 1024 | 313.392 | 56.025 | .179 |

The 112 timings are seven interleaved fresh connections per arm per cell. Both arms include query execution/fetch; guard includes local and source verification of a prepared candidate. Candidate generation, pre-warming/source hashing, connection setup and out-of-timer postcondition checks are excluded. A single permitted AMD EPYC 9V74 vCPU, DuckDB 2.0.1, one thread and 192MB engine memory limit per connection; no exclusive CPU reservation or memory/I/O performance claim. The original combined attempt exited 137 without emitting timing observations. The sealed retry isolates its measurements from the independent Arrow reference; no timings are pooled across attempts. These descriptive results do not give CIs, universal speed guarantees, or overhead as a fraction of a full production pipeline. An already-computed exact golden result might be compared more cheaply, but would exclude legal alternative cutoff IDs.

Replay with the stated DuckDB 2.0.1, PyArrow 26.0.1 and NumPy 2.5.5:

    set -o pipefail
    sha256sum -c SHA256SUMS
    python -B check.py /path/to/tlc/march/files | cmp - result.json
    python -IB summarize.py | cmp - timing-summary.json

Use check.py --timing for a fresh measurement; wall values need not reproduce. No source records are redistributed.
