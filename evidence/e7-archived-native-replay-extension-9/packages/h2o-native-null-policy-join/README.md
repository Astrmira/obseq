# E3 / F2: missing-value policy changes a native relation, not just ingestion

Input is the complete unchanged 10M H2O Join left CSV from the [pinned official benchmark generator](https://github.com/duckdblabs/db-benchmark/tree/3b074bc3190468803b3a890301f87ce455114d20); SHA enforced in check.py. This is generated benchmark data rather than a measured production population. The query is authored, not vendor Q3. It splits the source into disjoint sides by v1<50 vs v1≥50 over native DECIMAL(16,6). Exactly 500,000 NULL split values were outside both sides under this predeclared rule. Remaining side counts are 4,748,329 and 4,751,671 before any policy-specific filtering. Each side uses composite nullable integer key (id1,id2). Nonkeys, including nullable id3, are not part of the declared join condition.

| Policy | Matched pairs (bag cardinality) | Unmatched admitted left rows | Pairs involving a NULL id3 payload |
|---|---:|---:|---:|
| Ordinary componentwise equality | 214,340,026 | 237,423 | 20,884,339 |
| Componentwise null-safe equality | 5,854,757,535 | 0 | 574,699,642 |
| Drop only incomplete keys first | 214,340,026 | 0 | 20,884,339 |
| Drop any incomplete row across all seven fields | 193,455,687 | 0 | 0 |

For each key bag, matched pairs have multiplicity L(k)×R(k) under the selected relation; no distinct-row approximation. With ordinary equality, NULL-bearing keys are not eligible for matching, but the left input rows are not removed. The key-only drop agrees on the inner pair relation while changing the left-survival result: ordinary has 237,423 additional unmatched left rows for a left-preserving consumer. Null-safe matching adds exactly 5,640,417,509 pairs, all within the id2-NULL, id1-nonnull bucket; it does not mix different id1 values. Global dropping eliminates even ordinary nonnull-key pairs: 20,884,339 lost in this fixture, exactly those with at least one NULL id3. That equivalence is observed in this input, not a rule for other tables.

DuckDB 1.4.3 groups all 9.5M admitted source occurrences into side/key histograms once. Native SQL multiplies frequencies under each declared predicate and counts left-side membership, without materializing the billions of pairs. A separate Python stream independently forms bags from the unchanged CSV and matches every one of the 95,010 histogram cells per side and every output metric. A separate native literal non-factorized SQL join verifies ordinary/null-safe/key-complete/global-complete pair counts on the predeclared first 5,000 physical records: 77 / 1,549 / 77 / 67. Its input rows are independently compared exactly to the CSV prefix. No performance test, engine defect claim, broader missingness interpretation, or raw data export.

Replay with existing DuckDB 1.4.3; original source may be passed as the one positional argument. From the packet directory:
```sh
set -o pipefail
sha256sum -c SHA256SUMS
PYTHONPATH=/tmp/pvl-eab-submission/e1/input/duck143 python3 -B check.py /workspace/shared/eab-h2o-join-single-lane-guarded/J1_1e7_NA_5_0.csv | cmp - RESULTS.json
```
