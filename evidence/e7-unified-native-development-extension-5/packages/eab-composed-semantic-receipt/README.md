# Compositional EA&B receipt: mutation intent and join semantics

One small authored manifest implements a common contract across two distinct native boundaries, GeoPackage mutation and pandas join, with a SQLite/Python oracle. The manifest supplies signed-int64 keys, nullable rows, stable identities, explicit KEEP/CLEAR/WRITE intent, protected unchanged fields, right rows (including duplicate keys), and ordinary versus null-safe equality. Both programs consume it. The producer in GDAL's Python emits mutation status and raw SQLite readback keyed by FID. The checker derives the expected row state independently from the manifest, derives exact row-ID join pairs with both Python and SQLite, then runs pandas on actual readback while checking endpoint type materialization.

Results isolate three orthogonal cases:
- Complete update and typed join pass all status, row-state and row-pair checks.
- Sparse update returns errors on existing IDs but happens to give exactly correct states and joins for this fixture. The calls on already-matching keys are intentional: an output-only pass cannot establish successful execution.
- Normalizing all absent payloads to explicit NULL passes mutation status, but turns one KEEP into CLEAR, deleting a true row-ID pair under ordinary equality and adding a false pair under null-safe equality. Separately, with the successful full-write state, default pandas typing fabricates adjacent-large-key matches, even with the right join-null filter.

This is one held-out composition, not an interoperability benchmark result or speed result. It exposes why a useful portable receipt must carry **stage-level correctness**, not only final pair equality, and why operation intent cannot be collapsed into scalar nulls. The decimal JSON interchange here is exactly parsed in Python; a JavaScript-only or external adapter must independently certify int64 decoding or adopt lossless integer encoding. The result is scoped to authored data and captured library versions. Reads after mutation are raw SQLite, not a claim about an Arrow write. The reference does not infer upgrade compatibility or transaction guarantees.

Replay: `/usr/bin/python3 -IB producer.py | python3 -IB check.py | cmp - result.json` (run with shell pipefail).
