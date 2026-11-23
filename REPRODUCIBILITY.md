# ObsEq Reproducibility Guide

This document describes the three verification tiers provided in **ObsEq**, their software and hardware requirements, and how external datasets are acquired and verified.

---

## Overview of Verification Tiers

| Tier | Entrypoint | Internet / External Data | Typical Runtime | What It Verifies |
| --- | --- | --- | --- | --- |
| **Tier 1: Offline Digest & Receipt Verification** | `python -B replay.py` | None (stdlib Python 3.11+ only) | `< 2 min` on a laptop | Verifies all `SHA256SUMS` and `NUMBERS.json` source hashes; re-runs the independent `C2` contract interpreter (108 cases); recounts the `C2` (138 cases), `C3` (benchmark), and `C4` (29 natural bug pairs) verdict matrices and `A5` contract census. |
| **Tier 2: Pinned Comparator & SQL Validator Replay** | `python -B replay.py --comparators` | Pinned Python wheels (`requirements.lock`) | `< 10 min` on a laptop | Re-executes native comparator adapters across the `C2` and `C4` cohorts under bundled IANA `tzdata` 2025b (`zoneinfo/`) and runs the `ObsEq` tie-aware SQL window validator smoke suite. |
| **Tier 3: Containerized Full Native Producer Replay** | Docker (`docker/`) + `fetch_clickbench.py` / `build_tpc.py` | Public dataset downloads (pinned by SHA-256) | Workload-dependent (`16+ GiB` RAM for 100M-row runs) | Re-runs native multi-engine data producers (`DuckDB`, `PostgreSQL`, `SQLite`, `DataFusion`, `Polars`, `pandas`, `PyArrow`, `GDAL/GEOS`, `Spark/Deequ`, `dbt`, `GX`, `DVC`, `SQLLogicTest`, `LibreOffice Calc`). |

---

## Tier 1: Zero-Download Offline Verification

Requires only **Python 3.11 or newer** (standard library only):

```sh
python -B replay.py
```

Expected behavior:
- Checks every tracked receipt against `SHA256SUMS` and `NUMBERS.json`.
- Re-executes the sealed contract adjudication for `C2` (`original_contracts_replayed: 108`), recounts `later_cases_recounted: 138`, `natural_release_pairs_recounted: 29`, `benchmark_comparisons_recounted: 44`, and `development_contracts_recounted: 58`.
- Prints a deterministic JSON summary and exits with status `0`.

---

## Tier 2: Pinned Comparator Matrices & SQL Window Validator

Install the hash-locked Python environment and run `--comparators`:

```sh
python -m venv .venv
. .venv/bin/activate   # On Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-build-isolation --no-deps -e .
python -B replay.py --comparators
```

This also installs the standalone `obseq-verify-windows` CLI (`verify_windows.call` in Python), which derives complete sort keys and eligible projected rows directly from SQL (`sqlglot` + `DuckDB` type binding) to decide exact `ORDER BY ... LIMIT ... OFFSET` legality without manual annotations.

---

## Tier 3: Full Native Producer Replay & Large-Scale Datasets

### 1. Containerized Native Environment
Native producers span multiple C/JVM/CLI runtimes (`GDAL 3.10` / `GEOS 3.13–3.15` / `PROJ 9.6`, `Apache Spark` + `Deequ 2.0.15`, `LibreOffice Calc`, `C SQLLogicTest`, and multi-version engine wheels). Build and run the locked Linux image in [`docker/`](docker/README.md) so that system libraries and resource paths (`GDAL_DATA`, `PROJ_DATA`) match the recorded environment.

### 2. Acquiring Public Benchmark Datasets
Large public datasets are not stored in Git; helper scripts fetch and verify every partition by SHA-256:

- **ClickBench (`hits`, 100 partitions, 99,997,497 rows, ~14.7 GB)**:
  ```sh
  python -B fetch_clickbench.py /path/to/clickbench_hits
  ```
  Pass `--verify-only` to check an existing local directory against the pinned partition hashes in `evidence/pvldb-a7-typed-candidates/FULL-ACQUISITION.json`.

- **TPC-H & TPC-DS (`SF1` and `SF10`)**:
  ```sh
  python -B build_tpc.py --help
  ```
  Generates deterministic DuckDB 1.4.3 databases using the SHA-256-pinned v1.4.3 `linux_amd64` `tpch` and `tpcds` extensions.

- **NYC TLC / HVFHV, Natural Earth, OSM, US Census, and SpreadsheetBench**:
  Input role bindings follow `evidence/e7-archived-native-replay-extension-10/INPUT-ROLES.example.json`. When optional external datasets are not bound locally, the native runner reports those entries explicitly as `NA` (missing input role) rather than conflating missing external downloads with verdict failures.

### 3. Hardware & Resource Notes
- Tiers 1 and 2 run within `2 GiB` RAM on any modern laptop (Linux, macOS, or Windows).
- Full 100M-row ClickBench and H2O `O3`/`O4`/`O5` censuses and `h2o-factorized-association-moments` were measured on a Linux x86_64 server and expect `>= 16 GiB` RAM (at least `32 GiB` recommended for full ClickBench UserID self-join materialization).
