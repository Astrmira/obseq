# A1 query inventory and native cutoff census

The remote run parsed all 305 pinned SQL statements with sqlglot 28.0.0.
The catalog contains 22 TPC-H, 99 TPC-DS, 13 SSB, 113 JOB, 43 ClickBench
and 15 H2O queries. The six source schemas are frozen alongside the results.
The inventory records syntactic order-key coverage, nested limits, ranking
windows, grouped top-N aggregates, explicit representatives, and exact,
floating-point or unresolved reduction operand types. Statistical aggregate
inputs that appear exact before DuckDB's native binding are recorded separately.

The top-level ORDER BY/LIMIT counts are 5 TPC-H, 80 TPC-DS and 31 ClickBench.
`cutoffs.py` retains the native candidate relation, counts peers by the
complete key, and checks whether a peer group crosses either edge of the
selected rank window. Projected DISTINCT sort keys are mapped after deduplication.
Each of SF1 and SF10 verified all 5 TPC-H and all 80 TPC-DS windows. TPC-DS Q59
split an upper-edge peer group of 49 at both scales. It was the only TPC-DS
query with a split cutoff in these runs. No TPC-H window split a peer group.
The A7 [full ClickBench crosswalk](../pvldb-a7-typed-candidates/FULL-ANALYSIS.json)
binds all 43 static entries to their native 1/8-thread receipts by SQL
hash. It verifies all 31 cutoff windows on 99,997,497 source rows.
Eight windows split a peer group and six of those queries produced
different bags across the measured thread arms.

`covers_group_keys` and `covers_projected_expressions` record sufficient
structural matches. `dependency_unresolved` includes cases that require keys,
join dependency analysis, or native binding. Final mechanism labels and
contract derivation for the wider catalog remain open beyond the typed
ordered-window scope.

```sh
python -B schemas.py SOURCES JOB_SCHEMA CLICK_FOOTER TPCH_EXTENSION TPCDS_EXTENSION > SCHEMAS.json
python -B run.py SOURCES JOB_SQL_DIR STOCK_SQL H2O_CHECKOUT OUTPUT --schemas SCHEMAS.json
python -B cutoffs.py tpch TPCH_QUERIES OUTPUT_JSONL --extension TPCH_EXTENSION --scale 1
python -B cutoffs.py tpcds TPCDS_QUERIES OUTPUT_JSONL --extension TPCDS_EXTENSION --scale 1
```

Use `--scale 10` for the SF10 arms.
The TPC query bundles contain stock queries from DuckDB 1.4.3 and the
corresponding signed extension SHA-256. Use the SHA-pinned ClickBench SQL
and H2O DuckDB scripts in `run.py`, the JOB source at `a3960`, and the
existing SSB evidence query dictionary `Q`.

[HUMAN-AUDIT-QUEUE.tsv](HUMAN-AUDIT-QUEUE.tsv) freezes five queries per
suite for the independent 30-query audit. Selection greedily covers
distinct static signatures within each suite and uses an identity-hash
tiebreak. The [30-query SQL review](SQL-AUDIT.md) records the labels and
evidence for all selected queries. Across the five planned mechanism axes,
135 resolved automatic cells agree with the review and 15 remain unresolved.

## Typed window checks

`verify_windows.call(connection, query, candidates)` binds the output types
against DuckDB, derives the complete order key and eligible projected rows
from the query, and checks candidate sequence and multiplicity with exact
NULL-safe comparison. Candidate columns are positional. The witness reports
the required and observed row counts and any ineligible or excess peer member.
This validates the ordered-window contract against the DuckDB snapshot.
Independent aggregation, float envelopes and dependent nested choices require
their own contracts.

The returned `VERIFY-*.jsonl` receipts cover 5 TPC-H and 80 TPC-DS queries
at each of SF1 and SF10, and 31 full ClickBench queries. Across the two
scales and both ClickBench thread counts, all 232 native arms passed, and
all 201 cardinality controls were rejected. An empty native output uses
a one-row control.

The second Linux run covers the same 116 distinct SQL windows and preserves
all 232 native and 201 cardinality-control decisions. It rejects 549 certified
equal-length controls: 199 absent projected members, 177 excessive
multiplicities and 173 wrong orders. TPC-DS Q17 is empty at both scales.
The remaining 115 distinct windows all have an equal-length control.
The receipt gives the reason wherever a particular control could not be
certified. `verify_windows.py --same-cardinality` produces the per-window
receipts, and `python -B summarize_controls.py .` checks them against the
original decisions. Projection strings use exact value identity, while
rank peers continue to follow the source order.

```sh
python -IB select_audit.py INVENTORY.json | cmp - HUMAN-AUDIT-QUEUE.tsv
```
