# Same-host timing and Q39 numerical follow-up

This packet completes the same-host comparison for the O1–O5 timing table.
O1, O2 and O3 were rerun on the Intel Xeon Platinum 8352V used for the
[previous O4 and O5 measurements](../pvldb-s68-review-followup/README.md).
Each timed arm uses five fresh workers, CPU 95, warm OS caches, and a
single DuckDB thread where applicable. The series ran sequentially.
See [TABLE7-ENV.txt](TABLE7-ENV.txt) for the measured environment and
[TABLE7-RESULT.json](TABLE7-RESULT.json) for check-only times, min–max
ranges and paired ratios.

- O1 uses the original 100M-row, 2,062,352,384-byte SQLite carrier with
  the exact archived file and typed logical digests. O1 runs with SQLite
  3.53.1. Native count/sum, raw file SHA-256, backup only and backup plus
  typed digest are separate arms. The backup destination is in memory.
- O2 and O3 use DuckDB 1.4.3 and the 100M-row H2O GroupBy snapshot
  reconstructed for O5. Its full generated CSV digest and all 100
  partition row counts match the archived generation. The physical
  Parquet digests are from the separately verified regeneration.
  O2 measures the native Q1 producer, epoch lookup and full exact check
  in separate workers. The O3 workers keep the same producer and check
  in one process, with a separate producer-only arm.
- The O4 pressure comparison uses the same caller, input stream,
  return signature and sign accounting for both kernels. GCC keeps the
  common loop from being specialized for either target. The archived
  filtered predicate is unchanged. The authored hard inputs have exact
  determinant `m(m-2)-(m-1)^2=-1`. The exact filtered arm falls back on
  each hard input and the binary64 arm returns zero there. The native
  wedge timings in Table 7 remain a distinct workload.

O1 and O2 ratios divide separate arm medians. For O3 use the median of
each check worker's check/producer ratio. For native geometry use the
median of the five matching repeat ratios and for O5 use the median
within-worker witness/apply ratio. The time dispersion report is calculated
over the 14 displayed time cells, all within 30% of their respective
medians in the resulting table. At 0.1%, 1% and 10% fallback the pressure
panel's paired ratios are 1.026, 1.051 and 1.267, respectively. There are
separate ledger entries for
the O4 eager/filtered ratio, each O5 witness/apply and verification median,
and all 580 previously completed AST workers.

## Native timing replay

Use a writable scratch directory and set `P` to this packet and `E` to
the public evidence root. Select a single allowed CPU. Verify the SQLite
input against [its frozen reference](../e6-o1-native-sqlite-single-file-100m/REFERENCE.json).
Run the unchanged [O1 driver](../e6-o1-native-sqlite-single-file-100m/run.py)
in `run` mode with that input, the frozen reference and Python linked to
SQLite 3.53.1. Redirect stdout to `O1-RAW.jsonl`.

For O2/O3 set `H` to the parent of the `native-100m-hive/` tree named by
the [regenerated H2O manifest](../pvldb-s68-review-followup/o5-data/REGENERATED-INPUT.sha256).
Verify that manifest in `H`. Put the
[pinned upstream DuckDB GroupBy script](https://github.com/duckdblabs/db-benchmark/blob/3b074bc3190468803b3a890301f87ce455114d20/duckdb/groupby-duckdb.py)
at `$H/../eab-h2o/groupby-duckdb.py` and verify its SHA-256
`d23ede9d21ca8933f2aea169639a5ffc8cea2b05ad24b2325a02df495d6ade5f`.
Run `python -IB "$P/run_table7.py" "$H" "$CPU"` with DuckDB 1.4.3.
It invokes the original O2/O3 workers and reruns their correctness controls.

For the pressure comparison, compile and run from the same scratch directory.

```sh
c++ -std=c++20 -O3 -fno-fast-math -ffp-contract=off "$P/geometry_pressure.cpp" -o pressure
echo 'repeat,mode,per_mille,n,ns,rss_kib,fallbacks,mismatches,negative,zero,positive' > PRESSURE-RAW.csv
for rep in 0 1 2 3 4; do
  for rate in 1 10 100; do
    for offset in 0 1; do
      taskset -c "$CPU" ./pressure "$rep" "$(((rep+offset)%2))" "$rate" 100000000 >> PRESSURE-RAW.csv
    done
  done
done
```

## Q39 independent error certificate

[Q39-BOUND.md](Q39-BOUND.md) derives a relative error radius for Welford's
update and DuckDB's actual pairwise combine, then includes the integer
average, square root and final division. [Q39-RESULT.json](Q39-RESULT.json)
reports the maximum and threshold stability across all 1,019,995 January
and February groups. The maximum relative bound is 6.729e-11, and zero
group intervals can change the strict threshold decision. All 2,433
projected rows in each archived native arm pass, and the three original
negative controls are rejected. Cases with a NULL result or exact zero
variation are handled explicitly. The source carries exact integer group statistics
and the previously sealed projected results, which are kept separate from
the calculation of the radius.

```sh
python -IB "$P/q39_bound.py" "$P/Q39-STATS.csv.gz" \
  --native-directory "$P/q39-native" \
  --native-digests "$E/pvldb-s68-review-followup/Q39-M5-DISTANCE.json"
```

To regenerate the statistics, specify a fresh output name instead and add
`--database /path/to/tpcds-sf10.duckdb` under DuckDB 1.4.3. Use the pinned
[TPC-DS generation procedure](../e7-archived-native-replay-extension-10/packages/tpcds-sf10-q39-exact-threshold/README.md).
The measured source database SHA-256 is in [PROVENANCE.json](PROVENANCE.json).
The online aggregation is integer-only for this extraction. Neither CWI nor
the observed 2 ULP drift is an input to the error calculation.
