#!/bin/sh
set -eu
s=${1:?extracted H2O prerequisites}
d=$s/root/usr/lib/R
export R_HOME=$d LD_LIBRARY_PATH=$d/lib R_LIBS_SITE=$d/site-library
export TMPDIR=${CHECK_TMPDIR:-$s}
script='library(data.table); setDTthreads(0L); cat(R.version.string,"; data.table=",as.character(packageVersion("data.table")),"; requested threads=",as.character(getDTthreads()),"\n",sep=""); getDTthreads(verbose=TRUE)'
printf '%s\n' 'OMP_NUM_THREADS=1 without affinity or OMP_THREAD_LIMIT'
env -u OMP_THREAD_LIMIT OMP_NUM_THREADS=1 "$d/bin/exec/R" --vanilla --slave -e "$script"
printf '%s\n' 'OMP_THREAD_LIMIT=1 without affinity'
OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 "$d/bin/exec/R" --vanilla --slave -e "$script"
printf '%s\n' 'OMP_THREAD_LIMIT=1 and single affinity'
cpu=$(python3 -c 'import os; print(min(os.sched_getaffinity(0)))')
OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 taskset -c "$cpu" "$d/bin/exec/R" --vanilla --slave -e "$script"
