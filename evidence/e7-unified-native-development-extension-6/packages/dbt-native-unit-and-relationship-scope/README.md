# E5: native dbt fixed expected rows and per-field relationships bracket the real contract

Run stock dbt-core 1.10.15 and dbt-duckdb 1.9.6 against DuckDB 2.0.1.
Only a generated local project and five authored input rows are used.
No existing dbt test is modified. The three authored models choose a
minimum-score whole representative, either with ascending or descending
tie order, or intentionally build a fictitious tuple using separate
attribute minima from the tied set. A direct independent tuple oracle
says the first two are both legal and the third is not.

Native tests use the [stock unit-test interface](https://docs.getdbt.com/docs/build/unit-tests)
with exactly the same injected input and expected rows for all three.
The [stock generic data tests](https://docs.getdbt.com/reference/resource-properties/data-tests)
include unique and not-null group keys and independent relationship
tests from each scoped (group,value) projection to its genuine
minimum-score field support. An authored, native-executed singular
test checks whether all fields occur together in one eligible tied row.
For these fixtures the exact required group set is independently
verified by the Python oracle; the singular file by itself tests
coherence, not general missing-group admission.

| Produced model | Independent intent | Fixed native unit test | Stock generic tests | Coupled singular test |
|---|---|---|---|---|
| Ascending tie | legal | pass | all pass | pass |
| Descending tie | legal | fail | all pass | pass |
| Independent payload minima | illegal | fail | all pass | fail |

All 12 stock generic tests pass (three unique, three not-null and six
relationships). The native unit runner correctly checks its prescribed
golden, but that golden rejects a permitted alternate. Comparing each
relationship independently is weaker than checking a single source
row that realizes the whole tuple, even with consistent group binding.
The exact intent can be expressed as a singular data test; this is not
evidence about a dbt defect or recommended behavior without a declared
tie contract. No real-source prevalence, throughput or external
service claim.

    set -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B run.py DBT_DEPENDENCY_SITE_DIR SCRATCH_DIR | cmp - RESULT.json

The dependency directory contains the pinned existing wheels and bin/dbt.
The runner disables dbt anonymous usage statistics and cleans only its
generated private local project. All tests and data are authored.
