# EA&B E1: TPC-H SF10 bundled execution vs scale-bound workload Q11

This follow-up uses the same complete locally generated TPC-H SF10 input as the Q21 packet: all 8 tables and 59,986,052 lineitem records, generated with the [DuckDB 1.4.3 signed TPCH extension](https://duckdb.org/docs/lts/core_extensions/tpch). It is not a formal TPC qualification run. No performance results are claimed.

In the first bundled native execution matrix, Q11 had zero rows despite successful execution. The separate follow-up plan was frozen before trying the corrected arm. In [TPC-H 3.0.1 §2.4.11.3](https://www.tpc.org/TPC_Documents_Current_Versions/pdf/TPC-H_v3.0.1.pdf) the workload fraction is 0.0001/SF; §2.4.11.4 instead uses 0.0001 with Germany for the qualification fixture. The bundled DuckDB 1.4.3 SQL and actual PRAGMA tpch(11) on this locally generated SF10 retain the latter literal. We hold nation and all input data fixed, changing just that literal to 0.00001 for a controlled scale-bound workload (not claiming randomly chosen production parameters).

Bundled arm: 0 rows. Scale-bound arm: 8,685 rows. An independent exact integer-cents accumulation from 323,920 source inventory rows checks both full answer maps over 304,774 candidate groups. Since inclusion is strict, compare integer group cents times the reciprocal denominator against total cents directly. The bundled threshold is about 8.10 billion cents, higher than the largest group at approximately 2.04 billion cents; scaling the threshold to one-tenth changes admission. Both native outputs satisfy their respective contracts, including descending aggregate-value ordering. Under the non-empty scale-bound arm, two additional rows share scores with others, so no secondary ordering is claimed. A semantic witness or reference should bind the exact parameter and SF, not just the query number. This checks a confusable parameter/fixture contract, not a novel finding about TPC, an engine defect, or evidence that the package promised a sample valid for every workload size.

The execution matrix runs the unchanged bundled SQL only and records status/shape, not correctness for all queries. One initial author-wrapper mistake assumed a three-statement Q15 bundle; the 1.4.3 query is a single statement, so final execution uses the same direct call for all IDs. Q11 and the separate Q21 packet are the exact semantic controls, not proof of all 22 answer bags.

Replay on the hash-pinned signed DuckDB 1.4.3 extension and exact generated database; create it with the linked Q21 packet setup, generator and count receipt. Native SQL is extracted from the signed extension, not bundled here. From this directory:
```sh
set -o pipefail
E=/path/to/pinned/duckdb-runtime
W=/path/to/writable/sf10-replay
P=$PWD
(cd "$E" && sha256sum -c "$P/INPUTS.sha256")
sha256sum -c SHA256SUMS
python3 -IB check.py "$E" "$W" | cmp - q11-result.json
timeout 120s python3 -IB matrix.py "$E" "$W" | cmp - matrix.jsonl
```
