#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export R_HOME="${R_HOME:-$(R RHOME)}"
export OBSEQ_R_LAUNCHER="${OBSEQ_R_LAUNCHER:-$R_HOME/bin/exec/R}"
root=$(pwd)
mkdir columns
"$OBSEQ_R_LAUNCHER" --vanilla --slave -f generate-columns.R --args 1e8 100 250000 "$root/columns" "$root/unused"
python3 -B layout.py 100000000 "$root/columns" "$root/native-100m-hive" > RERUN-LAYOUT.json
python3 - <<'CHECK'
from pathlib import Path
import hashlib
import json
archived, rebuilt = (json.loads(Path(name).read_bytes()) for name in ('LAYOUT-100M.json', 'RERUN-LAYOUT.json'))
for name in ('csv_sha256', 'total', 'buckets', 'arrow'):
    if archived[name] != rebuilt[name]:
        raise ValueError('Rebuilt content differs for ' + name)
files = sorted(Path('native-100m-hive').glob('id1=*/*.parquet'))
if len(files) != 100:
    raise ValueError('Expected all 100 Hive partitions')
Path('RERUN-INPUT.sha256').write_text(''.join(
    f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.as_posix()}\n' for path in files), encoding='utf-8')
CHECK
