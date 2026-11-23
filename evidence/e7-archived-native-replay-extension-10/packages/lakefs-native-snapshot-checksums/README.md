# E5: stock lakeFS file identity and scope

Stock upstream lakeFS/lakectl 1.86.0 from [official release assets](https://github.com/treeverse/lakeFS/releases/expanded_assets/v1.86.0), Linux x86_64 tarball 60.7 MB, SHA-256 dc02b075ddcbb0984f96f6be2e0e08d74bd0967920ec89dd00a97b5d400ad8eb. Verified archive LICENSE: Apache-2.0. No artifact/binaries distributed here. No external endpoint or account used: local data and metadata, HTTP bound to loopback, disposable credentials, actions/telemetry/version checks disabled. Server exits before its private scratch is removed.

CASES.json selects the six existing scored E3 F3 and F7 pairs. F7 feeds the original source/candidate rows as CSV and checks the equal-sum fact before evaluating. F3 reconstructs a fresh SQLite main/WAL pair with the original stale and committed row values and verifies both native SQLite reads; only main bytes are uploaded for the two snapshots. A separate ordered-versus-reversed CSV panel is one authored legal control, not from the E2 panel. A native lakeFS upload followed by stat supplies each checksum; readback before and after committing independently verifies the bytes (except the separately staged legal control, which is read before commit).

| Configuration | E3 false admits | Additional legal false rejects |
|---|---:|---:|
| Native lakeFS object checksum comparison |3/6|1/1|

F7's 3 same-sum value mutations were distinguished by lakeFS. F3's 3 committed mutations were invisible when the snapshot manifest included the SQLite main object only. This is scoped to the chosen upload manifest, not a flaw in lakeFS checksum integrity or a claim that consistent SQLite backups lose commits. Comparing exact byte identity is stricter than order-free logical equality; the legal reversal exposes that restriction. No independent replication count or production rates claimed.

```sh
sha256sum -c SHA256SUMS
python -B run.py "$UPSTREAM_BIN_DIR" "$WRITABLE_SCRATCH" | cmp - RESULT.json
```
