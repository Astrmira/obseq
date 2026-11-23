#!/usr/bin/env bash
set -euo pipefail

root=/opt/obseq
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
fetch() {
    local url=$1 digest=$2 output=$3 alternate=${4:-}
    if [[ -z ${OBSEQ_SOURCE_MIRROR:-} ]] || ! curl --fail --silent --location \
        "${OBSEQ_SOURCE_MIRROR%/}/$digest" -o "$output"; then
        printf 'Downloading %s\n' "$url"
        curl --fail --silent --show-error --location --retry 3 "$url" -o "$output" || {
            [[ -n $alternate ]] || return
            printf 'Downloading %s\n' "$alternate"
            curl --fail --silent --show-error --location --retry 3 "$alternate" -o "$output" || return
        }
    fi
    printf '%s  %s\n' "$digest" "$output" | sha256sum --check -
}
unpack() {
    mkdir -p "$2"
    tar -xf "$1" -C "$2" --strip-components=1
}

mkdir -p "$root/tools" "$root/deequ" "$root/slt"
python3.12 -m venv "$root/venv"
python -m pip install --no-cache-dir --require-hashes -r requirements.lock
python -m pip install --no-cache-dir --no-build-isolation --no-deps -e .
python -m pip install --no-cache-dir --require-hashes --no-deps -r docker/requirements-default.lock
python -m pip install --no-cache-dir --require-hashes --no-deps --target "$root/e4-site" \
    -r docker/requirements-e4.lock
python -m pip install --no-cache-dir --require-hashes --no-deps --target "$root/e1-more" \
    -r docker/requirements-e1-more.lock
python -m pip install --no-cache-dir --require-hashes --no-deps --target "$root/duck142" \
    -r docker/requirements-duck142.lock
python -m pip install --no-cache-dir --require-hashes --no-deps --target "$root/arrow19" \
    -r docker/requirements-arrow19.lock
python - <<'PY'
from importlib.metadata import distribution
from pathlib import Path

site = Path("/opt/obseq/duck143")
site.mkdir()
wheel = distribution("duckdb")
for name in sorted({file.parts[0] for file in wheel.files} - {".."}):
    (site / name).symlink_to(wheel.locate_file(name))
PY

fetch https://conda.anaconda.org/conda-forge/linux-64/micromamba-2.3.3-0.tar.bz2 \
    e7274528ceb9c20d048a428d6c22d7e02e268f8ffb762c4c365422347c8b8ba2 "$work/mamba.tar.bz2"
tar -xf "$work/mamba.tar.bz2" -C "$work" bin/micromamba
MAMBA_ROOT_PREFIX="$work/mamba" "$work/bin/micromamba" create --yes \
    --prefix "$root/gdal" --file docker/gdal-linux-64.lock

fetch https://www.sqlite.org/2026/sqlite-autoconf-3530100.tar.gz \
    83e6b2020a034e9a7ad4a72feea59e1ad52f162e09cbd26735a3ffb98359fc4f "$work/sqlite.tgz"
unpack "$work/sqlite.tgz" "$work/sqlite"
( cd "$work/sqlite"; ./configure --prefix="$root/sqlite" --disable-static --disable-readline
  make -j"$(nproc)"; make install )

fetch https://ftp.postgresql.org/pub/source/v17.12/postgresql-17.12.tar.bz2 \
    9cf136a703d8ee2f83465c43be4e9e8e7930c82b0bfba13be7e2537be769ac55 "$work/pg.tar.bz2"
unpack "$work/pg.tar.bz2" "$work/pgsql"
( cd "$work/pgsql"; ./configure --prefix="$root/pgsql" --without-readline
  make -j"$(nproc)"; make install )

fetch https://downloadarchive.documentfoundation.org/libreoffice/old/7.3.7.2/deb/x86_64/LibreOffice_7.3.7.2_Linux_x86-64_deb.tar.gz \
    2c14b90744a9c2c320cca7863ae027e20ee14b9681e739ff8c2192c3672d9d80 "$work/calc.tgz"
