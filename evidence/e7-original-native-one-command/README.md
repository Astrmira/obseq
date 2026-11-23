# Original E7 native one-command re-execution (not a receipt-only audit)

Replays the original independent 108 frozen cases, through the exact previous native drivers (F1–F10 and each O3/O4 subtype). Bundle ships the small pinned preexisting case corpus, original runner files, plans/locks, existing expected comparisons and ledger; no native runtimes, executables, external datasets, or new fixtures are embedded. A fresh private scratch copy is used each run: legacy drivers may write their CSVs; two standalone PostgreSQL adapters make disposable clusters; no published source/receipt is modified. It does not rerun the separate 138 later independent cases or 100 established development/transfer replay packages.

Configure runtime locations by copying ENV.example.json, which documents the required two isolated Python dependency levels (DuckDB 1.4.3 / legacy PyArrow 22, Polars 1.35.2 and DataFusion 50.1.0; current PyArrow 26.0.1 / Polars 2.1.0 for F8), installed SQLite 3.53.1, Python with native GDAL (3.10.3) and GEOS (3.13.1), a trusted checksum-pinned DuckDB 1.4.3 spatial extension, and native PostgreSQL 17.12. F8 assumes the previously fingerprinted host TZ data. Use Python 3.11 or later with the matching dependency ABI; run as a non-root account because the local PostgreSQL cluster cannot initialize as root. The example paths are placeholders. A config can point to any local layout, and no installer/download is invoked.

From this directory:
    set -e -o pipefail
    sha256sum -c SHA256SUMS
    sha256sum -c BUNDLE.sha256
    python -B replay.py ENV.json | cmp - RESULT.json

Only three explicit legacy path literals are relocated in scratch (F6/F9 dependency sites and O4 point-set BLIND input path); byte-pinned native code is checked before each relocation and no query or predicate changes. Preexisting relative dependency expectations are restored using scratch symlinks. The archived receipts are never accepted in place of execution: WKB starts from a fresh native decode before scoring; F8 similarly passes fresh native bytes to its independent scorer. All other stages use exact byte comparisons except two O3 paths, where original engine versions and full per-case/engine/arm statuses are compared, not a particular permitted tie selection. O3 errors and invalid arms remain in the compared projection. Launcher checks every original ID was observed by an applicable native stage and that its stage evidence matches the established ledger. F8 supplied-policy primitives below a named-timezone interface and WKB strict decode rejection are properly scoped. No claim that all available engines can execute every case.

This is local, bounded native re-execution; a bundled environment/container, one command that merges every cohort, public distribution, and an archival DOI remain separate work. Replaying fixtures adds no new independent evidence.
