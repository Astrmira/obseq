# E7 selective native replay, extension 5

This extension adds original native producer/consumer paths for GeoPackage, Parquet VARIANT, DuckDB and Arrow, SQLite FTS, pandas, NetCDF, and projected geometry. MANIFEST.json pins every admitted path to an original archive Git blob and SHA-256. NEW-REPLAY.tsv records the actual new replay results. PRIOR-REPLAY.tsv preserves the immediately preceding evidence without implying it was rerun. The original independent 108 are outside the selector, and the single orientation receipt-only case remains separate.

Run with the shell's pipefail option:

    sha256sum -c SHA256SUMS
    python3 -IB replay.py --inputs /path/to/input-map.json $(cat NEW-IDS.txt) | cmp - NEW-REPLAY.tsv

The delta contains only the 15 new packages. To replay the full manifest, omit case IDs and pass `--prior-root` pointing to an unpacked copy of the prior published `e7-unified-native-development-extension-4` directory (commit 531f661393fbdbaeb5b91caac3ff0d9857689fb8). Every loaded package is hash checked regardless of which root supplied it. For a new environment, copy the role keys in INPUT-ROLES.example.json to an actual input map with version-matched dependencies and content-matched source files. The selector accepts --default-python, --system-python and --scratch. Missing role/path returns NA, not a successful check. Prior policies with absolute source paths and the schema-presence package's hard-coded DuckDB/Arrow paths remain legacy prerequisites; source is unmodified. No automatic installation, source downloads or large local copies.

A shared read-only artifact can support multiple scoped observations. Do not interpret a count of package IDs as a count of independent datasets or the 117 inventoried historical paths as an executed denominator.

All 15 additional package IDs executed and matched the exact archived receipts (three authored native development and 12 scoped external-transfer/control routes). With the prior 39 actual executions, this gives 54 actual executions (39 authored development and 15 external-transfer/control). The other case is receipt-only. Two geometric routes classified in the transfer/control cohort include minimal authored geometry to test external-engine behavior, not evidence of authentic-data prevalence.
