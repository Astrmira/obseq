# A3 coherent-representative held-out pilot

24 sealed cases come from the E7 later-138 coherent grouped representative
panel. For each source group, the replay derives a conventional reference
by choosing the lexicographically first visible row among minimum-score
rows, with NULL first, and emitting groups in key order. Source-only
references are constructed before candidate rows are scored or sealed
labels are loaded. The visible fields are `g,s,d,p,t`, and the row identity
used for sealed labels remains available only in the upstream typed evidence.

Ordered equality rejected 2/10 legal cases and accepted 2/14 invalid cases.
Bag equality rejected 2/10 and accepted 3/14. E2 byte hash and SQLite
integrity are NA on the in-memory table carrier. All counts are for this
one panel. Scoring the remaining panels and the E5/native-tool comparison
remain open.

```sh
python -IB run.py ../e7-independent-native-suite/later-138/panels/heldout-coherent-group-representatives ../pvldb-a2-q39-real-output/run.py ../submission-e-series-native-evidence/e23/check.py
```
