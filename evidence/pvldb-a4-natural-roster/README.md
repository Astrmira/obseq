# A4 natural-fault roster and native pandas pilot

`ROSTER.json` reconciles the 29 original release pairs against E9's
coverage audit and archive manifests. It retains family identifiers, source
packet paths and receipt anchors.

The two native pandas families test reversed positional assignment and
nanosecond duration cancellation against exact reference values.
pandas 2.2.3 produces 100 invalid observations out of 276, comprising four
positional-write, 48 Series-sum and 48 DataFrame-sum observations.
pandas 3.1.1 produces zero out of the same 276. Both use NumPy 2.5.5.
All 100 faulty observations pass E2 row count and schema, and all fail
exact ordered equality, bag equality and both E2 tolerance settings.
Counts are observations within two families.

## Five additional natural families

`paired_pandas.py` reuses the pinned E9 native release probes for grouping
snapshot, cached index uniqueness, repeated partial-key assignment,
annual date range boundaries, and as-of string boundaries. The released
2.3.3 and 3.0.0 wheels match the original wheel digests. Both use NumPy
2.3.5. In 19 matched observations, pandas 2.3.3 gives 14 invalid outputs
across all five families and pandas 3.0.0 gives zero. The three pandas
testing configurations reject all 14. Row count, schema and column sums
accept 7, 13 and 12 of the 14, respectively, in these visible projections.

The [common matrix](../pvldb-native-baseline-matrix/README.md#natural-faults)
adds 22 pairs from archived native releases. `legacy_pairs.py` reconstructs
590 observations from the first seven pairs using the pinned old and new
receipts. `E5-LEGACY.json` records all 16 E5 configurations on those observations.
`FAMILY-MATRIX.json` counts a release pair once per method and gives separate
coverage for legal and illegal arms across all 29 pairs.

E2 exact ordered comparison detects faults in 29/29 pairs and rejects a legal
variant in two. Row-count equality detects 4/29 and column sums detect 17/29.
Twelve E5 configurations have determinate faulty arms in all 29 pairs.
DataComPy detects 27/29 and dbt relationships detects 26/29. SQLLogicTest
detects 24/24 with both nosort and rowsort, 22/23 with valuesort, and 22/22
with rowsort hash, among pairs with a determinate faulty arm. The remaining
pairs have NA under the lossless carrier and native hash rules.

Reproduce the pair-level summary with
`python -B aggregate.py . ../pvldb-native-baseline-matrix`.

`CONTRACT-CHECKS.json` records a separate check for each of 968 archived
observations. The check functions score the typed projection before
looking up the historical label. They accept 760 legal arms and reject
208 faulty arms, covering all 29 release pairs on both sides. This is a
replay of authored per-family contracts over the recorded projections.
Several families have a single expected projected state, shared with
the original reference. The rank and coupled representative checks
derive admissible alternatives from the inputs. Reproduce the decisions
with `python -B verify_contracts.py ..`. `TYPED-LEGACY-ARMS.jsonl` contains
the unlabeled synthetic inputs for the first seven families, generated
using the four pinned legacy environments below.

```sh
python -IB build.py .. > ROSTER.json
python -IB pilot.py NEW_SITE old ../pvldb-a2-q39-real-output/run.py ../submission-e-series-native-evidence/e23/check.py
python -IB pilot.py NEW_SITE new ../pvldb-a2-q39-real-output/run.py ../submission-e-series-native-evidence/e23/check.py
python -B paired_pandas.py .. ../pvldb-a3-heldout-value-observers/run.py ../pvldb-a2-q39-real-output/run.py ../submission-e-series-native-evidence/e23/check.py
```

The base environment contains pandas 2.2.3. `NEW_SITE` contains pandas
3.1.1 and NumPy 2.5.5. The old arm takes NumPy from that site and enables
pandas 2.2.3 copy-on-write, matching the original positional replay.

For the five additional pairs, invoke the third command once under
pandas 2.3.3 and once under pandas 3.0.0, both with NumPy 2.3.5.

To reproduce the full legacy E5 coverage, export one array per arm with
`legacy_pairs.py . ARM` under those same four environments. For the first
two pass `--new-site NEW_SITE`. Concatenate the four arrays and use the
common matrix's five E5 commands to produce `E5-LEGACY.json`. For the
SQLLogicTest command, use the pinned `slt-frozen.py` as `slt.py` in a copy
of the matrix program directory.
