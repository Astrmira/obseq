# EA&B E5: GX compound uniqueness depends on string equivalence and NULL scope

Use the already admitted official H2O Join medium RHS SHA and select its first 12 physical rows, retaining id5 and integer id1 as token and group. This is benchmark source, not production IDs. Add four authored uppercase aliases preserving group and original records; explicitly separate literal duplicates, partial/full-NULL duplicate controls and Unicode cases. SQL BINARY and NOCASE tables are checked to contain identical typed rows and text values, and Pandas preserves integers using nullable Int64. An independent Python exact/binary or ASCII-fold oracle compares the whole unexpected tuple bags with multiplicity. For these small inputs the complete count equals the reported partial unexpected list. This metric does not emit row IDs here; none inferred.

| Case, no ignored rows | Pandas | SQLite BINARY | SQLite NOCASE |
|---|---:|---:|---:|
| Raw source | 0 | 0 | 0 |
| ASCII case aliases | 0 (pass) | 0 (pass) | 8 (fail) |
| ASCII aliases plus distinct non-ASCII and four duplicate NULL-bearing rows | 4 | 4 | 12 |
| Two literal duplicate pairs | 4 | 4 | 4 |
| Explicit ASCII-folded mixed cohort | 12 | 12 | 12 |

Counts are unexpected occurrences, not distinct pairs. SQLite NOCASE folds ASCII only as [documented](https://sqlite.org/datatype3.html#collating_sequences); Unicode controls show no added case equivalences. GX 1.25.0 uses Pandas duplicated(keep=False) versus native SQL window COUNT partitions over the indicated inputs, as checked in installed metric source (SHA 49f543a2da906eaef5ddae62693c8929e75a6afc45b4f4bced5941a89156a41c). The [GX uniqueness guide](https://docs.greatexpectations.io/docs/reference/learn/data_quality_use_cases/uniqueness/) and [expectation listing](https://greatexpectations.io/legacy/v1/expectations/expect_compound_columns_to_be_unique/) describe the operation and ignore-row options. All 45 native calls match their independent policy oracles. The all-values-missing option drops only two all-NULL occurrences; any-value-missing drops all four, irrespective of collation.

**Admission:** uniqueness is a predicate on eligible equivalence classes, not schema-free values. For a byte-exact key use BINARY; for this ASCII-folded contract canonicalize all inputs before native uniqueness and preserve their original form for other consumers. The positive folded control aligns all three. Bind eligibility/NULL policy, declared key equivalence and versioned adapter; portability requires an equality-reflecting canonicalization or matching backend semantics. Documented policy difference on the same values, not a tool defect or Unicode, prevalence, timing or deployment claim.

Replay python3 -IB check.py ADMITTED_H2O_GENERATOR_DIR PINNED_GX_DIR and compare stdout with RESULT.json. Uses previously installed GX dependencies; runtime versions and wheel provenance recorded. No new installs, persistent DB, raw benchmark IDs or Git.
