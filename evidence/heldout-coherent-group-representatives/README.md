# E7: sealed coupled group representatives across three native engines

A new independent author sealed 24 inputs and 24 answers before seeing
any adapter outputs. Native DuckDB 2.0.1, PostgreSQL 17.12 and SQLite
3.53.1 predictions were frozen at 2026-11-21 21:43:50 UTC, before the
executor read the authored labels. This is separate from the
real TLC representative audit
and every older holdout.

The contract is exact selected minimum score, one complete witness
per eligible group, and NULL-safe equality on a coherent tied tuple.
A named ordinal binds that actual source row. If the ordinal is
omitted, any coherent tied source witness suffices. All-null groups
do not require output. Native SQL checks use the same contract across
the three engines; these are not scoring differences between engine
defaults. Explicit SQL ordering requirements are outside this scope.

All three engines make the same verdicts against the 10 legal and
14 illegal independently authored inputs:

| Comparator | False accept | False reject |
| --- | ---: | ---: |
| Coupled, identity-aware exact guard | 0 | 0 |
| Fixed lowest-ordinal golden | 0 | 2 |
| Independent field marginals (omits named claimed identity) | 6 | 0 |

Every method still enforces the exact shared group, minimum and count
constraints. The intentionally weaker marginal control fails both
when compatible marginal values cannot occur in one tied row and
when an attractive tuple is claimed against the wrong ordinal. The
lowest-ordinal baseline is too strong for this contract because it
excludes other authorized representatives. The fixture counters are
not prevalence estimates or reports of native database defects.

Reproduce with the pinned versions and an already installed local
PostgreSQL binary directory:

    set -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B run.py CASES.json PG_BIN_DIR SCRATCH_DIR | cmp - PREDICTIONS.json
    python3 -B score.py | cmp - RESULT.json

The PostgreSQL worker never listens and cleans only its generated
scratch cluster. Source and labels are entirely authored.
