# A7 full ClickBench native typed capture

The run completed on 2026-11-23 at 01:53:35 UTC+08. All 100 publisher
shards passed exact length, ETag checks during transfer, pinned footer
checks, and local SHA-256 recording. The source has 99,997,497 rows and
14,737,666,736 compressed bytes. DuckDB 1.4.3 completed all 43 stock
queries at both one and eight threads. The 86 Arrow IPC candidates were
recovered and checked locally against the capture manifest. Raw candidates
are stored outside Git because rows can contain identifiers, phrases and URLs.

## A1 observed query behavior

The full [query crosswalk](FULL-ANALYSIS.json) joins the stock SQL hashes
to A1's static inventory, the native thread comparisons and the cutoff
census. Query numbers are one-based stock SQL line numbers.

| Full-cohort observation | Count | Queries |
| --- | ---: | --- |
| Divergent exact order | 9 / 43 | Q18, Q22, Q25, Q32, Q33, Q39–Q42 |
| Divergent exact bag | 7 / 43 | Q18, Q32, Q33, Q39–Q42 |
| Split ORDER BY/LIMIT window | 8 / 31 | Q25, Q31–Q33, Q39–Q42 |

Six bag changes coincide with split cutoff windows. Q18 has an unordered
group limit and both native outputs satisfy its exact group-count oracle.
Q25 has four mandatory rows and eight distinct projected cutoff peers
for six slots, admitting 28 projected bags. The observed thread outputs
have the same bag and pass the source-derived membership and order checks.
Q31 retains the same observed output across the thread arms despite
its split cutoff. The one-million-row comparison remains in the
`PART0-*` receipts, where 11 of 31 windows split a peer group.

The [later A2 independent scan](../pvldb-a2-clickbench-typed-windows/README.md)
adjudicates both native answers to the six additional bag-changing
queries, and both answers to Q31. All 14 pass.

## A2 baseline observations on independently checked outputs

[FULL-A2.json](FULL-A2.json) records three legal and four invalid
comparisons across Q18 and Q25 against the eight-thread reference.
The one-thread outputs are native, and the third legal control replaces
one selected Q25 peer with an omitted eligible peer observed in the
full data. Q18 uses exact Parquet group counts to label the key mutations
and the count swap. For Q25, 27 rows at the exact cutoff carry an empty
phrase excluded by the stock predicate, providing a same-score invalid
member. Byte comparisons use Arrow IPC payload hashes.

| E2 observer | Rejected legal / 3 | Accepted invalid / 4 |
| --- | ---: | ---: |
| Ordered equality or Arrow byte digest | 3 | 0 |
| Exact bag or set equality | 2 | 0 |
| Relative tolerance at either tested threshold | 3 | 2 |
| Exact numeric column sums | 1 | 2 |
| Row count or schema | 0 | 4 |

Both tolerance settings accept the Q18 exact-key +1 and float64
round-trip mutations. Column sums accept the Q18 group-count swap and
the Q25 filtered-out phrase. These observations cover two query families
and four instantiated operators (M1, M2, M3, M6).

## Full identifier conversion

[FULL-ID-CAST.json](FULL-ID-CAST.json) retains the exact cross-arm pair
counts. Converting both sides through float64 yields one additional
WatchID pair from two distinct exact keys. Converting one side loses
3/3 exact non-null WatchID pairs and 2,193,366,948/2,246,850,803
(97.62%) exact non-null UserID pairs. Neither source column contains
NULL. The one separately authored NULL-control pair is excluded from
these denominators. The arms use alternating row positions within
each shard, with the integer tie-to-even reference checked against
the native DuckDB adapter.

The wall-clock stages after acquisition were 632 seconds for queries
and independent checks, 130 seconds for ID conversion and 92 seconds
for the cutoff census. `FULL-RUN.log` preserves the stage receipts.

## Replay

```sh
python -B ../remote-clickbench-full/download.py ../clickbench-full-partition-footer-audit/PARTITIONS.json STORE_1 STORE_2 ACQUISITION --workers 8 --split 51
python -IB run.py ACQUISITION STOCK_SQL OUTPUT STORE_1 STORE_2 --upstream ../remote-clickbench-full/run.py
python -B ../remote-clickbench-full/id_cast.py ACQUISITION ../clickbench-native-id-cast-boundaries/check.py ID_CAST_JSON STORE_1 STORE_2
python -B ../pvldb-a1-query-inventory/cutoffs.py clickbench STOCK_SQL CUTOFF_JSONL --acquisition ACQUISITION --stores STORE_1 STORE_2 --upstream ../remote-clickbench-full/run.py
python -IB score.py ACQUISITION OUTPUT ../remote-clickbench-full/run.py ../pvldb-a2-q39-real-output/run.py ../submission-e-series-native-evidence/e23/check.py STORE_1 STORE_2
python -IB summarize.py ../pvldb-a1-query-inventory/INVENTORY.json --private-candidates OUTPUT/private-candidates
```

Run with DuckDB 1.4.3, PyArrow 22.0.0, sqlglot 28.0.0 for the cutoff
census and the stock SQL identified in `REMOTE-INPUTS.sha256`.
Omit `--private-candidates` to reconcile the published receipts alone.
