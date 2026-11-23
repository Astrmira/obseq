#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
sha256sum -c "${INPUT_MANIFEST:-RERUN-INPUT.sha256}"
sha256sum ../o5_cost.py archived-o5.py run-cost.sh > RERUN-PREEXECUTION.sha256
sizes=(3 1000 100000)
for rep in 0 1 2 3 4; do
    for offset in 0 1 2; do
        size=${sizes[$(((rep+offset)%3))]}
        python3 -B ../o5_cost.py native-100m-hive archived-o5.py "$size" "$rep" >> RERUN-COST-RAW.jsonl
    done
done
