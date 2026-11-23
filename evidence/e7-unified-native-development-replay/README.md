# E7 unified development replay

The manifest pins the research branch commit, source directories, SHA-1 Git blobs, and SHA-256 file digests. It covers 26 exact original package IDs: 23 authored native development executions, two native external-transfer executions (same public fixture corpus, separate scopes), and one archived receipt check. All 25 native executions actually ran in this replay, including 15 beyond the previous two pilots. Every completed check matched its frozen receipt byte for byte. The original independent 108 holdouts are not counted here; the compact package includes three separate authored transfer controls, not blind holdout credit. The orientation 100-million data path was not executed in this work.

    set -o pipefail
    sha256sum -c SHA256SUMS
    python3 -IB replay.py | cmp - REPLAY.tsv

Selective replay (case IDs are positional arguments):

    python3 -IB replay.py eab-native-collation-equivalence eab-sql-allowed-result-families

Override system GDAL Python with --system-python and the general interpreter with --default-python. Optionally pass --scratch to an existing directory for temporary native databases. Uses existing native runtimes only (GDAL/GEOS with NumPy in system Python, and SQLite, openpyxl, pandas and SciPy in general Python); no automatic installation. The admission/CRS/containment packages still need the original GeoPackage bytes at the explicit paths in their policies. Those source artifacts are not distributed by this package. Runtime/version or input differences are not silently normalized. No network downloads, expected-output regeneration, archive-level independence claim, or new fixture count. The broader inventory of 117 prior paths with entrypoint/receipt is metadata only, not a runnable denominator.

The individual case source READMEs retain the original experiment scopes and denominators.
