# A2 real-output pilot on TPC-DS Q39

This remote scoring pass used the five frozen exact-source receipts in
`tpcds-sf10-q39-exact-threshold`.
They contain 2,433 paired keys, 458 with a different native float result
between the 1-thread and 4-thread arms. Each exact-source-certified
native output is evaluated against the other. Two authored invalid
controls change an exact key by one and double one approximate value.

E2 exact ordered, bag, set, byte hash and column sum reject both legal
directions. Both tested E2 relative tolerances accept both legal directions
and detect both invalid controls. Stock CWI accepts both legal directions
and the key mutation. Count and E2 schema accept all four. The four
observations are from one query and share their source outputs.
Byte hashes cover the experimental TSV serialization.

The pinned CWI script sets `delta = 0.05` at line 11, converts integer columns
to floats at line 22 and tests `abs(first - second) > 0.05 * abs(first)` for
numeric cells at line 58. M1 changes item key 1265 to 1266, a relative
change of `1/1265 ≈ 7.9e-4` against the original file. Table 4 reports the stock
5% rule separately from the generic `1e-5` and `1e-9` relative tolerances.

The [full ClickBench A7 packet](../pvldb-a7-typed-candidates/README.md)
adds a distinct Q18/Q25 real-output pilot, scored with the same E2
observers against independently scanned exact source groups and peers.

```sh
python -IB run.py ../tpcds-sf10-q39-exact-threshold SF10_SHA_JSON STOCK_CWI ../submission-e-series-native-evidence/e23/check.py OUTPUT
```

`SF10_SHA_JSON` maps the five `q39-raw-part-*.jsonl` basenames to hashes
from the original packet. Use pandas 2.2.3 and the [pinned CWI script](https://github.com/cwida/tpcds-result-reproduction/blob/61ba82e7f6868760dcfbfa4347fe06cfd67a798f/roundingdiff.py).
