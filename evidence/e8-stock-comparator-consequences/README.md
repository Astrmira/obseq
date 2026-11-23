# E8: two native benchmark cases with concrete comparator consequences

Both cases are actual full scoped workloads with authored mutation controls. They test whether an observer accepts a legal numerical variant and rejects a materially different answer. This packet does not label controlled mutations as natural engine failures.

## H2O: correct sums, wrong partner assignment

Using the original complete 10M-row H2O generator input, execute the [publisher's stock Q3 query and checksum SQL](https://github.com/duckdblabs/db-benchmark/blob/3b074bc3190468803b3a890301f87ce455114d20/duckdb/join-duckdb.py). Run the untouched three-decimal `make_chk` helper on actual stock SUM results over the clean projection, a two-row right-value exchange and a one-unit positive-control change. The clean and exchanged joins both render **475042480.57;423957578.77**. The one-unit control changes the second checksum to **423957579.77**. Exchange changes which right-side value was assigned to each of two unique projected left rows; no observed key or cardinality change is necessary. The [independent exact projected observer](../h2o-stock-projection-switch-observer/README.md) already verifies the two witness occurrences and rejects the changed association without hidden row IDs. This new run tests the actual rounded publisher checksum, not an exact decimal substitute. The publisher logs that checksum; we show its inability to distinguish this fault, not a claim that the harness automatically accepts or rejects submissions.

## TPC-DS: admit legal float drift without relaxing keys

Use the frozen stock Q39 SF10 output; the two native thread arms agree on all **2,433** exact matched keys but differ in numeric fields on **458** rows. These are sealed outputs, not newly timed or re-executed native queries. Both the exact-key/four-ULP numeric contract and [stock unchanged CWI reproduction comparator](https://github.com/cwida/tpcds-result-reproduction/blob/61ba82e7f6868760dcfbfa4347fe06cfd67a798f/roundingdiff.py) accept the legitimate arms in both directions. Changing one exact item key by one (consistently in both role columns) is accepted by the CWI comparison but rejected by the key-aware contract. Both reject a doubled numeric control. Thus weakening every integer to a tolerant numeric field adds a false acceptance without being needed to accept these legitimate floating reductions. Four ULP is a separate stated gate for these paired observations, not a claim about official TPC qualification tolerances. The older small-scale CWI case is not used as a substitute for SF10.

## Replay

The source dependencies are the pinned H2O predecessor's `run.py`, checksum and query tools at the maintainer's commit, the original admitted H2O CSVs, the previously sealed SF10 output shards, and the unchanged CWI script. All inputs are checked by digest. Use native DuckDB 1.4.3 and pandas 2.2.3.

    set -e -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B check.py H2O_PRIOR_RUN H2O_INPUT_DIR STOCK_JOIN_PY STOCK_HELPERS_PY SF10_RECEIPT_DIR STOCK_ROUNDINGDIFF_PY | cmp - RESULT.json

No source data or upstream scripts redistributed. No rewritten comparison leaderboard, runtime claim or formal paper edits.
