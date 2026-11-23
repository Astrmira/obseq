# E3/E5: native exact-comparison admission is engine-dependent

Extend the DuckDB dual EXCEPT ALL detector audit
to native PostgreSQL 17.12 and SQLite 3.53.1 on the same pinned 22,743 public
Tweet IDs, stable unique row token, and one authored NULL. The only primary
mutation is narrowing the ID to binary64. Independent Python integer
ties-to-even finds 10,665 changed IDs. Source values are not included here.

| Engine and comparator | Forward and reverse differences |
| --- | --- |
| DuckDB 1.4.3 and 2.0.1, native mixed-type EXCEPT ALL (prior receipt) | 0 / 0 |
| PostgreSQL 17.12, native mixed-type EXCEPT ALL | 0 / 0 |
| PostgreSQL 17.12, exact integer comparison after conditional finite integral lift | 10,665 / 10,665 |
| SQLite 3.53.1, native mixed-type EXCEPT | 10,665 / 10,665 |
| SQLite 3.53.1, grouped bag difference with no input affinity | 10,665 / 10,665 |
| SQLite 3.53.1, explicitly narrow both sides before native EXCEPT | 0 / 0 |

The native DISTINCT detector is sufficient for this unique ordinal panel,
not for a general bag; the separately authored duplicate control proves the
grouped SQLite baseline reports the two multiplicity differences. Its
grouping uses two independent counters, not a digest. PostgreSQL same-type
EXCEPT ALL also retains those two differences, while PostgreSQL EXCEPT erases
them. PostgreSQL binds the mixed pair to double precision; related native
scalar equality declares all 22,743 nonnull pairs equal, compared with only
12,078 under exact integer equality. BIGINT-to-NUMERIC widening is a legal
value-preserving PostgreSQL negative control: no differences in either direction.
An authored PostgreSQL JSONB object with an explicit null member remains
different from one with that member absent; this is a different representation
from the prior DuckDB STRUCT example, not a direct native nested-type match.

[PostgreSQL type resolution for EXCEPT](https://www.postgresql.org/docs/17/typeconv-union-case.html)
and [SQLite compound SELECT](https://www.sqlite.org/lang_select.html#compound_select_statements)
document different operation scopes. This is an engine-default semantic
difference, not an engine defect. A detector with exact bag logic cannot
repair an inadmissible common representation. Conversely mixed declared
types need not imply a lossy comparator. Record resolved comparison semantics
and the intended row equivalence before interpreting empty output as exactness.
No speed, prevalence, production-ID recovery, or general SQLite coercion
claims.

Run `python3 -IB check.py TWEET_TEXT_DIR PG_BIN_DIR SCRATCH_DIR | cmp - RESULT.json`.
Use Python with the stated built-in SQLite version and the already installed
PostgreSQL 17.12 binaries. The check creates a private temporary standalone
cluster without listening, verifies input digests, then removes only that
generated scratch cluster; no source writes or external downloads.
