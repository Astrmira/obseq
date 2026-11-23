#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p inputs/ne inputs/osm
curl -fLsS --retry 2 https://naturalearth.s3.amazonaws.com/110m_cultural/ne_110m_admin_0_countries.zip -o ne.zip
curl -fLsS --retry 2 https://download.geofabrik.de/europe/liechtenstein-261120-free.gpkg.zip -o osm.zip
python3 - <<'EXTRACT'
from pathlib import Path
from zipfile import ZipFile
with ZipFile('ne.zip') as source:
    for suffix in ('shp', 'shx', 'dbf'):
        name = 'ne_110m_admin_0_countries.' + suffix
        (Path('inputs/ne') / name).write_bytes(source.read(name))
with ZipFile('osm.zip') as source:
    name, = [name for name in source.namelist() if name.endswith('.gpkg')]
    Path('inputs/osm/liechtenstein.gpkg').write_bytes(source.read(name))
EXTRACT
"${GDAL_PYTHON:-python3}" -B prep.py inputs wedges.bin > SEED-RESULT.json
python3 -B check.py wedges.bin labels.bin > ARCHIVE-CHECK.json
c++ -std=c++20 -O3 -fno-fast-math -ffp-contract=off geometry_native_float.cpp -o geometry-native
cpu=$(python3 -c 'import os; print(max(os.sched_getaffinity(0)))')
sha256sum geometry_native_float.cpp run.cpp prep.py check.py wedges.bin labels.bin run-native.sh > RERUN-PREEXECUTION.sha256
printf '%s\n' 'rep,mode,n,ns,rss_kib,negative,zero,positive,fallback,mismatches,producer_token' > RERUN-RAW.csv
for rep in 0 1 2 3 4; do
    for offset in 0 1 2 3; do
        taskset -c "$cpu" ./geometry-native wedges.bin labels.bin "$(((rep+offset)%4))" "$rep" >> RERUN-RAW.csv
    done
done