unpack "$work/calc.tgz" "$work/calc"
for deb in "$work"/calc/DEBS/*.deb; do dpkg-deb -x "$deb" /; done
cat > "$root/tools/soffice" <<'SH'
#!/bin/sh
program=/opt/libreoffice7.3/program
export LD_LIBRARY_PATH="$program${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$program/soffice" "$@"
SH
chmod 755 "$root/tools/soffice"
ln -s soffice "$root/tools/libreoffice"

fetch https://codeload.github.com/gregrahn/sqllogictest/tar.gz/c93ac416f05635ff5cc490009add936d9753d01d \
    0b02c1f4ab85a6c3fc69ace07bb05d24a2b256b99503f78700b2832fb1296b80 "$work/c-slt.tgz"
unpack "$work/c-slt.tgz" "$work/c-slt"
make -C "$work/c-slt/src" CC="gcc -g -Wall -DSQLITE_NO_SYNC=1 -DOMIT_ODBC=1" sqllogictest
install "$work/c-slt/src/sqllogictest" "$root/tools/sqllogictest"

fetch https://codeload.github.com/duckdb/duckdb-sqllogictest-python/tar.gz/66b0687fd7b21d22eb8c2216c5e26030dc6a3286 \
    61358f00600c1c49821e0ffc937b019cb42c187a7fc1dfa7fddbd1b3415840f6 "$root/slt/upstream.tar.gz"
unpack "$root/slt/upstream.tar.gz" "$root/slt/upstream"
cp evidence/submission-native-oracle-crosschecks/e5-slt/{UPSTREAM-FILES.sha256,TERM-COLOR.lock.json} "$root/slt/"
python - <<'PY' > "$root/slt/DUCKDB-SO.sha256"
import hashlib
import _duckdb
with open(_duckdb.__file__, "rb") as source:
    print(hashlib.file_digest(source, "sha256").hexdigest())
PY
( cd "$root/slt"; sha256sum -c "$root/evidence/e7-archived-native-replay-extension-9/packages/slt-native-port-framing-scope/NATIVE-INPUT.lock" )

fetch https://raw.githubusercontent.com/cwida/tpcds-result-reproduction/61ba82e7f6868760dcfbfa4347fe06cfd67a798f/roundingdiff.py \
    65171e4a8a54b5330fba5c97c4d705f34410c62748d9180cb2e161b628a7540f "$root/tools/roundingdiff.py"
fetch https://raw.githubusercontent.com/qgis/QGIS/939da08506f5cc61f93ff2ce979a2c84008a3f07/resources/data/world_map.gpkg \
    386bc75f4ac46c329cdc44caff01e2e27385d3d89ca3ded26495090def11f669 "$root/tools/world_map.gpkg"

spark_url=$(python - <<'PY'
import json, urllib.request
with urllib.request.urlopen("https://pypi.org/pypi/pyspark/4.0.1/json") as response:
    print(next(a["url"] for a in json.load(response)["urls"] if a["filename"] == "pyspark-4.0.1.tar.gz"))
PY
)
fetch "$spark_url" 9d1f22d994f60369228397e3479003ffe2dd736ba79165003246ff7bd48e2c73 "$work/pyspark.tgz"
tar -xzf "$work/pyspark.tgz" -C "$root/deequ" --wildcards \
    'pyspark-4.0.1/deps/bin/*' 'pyspark-4.0.1/deps/jars/*'
deequ_path=com/amazon/deequ/deequ/2.0.15-spark-4.0/deequ-2.0.15-spark-4.0.jar
# Use the Maven Central cache first because shared CI runners can hit Maven Central's rate limit.
fetch "https://maven-central.storage-download.googleapis.com/maven2/$deequ_path" \
    cc51910a73b8de05f07353e48a167baa35232c46a9f7861a4e6fc290501703f2 "$root/deequ/deequ.jar" \
    "https://repo.maven.apache.org/maven2/$deequ_path"
