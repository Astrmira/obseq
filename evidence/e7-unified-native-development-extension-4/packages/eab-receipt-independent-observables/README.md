# Three independently necessary observables for a patch–join conformance receipt

R98's successful and negative native pipeline arms now emit a machine-readable receipt under contract.json. The input manifest, output receipt and comparison protocol use decimal strings for signed int64 keys and IDs (JSON null is reserved for missing scalar data). The checker validates exact keyed records independently for patch status, persisted rows and output pairs by join predicate. It rejects duplicate status IDs, manifest mismatch and unexpected engine versions; missing, extra and changed records are reported separately. The SHA-256 header binds the expected contract/manifest version to the emitted receipt, not the truthfulness of the process; there is no attestation. Versions are checked against a separately checked-in versions.json. Status intentionally distinguishes only success from error, not detailed diagnosis.

**Independence by collisions.** Relative to the complete/typed passing receipt, the native sparse/typed arm differs only at patch status. Default dtype after the complete write differs only at final pair IDs. An explicitly injected protocol control changes an unrelated stored field at one FID, leaving status and all pairs identical. The latter is not a native failure assertion. In this contract each omitted observable thus creates a pair of receipts with identical remaining evidence but opposite correctness. The native normalize-all/typed arm shows a combined state + pair defect. These witnesses prove necessity of the three semantic observations for this test contract, not byte-minimal serialization or correctness of arbitrary workloads.

From this directory:
```sh
set -o pipefail
/usr/bin/python3 -IB native_producer.py | python3 -IB native_consumer.py | cmp - native.json
python3 -IB check.py | cmp - result.json
```
Oracle: explicit patch interpreter and Python exact pair matching, with independent SQLite truth comparison during native regeneration. Native path: actual GDAL GeoPackage updates, closed-database SQLite readback, pandas materialization and merge. The validator by itself needs only Python's standard library. Snapshot replay checks engine versions, not binary hashes. No timing, concurrency, security or cross-version compatibility claim.
