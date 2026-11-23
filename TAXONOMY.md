# ObsEq Taxonomy: Failure Modes, Contracts, Faults, and Cohorts

We model a correctness oracle as $O = (\pi, \approx, r)$, where $\pi$ maps an execution $e$ to an observation, $\approx$ is a binary comparison relation on observations (not necessarily transitive, so numeric tolerances fit directly), and $r$ is a reference execution or expected property. Given an intended input state $s$ and contract-legal set $L(s)$:

- **Over-strict**: $[r]_{\approx} \subsetneq L(s)$ on reachable outputs, rejecting legal variations (ties, unspecified row order, floating-point evaluation order, alternative geometry or text encodings).
- **Over-lenient**: $[r]_{\approx} \supsetneq L(s)$ on reachable outputs, accepting corrupted answers (keys altered within relative tolerance, partner swaps preserving column sums, cardinality-preserving value corruption).
- **Blind**: $\pi(e_1) = \pi(e_2)$ for a legal execution $e_1$ and an illegal execution $e_2$. By Proposition 2.1, **stricter is not safer**: no comparison relation $\approx$ can separate $e_1$ and $e_2$ without extending $\pi$ by a state or intent witness.

---

## 1. Contract & Witness Oracle Classes (`O1`–`O5`)

| Class | Role in $(\pi, \approx)$ | Contract / Witness Mechanism | Covered Surfaces |
| --- | --- | --- | --- |
| **O1** Logical snapshot binding | Extends $\pi$ | Binds logical snapshot identity, committed WAL state, and query/scale parameters rather than raw file bytes | SQLite WAL snapshots, scale-bound benchmark parameters (e.g., TPC-H Q11) |
| **O2** Derived-state freshness | Extends $\pi$ | Tracks dependency epochs per derived table, column, or cache | Stored generated columns, materialized views, cached aggregates |
| **O3** Legal result family | Refines $\approx$ | Decides membership in $L(s)$ via complete-key cutoff guards, group-representative predicates, and exact rational ULP envelopes | `ORDER BY ... LIMIT ... OFFSET` ties, nested limits, representatives, `DOUBLE` reductions |
| **O4** Representation quotient | Refines $\approx$ | Compares canonical decoded values rather than surface bytes | Topological point sets (WKB/GEOS), numeric strings, spreadsheet date serials, `GROUPING` markers |
| **O5** Intent and effect | Extends $\pi$ | Records explicit write-intent receipts (`KEEP`, `CLEAR`, `WRITE`) alongside post-state effects | Partial updates, patch overlays, ordered multi-step interventions |

---

## 2. Development & Replication Fault Classes (`F1`–`F10`)

| Fault | Name | Representative Mechanism |
| --- | --- | --- |
| **F1** | `int64` $\to$ `float64` identity loss | 64-bit integer keys above $2^{53}$ cast through IEEE-754 binary64 |
| **F2** | `NULL` join policy | Replacing `=` with null-safe `IS NOT DISTINCT FROM` / `IS` in an inner join |
| **F3** | Stale snapshot | Copying a main database file without committed WAL frames, or reading an outdated snapshot |
| **F4** | Stale derived state | Retaining a `STORED` generated column or derived summary after its upstream definition or input changes |
| **F5** | `KEEP` $\to$ `CLEAR` intent collapse | Writing an explicit `NULL` where the step contract requires leaving an already-`NULL` field untouched |
| **F6** | Illegal cutoff witness | Substituting an ineligible row that shares the boundary sort key in a tied top-$k$ result |
| **F7** | Aggregate cancellation | Applying equal-and-opposite or partner-swapping changes across rows while preserving column sums |
| **F8** | Civil-time ambiguity | Resolving repeated or nonexistent daylight-saving wall times against the declared policy |
| **F9** | Representative & physical type | Altering a selected group representative's physical type (`INTEGER` vs. `REAL` vs. `TEXT`) or cross-column coherence |
| **F10** | Geometry boundary drift | Snapping or repairing vertices so that exact topological coverage changes |

---

## 3. Benchmark Output Mutation Operators (`M1`–`M7`)

Applied to native benchmark outputs in Cohort `C3` only where structurally applicable:

- **M1**: Increment/change an exact integer key by `1` across all projected occurrences (e.g., TPC-DS Q39 item key `1265 -> 1266`).
- **M2**: Swap non-key payload values between two output rows, preserving row count, schema, and exact column sums (e.g., H2O 10M Q3).
- **M3**: Replace a tied boundary row with an ineligible candidate sharing the cutoff score.
- **M4**: Mislabel a rollup subtotal hierarchy level when inferring `GROUPING` from `NULL` (e.g., TPC-DS Q86).
- **M5**: Perturb a floating-point measure outside its exact rational evaluation-order envelope while staying within $10^{-5}$ relative tolerance.
- **M6**: Round-trip a 64-bit identifier through `binary64`.
- **M7**: Drop the `NULL`-key detail group.

---

## 4. Evaluation Cohorts (`C1`–`C4`)

Cohorts are evaluated and reported separately without pooling denominators:

- **C1 (Development mechanisms)**: 60 native legal variants (4 `O3` + 3 `O4` mechanisms) and 30 native injected faults (3 per `F1`–`F10`).
- **C2 (Independently authored held-out cases)**: 108 cases plus 138 later panel cases authored from the taxonomy and adapter interface alone without access to `C1` cases or results.
- **C3 (Real benchmark outputs)**: Native outputs across thread counts, engines, and input orders on TPC-H, TPC-DS, ClickBench, and H2O, paired with frozen `M1`–`M7` mutants.
- **C4 (Natural library bugs)**: 29 native old/new release pairs from `pandas`, `Polars`, `DuckDB`, and `GEOS` where the older release produces a wrong result fixed in the newer release.
