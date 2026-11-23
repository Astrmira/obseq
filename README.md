# ObsEq: Correctness Oracles Benchmark, Adapter Suite, and SQL Validator

**ObsEq** is the open benchmark corpus, multi-tool oracle adapter suite, offline exact reference collection, and zero-annotation SQL cutoff validator accompanying our PVLDB study:

> **Stricter Is Not Safer: An Experimental Study of Correctness Oracles in Data Systems \[Experiment, Analysis & Benchmark\]**  
> Xu Cao and Wenxuan Xiao (*Astrmira Tech.*)

Every test of a data system ends in an oracle $O = (\pi, \approx, r)$ combining an **observation** $\pi$ of an execution with a **comparison relation** $\approx$ on observations. **ObsEq** evaluates 26 deployed oracle configurations (official benchmark checkers, generic comparators, and 16 configurations of `pandas`, `Polars`, `DataComPy`, `dbt`, `Great Expectations`, `Deequ`, `DVC`, and `SQLLogicTest`) alongside deployable contract-and-witness checks (`O1`–`O5`) against independent arbitrary-precision references.

---

## Quickstart (3 Reproducibility Tiers)

Full instructions, hardware budgets, and dataset acquisition scripts are documented in **[REPRODUCIBILITY.md](REPRODUCIBILITY.md)**.

### 1. Offline Ledger & Receipt Verification (`< 2 min`, Python 3.11+ stdlib only, zero downloads)
Verifies every `SHA256SUMS` digest and `NUMBERS.json` entry, re-executes the independent `C2` contract interpreter (108 cases), and recounts all held-out (`C2`), benchmark (`C3`), natural bug-fix (`C4`, 29 release pairs), and contract-size (`A5`) matrices:

```sh
python -B replay.py
```

### 2. Pinned Comparator Matrices & SQL Window Validator (`< 10 min`)
Installs the hash-locked Python environment (`requirements.lock`), replays the native comparator matrices across `C2` and `C4`, and runs the tie-aware SQL window validator smoke tests:

```sh
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-build-isolation --no-deps -e .
python -B replay.py --comparators
```

### 3. Containerized Native Producer Replay & Full-Scale Datasets
Re-runs native multi-engine producers and acquires SHA-256-pinned public datasets (`ClickBench` 100M rows, `TPC-H`/`TPC-DS` `SF1`/`SF10`):

```sh
python -B fetch_clickbench.py /path/to/clickbench_hits
python -B build_tpc.py --help
# See docker/README.md and REPRODUCIBILITY.md for containerized execution
```

---

## Using the Zero-Annotation SQL Cutoff Validator (`O3`)

`ObsEq` derives complete `ORDER BY ... LIMIT ... OFFSET` tie contracts directly from SQL (`sqlglot` AST analysis + `DuckDB` schema/type binding) and verifies candidate outputs in $O(|R|\log|R|)$ time without manual annotations:

```python
import duckdb
import pyarrow as pa
from verify_windows import call

with duckdb.connect() as conn:
    conn.execute("CREATE TABLE hits (phrase VARCHAR, ts INTEGER)")
    conn.execute("INSERT INTO hits VALUES ('alpha', 10), ('beta', 5), ('gamma', 5)")

    sql = "SELECT phrase FROM hits ORDER BY ts DESC LIMIT 2"
    candidates = {
        "thread_1": pa.table({"phrase": ["alpha", "beta"]}),     # legal tie choice
        "thread_8": pa.table({"phrase": ["alpha", "gamma"]}),    # legal tie choice
        "corrupted": pa.table({"phrase": ["alpha", "missing"]}), # ineligible witness
    }
    verdicts = call(conn, sql, candidates)
    # verdicts["thread_1"]["accepted"] == True
    # verdicts["thread_8"]["accepted"] == True
    # verdicts["corrupted"]["accepted"] == False
```

---

## Paper-to-Repository Map

Every number reported in the paper is registered with its exact denominator, `artifact_path`, SHA-256 digest, and replay command in **`NUMBERS.json`**.

