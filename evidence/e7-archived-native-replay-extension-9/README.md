# E7 archived native replay extension 9 (add-only)

Eight previously uncounted archive packages freshly ran and matched their archived receipts byte-for-byte. Two are authored native controls; six are scoped external transfers. The two reserves from extension 8 were actually rerun, not counted from old reports. Cumulative: 94 actual packages (57 authored and 37 transfer), plus one prior receipt-only row. The independent 108 are separate. The Q11 variants are distinct archived executable gates but share SF10 and an overlapping source arm; they are not independent samples. No downloads, generators, macros or Calc retries.

The DuckDB Python SQLLogicTest entrypoint writes a generated SCORES.csv, which also matches the archived bytes. The original dbt source freshness workflow ran stock, with telemetry off; its deterministic summarized decisions match, not wall-clock cache timestamps. It tests source freshness, distinct from the previous dbt unit and relationship tests. Stock CWI Q39 uses a different archived result contract from the previous NULL-attribution study. See SCOPE.tsv for exact restrictions and unadmitted candidates.

The manifest pins original archive paths, Git blobs, and SHA-256 digests. BASE-PINS verifies the exact published baseline extension 8 and all earlier roots. Existing local prereqs are referenced by INPUT-ROLES.example.json; supply equivalent absolute paths when relocating. The selector uses private scratch copies for packages that write next to scripts, and symlinks existing dependencies/read-only input databases into that scratch. It does not download or generate underlying workloads. The two optional prior-source locator variables from extension 8 may reference the same original TweetID input partition hashes; packaged files do not include raw TweetIDs. No new fixture authoring.

    set -o pipefail
    sha256sum -c SHA256SUMS
    python3 -IB replay.py --inputs INPUT-ROLES.example.json | cmp - NEW-REPLAY.tsv

Specify case IDs for selective replay. For all prior and new cases, add --include-prior with repeated --prior-root for the unpacked pinned original release plus extensions 4, 5, 6, 7, 8. Prior receipts are not rerun by the default invocation.
