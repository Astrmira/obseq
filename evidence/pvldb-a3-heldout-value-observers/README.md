# A3 ordinary observers on two sealed E7 panels

This packet scores 48 distinct cases from two later-138 panels
with E2 observers and three pandas 2.2.3 configurations from E5.
The candidates and truth labels are the original sealed cases.

| Panel | Scope | pandas false rejects | pandas false accepts |
| --- | --- | ---: | ---: |
| Keyed aggregate cancellation | Source sorted lexicographically; candidate keeps its authored row order | 10 / 12 | 0 / 12 |
| Ordered intervention receipts | Values after committed/rolled-back native DuckDB work | 0 / 12 | 9 / 12 |

All three pandas configurations agree within each panel. On the
keyed-aggregate panel, E2 multiset equality accepts all 12 legal
and rejects all 12 illegal candidates. On the intervention panel,
the ordinary projection includes only the two post-state columns.
The sealed labels also account for committed write events, so nine
illegal executions have the same visible values as their intended
execution. Native DuckDB 1.4.3 replay reproduces every archived
DuckDB 2.0.1 comparison in the intervention panel before scoring.

With the earlier [24-case representative pilot](../pvldb-a3-independent-panel/README.md),
this brings ordinary E2 coverage to 72 of 138 cases in the later
independent cohort. The original 108 and other tool configurations
remain separate.

```sh
python -IB run.py ../e7-independent-native-suite/later-138/panels ../pvldb-a2-q39-real-output/run.py ../submission-e-series-native-evidence/e23/check.py
```