| Paper Section / Artifact | Description | Primary Repository Location |
| --- | --- | --- |
| **§2, Table 1** | Formal $(\pi, \approx, r)$ model, `O1`–`O5`, `F1`–`F10`, `M1`–`M7` | [`TAXONOMY.md`](TAXONOMY.md) |
| **§4.1, Table 3** | 305-query static SQL inventory, 30-query manual audit, 116-window uniqueness census & `ObsEq` validator (`232/232` accepted; `201/201` cardinality & `549/549` equal-length controls rejected) | `evidence/pvldb-a1-query-inventory/`, `evidence/pvldb-a7-typed-candidates/`, `evidence/pvldb-a2-clickbench-typed-windows/` |
| **§4.2, Table 4** | Official benchmark checkers (`ClickBench`, `CWI roundingdiff`, `H2O chk`, `SpreadsheetBench` grader) & 16 tool configs on native TPC SF10 and ClickBench outputs (`C3`, including positional & natural-key `DataComPy` and independent `Q59` source scan) | `evidence/pvldb-native-baseline-matrix/`, `evidence/pvldb-a2-q39-real-output/`, `evidence/pvldb-a10-spreadsheetbench-scorer/`, `evidence/tpch-sf10-bundled-vs-workload-q11/`, `evidence/tpch-sf10-q21-secondary-rank/` |
| **§5.1, Table 5, Figure 2** | Development mechanism matrix (`C1`: 60 legal variants, 30 faults across `F1`–`F10`) over 10 comparators & 16 tool configs | `evidence/submission-e-series-native-evidence/`, `evidence/e7-archived-native-replay-extension-10/` |
| **§5.2, Table 6** | Replication on 246 independently authored held-out cases (`C2`) and 29 natural bug-fix release pairs (`C4`, 968 per-arm contract replays) | `evidence/pvldb-native-baseline-matrix/`, `evidence/pvldb-a3-independent-panel/`, `evidence/pvldb-a3-heldout-value-observers/`, `evidence/pvldb-a4-natural-roster/` |
| **§6, Figure 3** | Full-dataset censuses: 317M NYC TLC trips & HVFHV DST night, 100M ClickBench 64-bit ID joins, GEOS WKB encodings, 2,000 SpreadsheetBench caches, 300-issue tracker audit | `evidence/tlc-complete-published-clock-transition-coverage/`, `evidence/hvfhv-native-fold-duration-constraints/`, `evidence/pvldb-a2-clickbench-left-join/`, `evidence/e4-direct-geos-version-order-matrix/`, `evidence/pvldb-a6-cache-transitions/` |
| **§7, Table 7** | Runtime cost at $10^8$ rows (`O1`–`O5`), durable write-side epoch overhead, and contract specification census | `evidence/pvldb-a5-epoch-writer/`, `evidence/sqlite-wal-native-snapshot-cost/`, `evidence/sqlite-write-intent-receipt-cost/`, `evidence/exact-dyadic-predicate-gate/` |

---

## Repository Layout

- `replay.py` — Unified entrypoint for Tier 1 (offline digest & receipt verification), Tier 2 (`--comparators`), and Tier 3 (`--native-inputs`, `--original-environment`).
- `NUMBERS.json` — Machine-verified ledger mapping paper claims to `evidence/` artifacts, SHA-256 digests, and replay commands.
- `SHA256SUMS` — Manifest of SHA-256 checksums across all shipped files.
- `TAXONOMY.md` — Contract (`O1`–`O5`), fault (`F1`–`F10`), mutant (`M1`–`M7`), and cohort (`C1`–`C4`) definitions.
- `REPRODUCIBILITY.md` — Step-by-step instructions for all three verification tiers.
- `fetch_clickbench.py` / `build_tpc.py` — Verified dataset acquisition and generation utilities.
- `zoneinfo/` — Bundled public-domain IANA `tzdata` 2025b TZif files for deterministic civil-time tests.
- `docker/` — Containerized Linux runtime specification for full native producer replay.
- `evidence/` — Self-contained cohort packages, queries, schemas, adapters, and frozen receipts.

## License

Released under the [MIT License](LICENSE).
