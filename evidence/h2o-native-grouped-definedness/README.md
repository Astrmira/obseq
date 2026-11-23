# EA&B E1: native H2O db-benchmark GroupBy Q10 definedness

The [original H2O repository](https://github.com/h2oai/db-benchmark) was revived by [DuckDB Labs](https://duckdb.org/2023/04/14/h2oai). This run pins its [maintainer commit](https://github.com/duckdblabs/db-benchmark/tree/3b074bc3190468803b3a890301f87ce455114d20), selects the checked-in active 10M-row 5%-missing shape, and runs the original R generator with arguments `1e7 1e2 5 0` (seed 108 as published) unchanged. Local Debian R 4.5.0 and data.table 1.17.0 official packages were unpacked in scratch, no system installation. Resulting intact inputs, original scripts, and packages are hash-pinned in INPUTS.json. This is official-generator synthetic benchmark data, not measured production. It is not claimed byte-identical to the publisher's multi-size DuckDB blob. Publisher-host HEAD confirmed the groupby file is 11,621,904,384 bytes and join file 14,904,471,552; the older S3 URLs in download_data.sh returned HTTP 404 in this environment. No large native DB download was attempted. A separate initial original full-size join generator attempt exited 137 before producing complete inputs; no partial join input was admitted to this packet.

All 10 pinned DuckDB GroupBy SELECTs and their checksum SELECTs execute natively with the publisher's typed ingestion (including FLOAT for v3 and enum groups). The runner extracts the publisher's repeated SQL verbatim, but this is not a stock performance harness or timings claim. Only Q10 has the independent comparator below. No rewrite to the grouped SQL is needed for the native results arm; the extra NULL-to-zero view is explicitly a separate checker sensitivity arm.

At Q10 the native DuckDB and stock R data.table aggregate bodies both account for all 10,000,000 source records and emit 9,999,993 groups. The sets of (six keys, count) on which their respective native sum is undefined or zero match exactly: 499,998 have DuckDB NULL versus data.table zero. Neither engine emits the other label anywhere. This is a legitimate dialect/declared policy difference: DuckDB SQL SUM over only NULL has no nonnull input; R sum with na.rm=TRUE over an empty retained vector returns its identity zero. The aggregate type difference (SQL FLOAT inputs vs R DOUBLE) is intentionally not treated as additional correctness evidence. A streaming Python CSV oracle independently checks all 99,799 six-key/count entries at a preselected id001 stratum, including 4,896 all-missing groups.

For an unambiguous fair checksum control, hold SQL engine, input/precision, keys, and counts fixed; replace only NULL group sums by zero. Publisher Q10's three-decimal rendered SUM(v3) and SUM(count), along with row/column counts, remain unchanged here. A separate 20-decimal-place native checksum agrees; no claim is made of floating reduction order or raw bit identity. The explicitly matched comparison does not assert byte-equal raw checksums between R and SQL, nor equivalence under other field values or all-null global results. At least one other defined group is required for the nonempty global SUM versus zero-fill argument. A per-key Boolean definedness bit (or native NULL-bearing keyed results) distinguishes these arms; globally counting defined results suffices for this point control, but does not detect reassignments at equal totals. No general judgment of tool correctness, incidence estimate, or novelty claim.

The replay extracts the two repeated native query bodies and checksum lists from the digest-verified upstream scripts. This packet does not redistribute those scripts, source SQL, or benchmark data.

Replay from this directory:
```sh
set -o pipefail
sha256sum -c SHA256SUMS
python3 -IB check.py /path/to/h2o-replay /path/to/duckdb-1.4.3/site-packages | cmp - result.json
```

## Recreate pinned inputs on Debian 13 amd64

No root access or package setup scripts are needed. From this packet directory, put the absolute packet path in `P` and put scratch on a volume with several GiB free. These are the acquisition and generator steps (not network timing measurements):

```sh
set -eu
P=$PWD
S=/path/to/writable/h2o-rebuild
mkdir -p "$S"/generated
cd "$S"
curl -fL --max-filesize 15000000 https://codeload.github.com/duckdblabs/db-benchmark/tar.gz/3b074bc319 -o pinned.tar.gz
curl -fL --max-filesize 35000000 https://deb.debian.org/debian/pool/main/r/r-base/r-base-core_4.5.0-3_amd64.deb -o r.deb
curl -fL --max-filesize 3000000 'https://deb.debian.org/debian/pool/main/r/r-cran-data.table/r-cran-data.table_1.17.0+dfsg-1_amd64.deb' -o dt.deb
python3 - "$P/INPUTS.json" <<'PY'
import hashlib,json,sys
d=json.load(open(sys.argv[1]))
for p in ("pinned.tar.gz","r.deb","dt.deb"):
    with open(p,"rb") as f: assert hashlib.file_digest(f,"sha256").hexdigest()==d[p]
PY
src=db-benchmark-3b074bc319
tar -xOzf pinned.tar.gz "$src/_data/groupby-datagen.R" > generator.R
for f in duckdb/groupby-duckdb.py datatable/groupby-datatable.R _control/data_small.csv _utils/download_data.sh _helpers/helpers.py; do
  tar -xOzf pinned.tar.gz "$src/$f" > "${f##*/}"
done
dpkg-deb -x r.deb root
dpkg-deb -x dt.deb root
d=$S/root/usr/lib/R
# Keep Debian's packaged config links inside the extracted root.
for f in "$d"/etc/*; do
  if [ -L "$f" ]; then ln -sfn "../../../../etc/R/${f##*/}" "$f"; fi
done
cp -Lf "$d/etc/Renviron.ucf" "$S/root/etc/R/Renviron"
cd generated
OMP_NUM_THREADS=4 R_HOME="$d" LD_LIBRARY_PATH="$d/lib" R_LIBS_SITE="$d/site-library" TMPDIR="$PWD" \
  "$d/bin/exec/R" --vanilla --slave -f ../generator.R --args 1e7 1e2 5 0
# Use upstream DuckDB 1.4.3 wheel from PyPI for this Python/architecture.
# Reuse the pinned E1 wheel target, or use python3 -m pip install --only-binary=:all: --target "$S/duck143" duckdb==1.4.3
cd "$P"
python3 -IB check.py "$S" "${DUCK143_TARGET:-$S/duck143}" | cmp - result.json
```

For join scope only: the unchanged attempted entry point was `_data/join-datagen.R --args 1e7 0 5 0`; the process was killed during LHS output. No join matrix or altered/partial workload is claimed.
