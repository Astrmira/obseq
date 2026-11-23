# A2 independent typed checks for grouped ClickBench windows

An Arrow/NumPy source scan checked both frozen DuckDB thread outputs
for Q31–Q33 and Q39–Q42 on all 99,997,497 rows. All 14 outputs passed.
The [earlier Q18 check](../pvldb-a7-typed-candidates/FULL-RESULT.json)
accepted both of its native outputs. Together the results confirm
both answers for all seven stock queries whose native output bags
differed. Q31 is an additional split-window control whose native
bags were equal.

For each output the scan validates the source group key and the exact
count and integer sum. Integer means are computed from exact rational
values before comparison with the native binary64 values. The native
stock queries rank these groups by count. The independently derived
group-count histogram fixes the required number of groups at each
score inside the original OFFSET/LIMIT band. With distinct source
keys this also establishes inclusion of every mandatory interior group.
The histogram checks both edge peer sizes against the prior census.

The scan builds an all-row duplicate census for WatchID/ClientIP,
combines exact coded engine/IP keys for Q31, and directly aggregates
the filtered source groups for Q39–Q42. The claimed keys for Q31–Q33
include native outputs and all first-applicable mutations before the
scan. Comparisons retain UTC-derived day semantics and use the stock
exact predicates. The verifier reads the stock query SHA and the
candidate and acquisition manifests before using the results.

The E2 matrix compares one native 1-thread output per query with
its 8-thread reference. It contains seven legal observations and
15 independently rejected mutations (M1, M2, M5 and M6). Numeric
scale-zero Arrow decimals are transported as exact integers to
the ordinary observers, date fields as ISO dates, and byte hash
uses the IPC carrier. SQLite integrity is inapplicable here.

| Observer | False rejects / 7 | False accepts / 15 |
| --- | ---: | ---: |
| Ordered, bag, set or IPC fingerprint | 6 | 0 |
| Relative tolerance, either tested threshold | 6 | 8 |
| Exact column sums | 5 | 4 |
| Row count or visible schema | 0 | 15 |

These are per-query observed controls, with one common comparator
interface. The remaining operators and E5 configurations are
outside this receipt. [RESULT.json](RESULT.json) preserves each decision.

```sh
python -IB run.py ACQUISITION STOCK_SQL FULL_OUTPUT ../remote-clickbench-full/run.py ../pvldb-a2-q39-real-output/run.py ../submission-e-series-native-evidence/e23/check.py STORE_1 STORE_2
```

Use the pinned Python environment with PyArrow 22.0.0 and the intact
publisher shards. The captured data and source keys are private.
