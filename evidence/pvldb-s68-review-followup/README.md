# Second-review experiments

This packet contains paired native controls, stock-tool comparisons and full-scale performance measurements for the follow-up experiment plan. Each numerical entry is recounted from the recorded observations by `recount.py` and registered in the repository ledger.

## Correctness controls

| Experiment | Faulty executions | Legal controls | Measured result |
| --- | --- | --- | --- |
| M1, identical witnesses | 21 | 21 | ObsEq, Python assertions and a dbt singular test each reject all faults and accept all controls |
| M1, stock dbt freshness | 15 | 15 | All recent-load timestamps pass, including the semantically faulty executions |
| M1, DVC dependencies | 6 | 6 paired configurations | Declaring the WAL or UDF definition detects all six changes. Omitting that dependency detects zero |
| M2, execution binding | 12 | 9 | Execution-bound witnesses reject all faults and accept all controls. Request-layer witnesses accept all 12 faults |
| SpreadsheetBench missing caches | 19 tasks | 19 populated-cache controls | The stock grader accepts both mutually exclusive uncalculated formulas in every task. All populated-cache controls are rejected |

The M1 assertions receive the same explicit witness and reference. This measures comparison capability given that information. The stock dbt arm uses a `loaded_at` field and a one-hour threshold on newly loaded tables. DVC uses actual `stage add`, `repro` and `status --json` commands. Tracking a dependency detects invalidation. These experiments retain the explicit dependency declarations in the driver. No configured lakeFS service was available for the optional arm.

M1 recreates three paired executions for each selected C1 mechanism and replays the frozen C2 cases. M1, DVC and SpreadsheetBench ran on Windows 11 with Python 3.12.10. M2 and the full-scale runtime experiments ran on the remote Linux server. Each result records its engine and tool versions.

M2 uses native SQLite transactions, a trigger recording actual committed writes and a real subprocess exit between commits. O1 changes the opened snapshot while preserving the selected value. O2 tests both a data commit followed by a crash before the epoch commit and an epoch commit followed by data rollback. O5 requests KEEP while the executor commits CLEAR on an already-NULL value.

The SpreadsheetBench experiment runs the pinned stock evaluator on publisher V1 workbooks. It selects one eligible missing-cache formula in each of the 19 tasks. Each candidate contains either `=1000000000` or `=-1000000000`, saved without recalculation. Acceptance of both establishes at least one wrong accepted candidate per task. The normal openpyxl-save arm tests the usual output workflow. A second arm splices only the edited cell into the original archive and gives the same result. Receipts retain hashed task, workbook and cell labels.

## Native release sources and issue review

[C4-SOURCES.md](C4-SOURCES.md) lists all 29 release pairs, upstream issues and fix links, tested versions, classes, ordered-output visibility and ObsEq families. All 15 frozen issue IDs match distinct positive E9 labels and canonical issue URLs. The source lookup establishes a merged-PR link for 28 release pairs. The causal repair for DuckDB issue 21207 remains unresolved.

[E9-REVIEW.md](E9-REVIEW.md), [the retained annotation protocol](E9-ANNOTATION-PROTOCOL.md), [the acquisition protocol](E9-ACQUISITION-PROTOCOL.json) and [the codebook reference](E9-CODEBOOK.md) describe the retained annotation evidence. All 82 rows of [E9-HUMAN-REVIEW-QUEUE.tsv](E9-HUMAN-REVIEW-QUEUE.tsv) now carry completed human review decisions (67/82 confirmed wrong results, 8 `no`, 7 `unknown`; 65/67 conditional class agreement; 65/82 joint agreement; 15/15 on C4-replayed issues), recounted by `recount.py`. All 34 boundary non-positive rows in [E9-BOUNDARY-REVIEW.tsv](E9-BOUNDARY-REVIEW.tsv) (24 `F5`-stratum non-positives and 10 non-positive rater-`yes` disagreements) also carry completed human review decisions (`31 no`, `3 unknown`, `0 yes`, `0 F5`), recounted by `recount.py`. Exact original rater model parameters and invocation prompts were absent from the retained packet.

The complete [paired ratings, roster and 28 adjudications](../e9-independent-annotation-and-adjudication/) are shipped with their original digests. Running that directory's `check.py` reproduces the reported model agreement and the 82/203/15 final status distribution. The C4 linkage is independently joined back to those full records.

[Tracker-specific acquisition notes](E9-ACQUISITION-NOTES.md) record provider ordering, title/snippet checks and lifecycle differences. [Retrieval-cell coverage](E9-RETRIEVAL-COVERAGE.csv) retains the counts for the fixed tracker/term cells.

## Runtime measurements

`TABLE7-ARCHIVED.json` recomputes all five archived workers per cell, including check-only durations, min/max and within-worker ratios. It preserves the archived CPU information. The O3 top-k family, cutoff guard and representative-family check-only medians are 11.028903, 13.995783 and 11.203899 seconds, respectively. Their check/producer ratio medians are 1.319173, 1.807262 and 1.167578. Adding one gives total/producer ratios of 2.319173, 2.807262 and 2.167578 for those paired workers.

`geometry-pressure/` contains five workers for each of three arms at each injected hard-case rate, 0.1%, 1% and 10%, with 100M calls per worker. Filtered and eager exact predicates have zero wrong signs. Plain binary64 gives a wrong sign on each authored hard case. Filtered medians are 1.993623, 2.006738 and 2.897884 seconds, with 100,000, 1,000,000 and 10,000,000 exact fallbacks. The recorded environment identifies the shared remote host.

