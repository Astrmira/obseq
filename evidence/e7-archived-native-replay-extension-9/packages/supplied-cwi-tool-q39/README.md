# E1: direct stock CWI comparator on the frozen Q39 evidence

This extends the source-semantics comparison in the E-series evidence package. We recovered and executed [CWI's existing roundingdiff.py](https://github.com/cwida/tpcds-result-reproduction/blob/61ba82e7f6868760dcfbfa4347fe06cfd67a798f/roundingdiff.py) unchanged, not a local imitation. It accepts the two legitimate DuckDB Q39 reductions in both comparison directions. It also accepts the authored coherent +1 mutation in an exact item key. On the same shape it correctly rejects a doubled approximate value, a negative control verifying that the executable is not merely accepting everything. The column-aware comparison agrees on the good and large-numeric cases and finds the key mutation. Stock stdout indicates match with exit status 1 in this file mode; tests explicitly verify that convention. This is one contrast on an actual query result with authored counterfactuals, not an official TPC qualification or a prevalence claim. The earlier independent exact-source check bounds each original numeric result to 2 ULP; the paired 3 ULP check accounts for variation between those two measured results.

To replay, use the upstream file at the commit linked above and the immutable evidence packet's e1/q39-retry-reference.json file. The checker verifies both SHA-256 before execution; the source file is not redistributed. Use pandas 2.2.3.

    python3 -IB check.py PATH_TO_UPSTREAM_SCRIPT PATH_TO_Q39_REFERENCE | cmp - result.json
    python3 -IB check.py PATH_TO_UPSTREAM_SCRIPT PATH_TO_Q39_REFERENCE --csv | cmp - cases.csv
    sha256sum -c SHA256SUMS
