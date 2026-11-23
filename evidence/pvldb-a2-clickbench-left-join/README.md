# A2 full native UserID left join

DuckDB 1.4.3 evaluates an exact left join and a right-only float64
round-trip on all 100 ClickBench source shards. The arms use alternating
row positions in each shard, with 49,998,749 left and 49,998,748 right
occurrences. The right-hand float64 value is converted back to an integer
for equality, keeping the left ID in its exact domain. The native counts
agree with the earlier independent frequency reference.

| Native observation | Exact IDs | Right side via float64 |
| --- | ---: | ---: |
| Matched pairs | 2,246,850,803 | 53,483,855 |
| Left occurrences without a match | 3,593,089 | 48,596,836 |
| Output rows of the raw left join | 2,250,443,892 | 102,080,691 |
| Rows retaining one record per left occurrence | 49,998,749 | 49,998,749 |

The engine counts the complete raw joins. The scoped business output is
materialized as two Parquet files with shard, physical source row, UserID
and the number of matched pairs. Summing those match counts and adding
one row per zero-match left occurrence reproduces the raw join counts.
Working directly from the materialized products also reproduces the
independent exact matching result, with 2,193,366,948 pairs lost (97.62%).

Raw join cardinality detects the fault. The per-left row count and
schema accept the corrupted rollup; 45,003,747 corresponding rollup
records have different values. Exact numeric sums, keyed exact equality,
both relative tolerances and all three full-output pandas 2.2.3
configurations reject it. The whole-rollup comparisons use the declared
left occurrence identity for alignment. A fixed stride of 16,384 source
rows also gives 6,199 paired rows per arm for the original E2
observer functions, with the same decisions on overlapping checks.

The pandas calls use the default, relaxed-dtype and check-like settings.
The [wider E5 matrix](../pvldb-native-baseline-matrix/README.md#full-e5-benchmark-matrix)
adds 16 configurations on the same fixed projection. Fourteen detect the
fault, and the two row-count configurations accept it. The two raw per-left
products contain UserIDs and remain private.

```sh
python -IB run.py ACQUISITION ../pvldb-a7-typed-candidates/FULL-ID-CAST.json ../remote-clickbench-full/run.py ../pvldb-a2-q39-real-output/run.py ../submission-e-series-native-evidence/e23/check.py OUTPUT STORE_1 STORE_2
```

Replay with DuckDB 1.4.3, PyArrow 22.0.0 and pandas 2.2.3.
