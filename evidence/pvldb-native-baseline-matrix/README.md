# Native comparator matrix for benchmark outputs, E7 holdouts and E9 release pairs

The table comparators use pandas 2.2.3 (default, `check_like`, `check_dtype=False`),
Polars 1.31.0 (default and row-order ignored), and DataComPy 0.16.8 (declared
keys or physical positions). The E2 observation functions are loaded from the
frozen source by the Q39 runner. SQLite integrity and byte identity are NA for
these in-memory tables. When a declared key is missing or nonunique, the
DataComPy cell is NA. The original TPC receipt has the six frame configurations.
For the holdouts and 22 archived natural pairs, separate receipts cover
native DVC/GX (`EXTRA-RESULT.json`), four DuckDB Python SQLLogicTest settings
(`SLT-RESULT.json`), configured dbt relationships and fixed typed bag
(`DBT-RESULT.json`), and Deequ row count and fixed typed bag
(`DEEQU-RESULT.json`). These four receipts and the six frame comparators
cover the 16 E5 configurations. They share 714 comparator input pairs.
Deequ executes 308 distinct encoded payload pairs and maps its outcomes
back through exact typed input identity. SLT admits lossless explicit SQL scalar declarations
and uses native hash output for the configured hash arm. Each test records NA
for its unsupported inputs. `slt-frozen.py` retains the exact adapter pinned
in `SLT-INPUTS.sha256` for these archived results.

## Full E5 benchmark matrix

