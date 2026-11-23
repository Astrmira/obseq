# E7 replay and coverage reconciliation

One command reruns three distinct cohorts: the original independently authored interpreter holdout (108 fixtures, six in each of F1–F10 and eight O3/O4 subtypes); six later independently authored native panels (138 fixtures, 282 paired case/adapter channels); and the compact development/transfer corpus (no independent blind credit). It also reruns native WKB on six fixtures already inside the original 108. Do not count those six twice. The command accepts pinned scored-only sources; no new labels were opened.

The original ≥5 criterion is met for authored and interpreter-scored cases, not uniform native coverage. Separately published original native receipts cover all original F1/F2 across four engines, F3/F4 across SQLite and DuckDB, all O3 cases across SQLite/DuckDB/DataFusion SQL and a separate Polars eager path (retain the reported SQLContext errors/invalid results), and original equivalent-WKB across GDAL/GEOS. These earlier sources are not rerun by this command except WKB. See original sibling directories e7-native, e7-native-f34, e7-native-o3 and e7-native-o4-wkb under submission-native-oracle-crosschecks. Do not credit a newer panel as re-running the original fixture, or equate wire-equivalence WKB with GEOS union-order/point-set coverage. E2 still needs broad cross-engine/format variant coverage across O3/O4; the separate XLSX date witness is not sufficient. The approximately 100 development packages are not yet integrated, and no DOI or archived deposit is claimed.

Replay with pinned native SQLite, DuckDB, PostgreSQL, GEOS, GDAL, openpyxl and pandas plus dependencies documented by each adapter. Pass the parent directory of the newer six panels, PostgreSQL bin, the compact corpus directory, the original native WKB directory (with e7-scored beside it), and the published e7-holdout/cases.json.

    set -e -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B check.py SIX_ROOT PG_BIN COMPACT WKB OLD_CASES | cmp - RESULT.json