The [full-window AST analysis](M6-ANALYSIS.md) covers 116 windows and all 580 workers. Additional validator time relative to the producer has median 1.169669, p90 2.802846 and maximum 10.878051 across per-window paired-ratio medians. The AST driver measures the unchanged public validator with candidate recomputation. Its diagnostic phases execute later in the same worker, materialize the candidate relation and time reuse of that relation. RSS values are process high-water marks including producer state.

The original-native-input O4 series runs after the AST and O5 pilot jobs finish. Plain binary64, filtered exact and eager exact medians are 1.443786, 1.742752 and 7.541544 seconds per 100M calls. The median within-repeat filtered/plain ratio is 1.204833. All three predicate arms have zero wrong signs on those native inputs. The filtered arm uses 21,744 exact fallbacks per worker. These new measurements use the Intel server and GCC 11.4.0. The archived O4 measurements identify an AMD server and GCC 14.2.0 in their own receipts.

O5 then completes five fresh workers at each overlay scale. Each worker verifies all 100M backing rows with zero post-state differences and zero orphan overlays. Median durations are below. The ledger preserves each stage's min/max and process RSS.

| Overlay rows | Receipt rows | Apply, ms | Witness, ms | Full verification, s |
| --- | --- | --- | --- | --- |
| 3 | 4 | 2.827008 | 0.858064 | 5.501439 |
| 1,000 | 1,333 | 9.575174 | 2.112864 | 6.496089 |
| 100,000 | 133,333 | 581.915713 | 151.021388 | 77.984144 |

Full verification includes constructing the independent reference table and scanning all backing rows. The complete regenerated CSV hash and all partition row counts match the archived source. The generated Parquet bytes differ and have their own sealed manifest.

## Reproduction

The repository offline entry point verifies the ledger and these receipts using the Python standard library.

```sh
python -B replay.py
python -B scripts/recount_numbers.py s68.m2.execution_bound
python -B evidence/pvldb-s68-review-followup/recount.py
```

For the M1 and DVC native reruns, create a separate Python 3.12 environment with dbt-core 1.10.15, dbt-duckdb 1.9.6, DuckDB 2.0.1 and DVC 3.66.1. The recorded SQLite version for those runs is 3.49.1. M2 ran remotely with SQLite 3.45.3 and needs only Python's standard library. The SpreadsheetBench driver needs openpyxl 3.1.5, the original V1 archive and the pinned original evaluator identified in its receipt.

```sh
python -B binding_faults.py --plan PLAN.json
python -B equal_information.py ../ /path/to/separate-environment/bin/dbt
python -B dvc_status.py /path/to/separate-environment/bin/dvc
python -B spreadsheet_false_accept.py /data/publisher-v1.tgz /data/pinned-evaluation.py ../pvldb-a10-spreadsheetbench-scorer
python -B table7_timings.py ../
python -B sources.py ../ C4-UPSTREAM-LOOKUP.json --e9-positives E9-ADJUDICATED-POSITIVES.json
```

Run those commands inside this packet directory. The first M1 argument points to the surrounding evidence directory. The complete runtime versions and input digests are in each result receipt. The `*-PREEXECUTION.sha256` files seal the plan and executable correctness drivers before the successful measurements.

The full-window performance rerun uses Linux and the archived DuckDB 1.4.3, PyArrow 22.0.0 and sqlglot 28.0.0 environment. Bind generated SF10 databases and the SHA-verified ClickBench partitions with the portable preparer. It verifies every publisher partition and freezes the complete SQL/window roster before timing.

```sh
python -B prepare_ast.py --tpch /data/tpch-sf10.duckdb --tpcds /data/tpcds-sf10.duckdb --clickbench-store /data/hits --spill /data/spill /data/AST-FROZEN.json
python -B ast_cost.py run /data/AST-FROZEN.json /data/AST-RAW.jsonl
python -B ast_cost.py summarize /data/AST-FROZEN.json /data/AST-RAW.jsonl
```

`geometry-native/run-native.sh` rebuilds the exact native wedges from the pinned Natural Earth and dated OSM archives, derives arbitrary-precision signs, then times the four native-predicate arms. It needs GDAL Python bindings and a C++20 compiler. `geometry-pressure/run-pressure.sh` runs the analytic stress panel with the same exact-predicate core.

For O5, `o5-data/generate.sh` uses R 4.5.0, data.table 1.17.0 and PyArrow 26.0.1 to reproduce the archived complete CSV stream and partition counts. It records a fresh byte manifest for the generated Parquet files. Run `o5-data/run-cost.sh` in the DuckDB 1.4.3 timing environment. The O5 native measurement process uses one pinned CPU and a 400MB DuckDB memory limit. Full verification includes independent reference-table construction and the scan of all 100M backing rows.

The retained renderer sets `R_LIBS_SITE` to `R_HOME/site-library`. Make data.table available through that library or `R_LIBS_USER`.

## Q39 numerical scope

The original M5 mutation changes the January mean at warehouse/item `(1,259)`. Its exact reference is `1093/4`. Recomputing the binary64 multiplication puts it 2,403,532,417 representable steps beyond the 2-ULP envelope. This identifies the mutated field for manuscript alignment. The optional a-priori bound for the engine's parallel variance algorithm remains a separate derivation.