`BENCHMARK-E5-RESULT.json` contains 44 comparisons with all 16 configurations
attempted. Forty comparisons use complete emitted results from nine
ClickBench queries and five SF10 TPC queries. The separate H2O Q3 cohort uses
the two changed rows witnessed in the 10M-row join for each of three
comparisons. The UserID left-join cohort uses the fixed 6,199-row projection
from each of the two previously pinned 49,998,749-row rollups. The native
source scans and original full-output checks are described in the
[join](../pvldb-a2-clickbench-left-join/README.md) and [H2O](#h2o-q3-source-replay)
sections.

Of the 40 complete-result comparisons, 13 are legal and 27 are illegal.
The fixed typed bag configurations in dbt and Deequ reject all 27 illegal
arms and nine legal arms. The five pandas and Polars configurations detect
23/27 illegal arms. The stock Deequ and GX count checks detect 3/27. All
four SQLLogicTest configurations have nine NA comparisons where the stock
literal carrier cannot preserve the input. On the 6,199-row left-join
projection, 14 configurations detect the fault and the two row-count
checks accept it.

`BENCHMARK-DATACOMPY-KEYS.json` scores the same 40 complete-output arms
with positional alignment and explicit non-null unique source grouping
keys. ClickBench positional misclassifies 9/10 legal and 7/19 illegal
arms. Natural keys misclassify 7/8 applicable legal and 0/18 applicable
illegal arms, with 2 legal and 1 illegal arm marked NA. TPC positional
misclassifies 1/3 legal and 0/8 illegal arms. Natural keys misclassify
1/1 applicable legal and 0/5 applicable illegal arms, with 2 legal and
3 illegal arms marked NA. The receipt identifies projected key columns
and every unsupported arm. The source query definitions determine each key,
including the two grouping columns of Q33 and five of Q40.

The source adapters generate private comparison inputs. Pass `--pairs PATH`
to the A2 ClickBench typed-window runner, the A7 cutoff scorer, and the TPC
and H2O runners. Use `left_join_pairs.py` on the two pinned private rollups.
Combine the five arrays and run the commands below in the recorded runtimes.
`BENCHMARK-E5-INPUTS.sha256` pins the input arrays and adapters. The grouped
Deequ test guards a count of differing Spark row multiplicities while
retaining its separate stock size check. The harness verifies the resulting
verdicts against exact typed reference counts.

```sh
python -B e5_pairs.py frames PAIRS.json > RECEIPTS/FRAMES-RESULT.json
python -B e5_pairs.py extra PAIRS.json > RECEIPTS/EXTRA-RESULT.json
python -B e5_pairs.py slt PAIRS.json --slt-root SLT_ROOT --old-adapter ARCHIVED_SLT_ADAPTER --upstream-seal UPSTREAM_SEAL > RECEIPTS/SLT-RESULT.json
python -B configured.py dbt PAIRS.json > RECEIPTS/DBT-RESULT.json
python -B configured.py deequ PAIRS.json SPARK_HOME DEEQU_JAR DeequGrouped.scala > RECEIPTS/DEEQU-RESULT.json
python -B merge_e5.py RECEIPTS
python -B e5_pairs.py keys PAIRS.json > DATACOMPY-KEY-ARMS.json
python -B merge_e5.py BENCHMARK-E5-RESULT.json --key-diagnostic DATACOMPY-KEY-ARMS.json
```

## TPC SF10

`TPC-BUILD.log` binds local DuckDB 1.4.3 generated data to the signed extensions.
`TPC-RESULT.json` uses the sealed Q39 source outputs, regenerates Q59 from the
TPC-DS SF10 snapshot, and re-executes the existing source-oracle drivers for
Q86, Q11 and Q21. The Q59 ascending and descending within-peer controls yield
the same 100 projected rows in this snapshot. Its deleted-row control is
visible to bag equality and all six table configurations, and passes set and
schema equality. `Q59-INDEPENDENT-RESULT.json` records a second source
calculation using exact Decimal subtotals over 11,213,853 scanned sales,
Python week and store pairing, and date-dimension multiplicities. The
independent calculation and the typed window checker agree on all five
arms, including the rejection of a changed ratio with the same 100 rows.
The [SF1](Q59-SF1-INDEPENDENT-RESULT.json) and [SF10](Q59-INDEPENDENT-RESULT.json)
reference receipts each count one distinct projected row with multiplicity
49 in the split peer band. The window takes two copies of that row, so all
selections within that band produce the same projected multiset. Run
`python -B q59.py QUERIES_JSON TPCDS_DB --verify-window ../pvldb-a1-query-inventory/verify_windows.py`
with a DuckDB 1.4.3 TPC-DS database at either scale.
Q86 has 57 incorrectly inferred grouping roles out of 168
groups before LIMIT when using nullness instead of `GROUPING`. Q11's bundled
qualification fraction returns 0 rows, and the SF10 workload fraction returns
8,685. Reversing Q21's secondary key changes eight of the 100 head members
and keeps the numeric column sum. Q39's M5 control has relative change
approximately 5×10⁻⁷ beyond the source ULP envelope. CWI and E2 at 1e-5
accept it, while E2 at 1e-9 rejects it. The publisher H2O checksum and
independent projected H2O witness results remain in [E8](../e8-stock-comparator-consequences/README.md).
`TPC-ANSWER-ADMISSION.json` records DuckDB 1.4.3's exposed TPC-H answer
scales SF0.01, SF0.1 and SF1. Querying the signed TPC-DS answer function
raises an SF10 unsupported-scale error. The SF10 matrix uses the
documented source references and the stock CWI check where applicable.

Use Q11's and Q21's archived `check.py` and Q86's archived `q86.py` under the
names `q11.py`, `q21.py` and `q86.py`, respectively. Supply the same frozen
query manifest layout used by the A1 runner and the exact generated
`tpch.duckdb` and `tpcds.duckdb` SF10 snapshots. See `TPC-INPUTS.sha256` for
the archived runner identities and query-specific source packets.

## Holdouts

`ORIGINAL-RESULT.json` scores one frozen observed payload for each of the
original 108 independent cases. The carrier keeps native scalar kinds where
both sides fit one field type, preserves the rows of emitted collections and
explicitly serializes heterogeneous nested fields. Each chosen fixed reference
is checked with the frozen independent reference interpreter. The references
are new fixed exemplars selected with the original corpus available. The
result describes comparator behavior against these exemplars. It has 54 legal
and 54 illegal cases. pandas default rejects 23/54 legal cases and detects
54/54 illegal cases in this carrier. E2 row count accepts 47/54 illegal cases.

`LATER-RESULT.json` scores all six panels and 138 distinct cases, with 228
pooled observations (180 legal, 48 illegal) and 24 extra alternate-contract
decimal controls. It replays DuckDB on the ordered-intervention panel and
uses the existing sealed outputs or legal-family projections in the other
panels. pandas default rejects 19/180 legal observations and accepts 11/48
illegal observations. Polars ignoring row order has 9/180 and 12/48,
respectively. The observations include several producer arms per case.

`HOLDOUT-MATRIX.json` joins the six native frame verdicts, E2, and the four
supplemental evidence packets by exact case and arm. It summarizes all 336
scored observations by original family or later panel, with each NA counted.

## H2O Q3 source replay

`H2O-GENERATOR.log` records the unchanged R 4.5.0 and data.table 1.17.0
generator on the remote host. `h2o.py` verifies all four generated CSV
digests before running the pinned Q3 SELECT and the independent full-output
projected association check. Clean and two-payload exchange both produce
10,000,000 rows, identical types, exact `v2` sum 423957578.770283, and the
same publisher checksum `475042480.57;423957578.77`. The one-unit control
changes the checksum. All six table settings and the two E2 tolerance
settings reject the exchange on its two actual changed native rows. Full
output shape, sums and association checks scan the whole 10M result. Only
the witnessed changed rows are supplied to the external table comparators.

## Natural faults

`NATURAL-RESULT.json` adds eight release pairs with trusted archived native
rows and independently established reference values. The new and old
observations are paired by family. Ordered comparison detects 8/8 old-version
faults and row count detects 1/8. Both use the declared projection. The
next 14 are in `NATURAL-EXTENDED-RESULT.json`. Their archived observations
include legitimate alternate tie selections. The [A4 roster](../pvldb-a4-natural-roster/README.md)
combines both packets with the earlier seven pandas pairs at release-pair granularity.

```sh
python -B original.py E7_SCORED ORIGINAL-REFERENCES.json A2_RUNNER FROZEN_E2
python -B later.py PANELS REPRESENTATIVE_RUNNER VALUE_RUNNER A2_RUNNER FROZEN_E2
python -B natural.py E9_ARCHIVE A2_RUNNER FROZEN_E2
python -B natural_extension.py E9_ARCHIVE A2_RUNNER FROZEN_E2
python -B file_and_shape.py MATRIX PANELS REPRESENTATIVE_RUNNER VALUE_RUNNER
python -B slt-frozen.py MATRIX PANELS REPRESENTATIVE_RUNNER VALUE_RUNNER SLT_ROOT ARCHIVED_SLT_ADAPTER UPSTREAM_SEAL
python -B configured.py export MATRIX PANELS REPRESENTATIVE_RUNNER VALUE_RUNNER > PAIRS.json
python -B configured.py dbt PAIRS.json
python -B configured.py deequ PAIRS.json SPARK_HOME DEEQU_JAR ARCHIVED_SCALA
python -B tpc.py PRIOR_DRIVERS QUERY_BUNDLES DATASET Q39_RECEIPTS A1_VERIFIER A2_RUNNER FROZEN_E2 --cwi STOCK_ROUNDINGDIFF
python -B h2o.py ARCHIVED_PROJECTED_OBSERVER H2O_INPUT STOCK_JOIN STOCK_HELPERS A2_RUNNER FROZEN_E2
```

`REPRESENTATIVE_RUNNER` is `../pvldb-a3-independent-panel/run.py`,
`VALUE_RUNNER` is `../pvldb-a3-heldout-value-observers/run.py`,
`A2_RUNNER` is `../pvldb-a2-q39-real-output/run.py`, and `FROZEN_E2` is
`../submission-e-series-native-evidence/e23/check.py`.
