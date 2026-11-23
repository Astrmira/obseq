# E7 native replay extension 6 (add-only)

11 additional historic packages executed on 52f36f77455cc536875dfd4c09dee6388b3e2e55: eight authored native packages and three scoped external transfers. All 11 matched archived outputs byte-for-byte. No prior case or independent holdout was replayed in this tranche. Cumulative recorded executions: 65 (47 authored, 18 transfer/control), with one separately counted prior receipt-only check. A workbook LibreOffice case exited 137 and is not counted; see BLOCKED.tsv. No workbook macros were executed or counted. Successful authored workbook cases cover openpyxl writing/reopening and XML evidence; they are not LibreOffice or Excel formula evaluations. The actual dbt unit and relationship tests executed in isolation with telemetry disabled.

The delta ships only the new original test packages; each file is pinned to the original archive Git blob and local SHA-256. BASE-MANIFEST.json and PRIOR-REPLAY.tsv reproduce published extension-5 metadata at the pinned commit, not newly executed observations. Source-fixed folder roles require local installations; no files or runtimes are downloaded by the selector.

    set -o pipefail
    sha256sum -c SHA256SUMS
    python3 -IB replay.py --inputs INPUT-ROLES.example.json | cmp - NEW-REPLAY.tsv

Replace the paths in INPUT-ROLES.example.json locally with matching sources and pinned dependency sites. Provide IDs to run a subset. To replay all prior and current rows in one command, add --include-prior and repeat --prior-root for the unpacked published replay, extension-4, and extension-5 directories pinned in BASE-PINS.json. The selector validates prior manifest hashes and every loaded file; missing original files are not accepted. Use --scratch on a writable volume to isolate runtime outputs. Some previous original entrypoints embed fixture paths as documented in their own PREREADME/README; no transparent patching is done.
