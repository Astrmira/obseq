#!/usr/bin/env bash
set -euo pipefail
cpu=$(python3 -c 'import os; print(max(os.sched_getaffinity(0)))')
printf '%s\n' "pinned_cpu=$cpu" 'workers=5; scenarios=0.1%,1%,10%; no system cache drop; shared remote host' > ENV.txt
c++ --version >> ENV.txt
uname -srv >> ENV.txt
lscpu | grep -E 'Model name|^CPU\(s\)' >> ENV.txt
sha256sum geometry_pressure.cpp run.cpp run-pressure.sh > PREEXECUTION.sha256
c++ -std=c++20 -O3 -fno-fast-math -ffp-contract=off geometry_pressure.cpp -o pressure
printf '%s\n' 'repeat,mode,per_mille,n,ns,rss_kib,fallbacks,mismatches,negative,zero,positive' > RAW.csv
for r in 0 1 2 3 4; do
  for f in 1 10 100; do
    for offset in 0 1 2; do
      taskset -c "$cpu" ./pressure "$r" "$(((r+offset)%3))" "$f" 100000000 >> RAW.csv
    done
  done
done
