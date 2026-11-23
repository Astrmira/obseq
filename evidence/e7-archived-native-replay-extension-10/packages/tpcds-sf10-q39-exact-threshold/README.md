# EA&B E1: TPC-DS SF10 Q39 threshold and binary64 control

Dataset: original `CALL dsdgen(sf=10)` from the [DuckDB TPC-DS extension](https://duckdb.org/docs/lts/core_extensions/tpcds), with the already matched official DuckDB 1.4.3 wheel and signed extension. This is all tables of a local DuckDB-generated SF10 database, not a scaled sample or the external TPC qualification data. [DuckDB 2.x documents a generator change](https://duckdb.org/docs/2.0/core_extensions/tpcds), so do not silently substitute the latest release. The SQL is the extension's shipped Q39, no predicate or aggregation changed in the measured native result. The extra month-admission diagnostic uses the unchanged CTE and switches only its final projection to compare the exact January and February domain before the join; it is labeled separately. No full 99-query SF10 execution, approved TPC result, qualification or comparative runtime.

Native result: 2,433 exact January/February matched keys; 458 rows differ in their binary64 fields across the two thread settings, each at most 2 ULP from the exact reference. Across 1,019,995 individual January/February groups there are zero exact-threshold ties, and the smallest nonzero absolute squared-CV gap to 1 is 23/2577987. Both native monthly admitted key sets exactly match the rational criterion, and no output key changes. A fresh native replay kept the same keys and predicate choices; 460 instead of 458 rows differed as binary64 values (maximum at most 2 ULP again). A portable replay with SQL extracted from the signed extension also kept exact key sets and recorded 478 differing rows. The SF1 predecessor saw 57/243 binary64-different rows (also max 2 ULP). The larger example increases absolute witness count, not the observed fraction of drift; this is a controlled replication and predicate-sensitivity qualification, not a new instance of numerical instability or a claim about prevalence.

The Python oracle reads generated integer inventory records across the two relevant months and independently filters the dimensions. From count n, sum s and sum of squares u, the exact rational squared coefficient of sample variation is n*(n*u-s*s)/((n-1)*s*s) for n>1 and positive mean. Compare this rational to 1 before computing a square root. For admitted native results it verifies nearest binary64 to exact sqrt by rational comparison to squared midpoints of adjacent doubles. The oracle enumerates every output key, and keeps the native binary64 vectors from both thread configurations and exact fractions for deterministic verification of this frozen execution. Each arm must agree with the mathematically exact key set. Native reduction order can vary on replay; exact floating output identity is not an expected contract. Individual float deviations are not a checker weakness by themselves; a typed tolerance chosen in advance can admit numerical drift while keys and threshold membership are measured separately.

Resources: no new download; native generation uses a disk-backed file, 2 engine threads, 1,300 MB engine memory setting, 800 MB spill setting and an external 420-second initial timeout. The script checks for at least 7 GiB free before launch; 5 GiB was an occupancy planning target, not an enforced OS quota. Keep data and spill away from small /tmp. Use the pinned CPython 3.12 [DuckDB 1.4.3 wheel](https://pypi.org/project/duckdb/1.4.3/) and the [matching signed official extension](https://extensions.duckdb.org/v1.4.3/linux_amd64/tpcds.duckdb_extension.gz). Put the wheel beneath input/, unpack it to input/duck143 and decompress the signed extension into input/ext143/; validate exact hashes before running. The SQL is extracted directly from that extension and its SHA checked. This packet distributes derived numeric observations in text shards, not the binary extension, input database or upstream SQL. A fresh writable target directory, with no tpcds.duckdb file, may be used to regenerate.

```sh
set -o pipefail
E=/path/to/pinned/duckdb-runtime
W=/path/to/writable/sf10-rebuild
mkdir -p "$W"
export TMPDIR="$W"
P=$PWD
(cd "$E" && sha256sum -c "$P/INPUTS.sha256")
timeout 420s python3 -IB generate.py "$E" "$W" tpcds > "$W/tpcds-counts.json"
python3 -c 'import json,sys; a,b=(json.load(open(p)) for p in sys.argv[1:3]); assert a["tables"]==b["tables"]' tpcds-counts.json "$W/tpcds-counts.json"
timeout 250s python3 -IB q39.py "$E" "$W" > "$W/q39-result.json"
python3 -IB check.py "$W"
python3 -IB check.py "$P"
sha256sum -c SHA256SUMS
```
