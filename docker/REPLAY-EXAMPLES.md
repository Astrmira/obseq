# Representative table replays

Run from the repository root with the Tier 2 Python environment. These
commands take explicit scratch paths for generated outputs. For Linux
commands run from the supplied image, mount that scratch directory read-write.

## Table 4 — independent TPC-DS Q59

Fetch the signed Linux x86-64 DuckDB 1.4.3 TPC-DS extension and generate the
SF10 snapshot. `build_tpc.py` checks the decompressed extension's SHA-256.

```sh
mkdir -p "$SCRATCH"
curl -fsSL https://extensions.duckdb.org/v1.4.3/linux_amd64/tpcds.duckdb_extension.gz |
  gzip -d > "$SCRATCH/tpcds.duckdb_extension"
python -B build_tpc.py tpcds 10 "$SCRATCH/tpcds.duckdb_extension" \
  "$SCRATCH/tpcds.duckdb" "$SCRATCH/queries.json"
python -B evidence/pvldb-native-baseline-matrix/q59.py "$SCRATCH/queries.json" \
  "$SCRATCH/tpcds.duckdb" --verify-window evidence/pvldb-a1-query-inventory/verify_windows.py
```

The native output and both within-peer orders pass. The 99-row control
and a 100-row control with a changed ratio fail. [Archived verdicts](../evidence/pvldb-native-baseline-matrix/Q59-INDEPENDENT-RESULT.json)

## Table 6 — pandas positional write

Use the Tier 2 environment for pandas 2.2.3. Install pandas 3.1.1 and
NumPy 2.5.5 into a separate site directory with `python -m pip install
--target "$NEW_SITE" pandas==3.1.1 numpy==2.5.5`. Both arms load NumPy
from this directory.

```sh
for arm in old new; do
  python -B evidence/pvldb-a4-natural-roster/pilot.py "$NEW_SITE" "$arm" \
    evidence/pvldb-a2-q39-real-output/run.py \
    evidence/submission-e-series-native-evidence/e23/check.py > "$SCRATCH/pandas-$arm.json"
done
python -B evidence/pvldb-a4-natural-roster/verify_contracts.py evidence
```

The old release has four incorrect positional-write observations out of six.
The new release has zero. [Old observations](../evidence/pvldb-a4-natural-roster/OLD-PILOT.json)
· [New observations](../evidence/pvldb-a4-natural-roster/NEW-PILOT.json)
· [Per-arm contract decisions](../evidence/pvldb-a4-natural-roster/CONTRACT-CHECKS.json)

## Table 7 — SQLite source scan and file digest

Use Linux and Python with SQLite 3.53.1. The build writes a 2.1 GB database.

```sh
packet=evidence/e6-o1-native-sqlite-single-file-100m
python -B "$packet/summarize.py" "$packet/RAW.jsonl" | cmp - "$packet/SUMMARY.json"
python -B "$packet/run.py" build --source "$SCRATCH/o1.sqlite"
for arm in sqlite_native_read raw_file_sha256; do
  python -B "$packet/run.py" worker --source "$SCRATCH/o1.sqlite" \
    --ref "$packet/REFERENCE.json" --method "$arm"
done
```

The workers check the exact count, sum and file SHA-256 before emitting valid
timings. The first command recomputes the archived five-repeat medians.
New timings vary with CPU and I/O. [Archived timing samples](../evidence/e6-o1-native-sqlite-single-file-100m/RAW.jsonl)
