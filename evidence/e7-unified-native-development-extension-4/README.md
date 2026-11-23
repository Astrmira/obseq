# E7 selective development replay, extension 4

The manifest pins original archive paths, Git blob IDs, and SHA-256 content hashes. In this extension, 14 additional packages actually ran on the existing native stack: 13 authored development and one scoped external transfer. All matched original output bytes. NEW-REPLAY.tsv names the exact IDs. Workbook cases include real openpyxl production and reopen; the optional LibreOffice consumer variants were not run and get no additional score. The independent-observables package runs the original native producer and native consumer against native.json, not its separate receipt checker.

Together with 25 earlier executions, there are 39 executed exact IDs (36 authored development, three scoped external transfers) and one receipt-only check. PRIOR-REPLAY.tsv carries prior evidence, not reruns in this extension. The original independent 108 are separate. Several external-transfer packages share inputs and are not independent samples. The 117 inventoried paths are still metadata, not an execution denominator.

With shell pipefail, run sha256sum -c SHA256SUMS and then:

    python3 -IB replay.py $(cat NEW-IDS.txt) | cmp - NEW-REPLAY.tsv

Omit IDs to replay the full manifest and compare to REPLAY.tsv, or provide individual IDs. Override dependency interpreters via --default-python and --system-python; --scratch selects a writable directory. Uses original SQLite, GDAL/GEOS, NumPy, openpyxl, pandas and SciPy dependencies; no auto-install. Some GDAL packages require existing pinned GeoPackages at their policy paths; no acquisition or redistribution. All temporary writes go to owned scratch and PROJ networking is disabled.
