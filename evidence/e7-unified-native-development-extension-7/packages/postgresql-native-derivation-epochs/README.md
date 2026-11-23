# EA&B F4: rebuilding an expression index and refreshing a stored value are distinct operations

On 24,926 real NYC Yellow Taxi source rows, native PostgreSQL 17.12 classified the same rows against a versioned target rule using three physical paths. After the authored function revision, sequential reevaluation produced the new exact answers; both the expression index and the stored generated column still classified every row according to V1. Reindexing both paths repaired the expression-index result but left the stored generated result old. An explicit generated-column rewrite repaired the latter. A second cycle verified that the rewrite alone can refresh both paths in the tested schema.

| Native phase | Sequential re-evaluation | Indexed expression | Indexed generated value |
|---|---|---|---|
| V1 baseline | current | current | current |
| Function replaced with V2 | current | 24,926 stale memberships | 24,926 stale memberships |
| Both indexes reindexed | current | current | 24,926 stale memberships |
| Generated expression explicitly rewritten | current | current | current |
| Function replaced back to V1 | current | 24,926 stale memberships | 24,926 stale memberships |
| Direct SET EXPRESSION, no separate REINDEX | current | current | current |

Every stale membership is an authentic fixture row under its wrong bucket and a missing row under the correct one. All three routes still cover the whole input count: a total-count check cannot tell them apart.

## Exact experiment and interpretation

Use the exact [public NYC TLC Yellow Taxi November file](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page). Take all naive pickup timestamps in [2025-11-02 00:30,04:30), treating the recorded clocks merely as labels; there is no timezone or actual-trip inference. PyArrow 26.0.1 reads the original timestamp column and gives each retained observation a process-local row number. Independent integer hour/minute extraction assigns a 15-minute bucket V1; V2 advances one bucket modulo 96. No original file, origin timestamp or existing database service is modified. An authored disposable table alone stores the copied typed values. The native code verifies named plans and compares exact per-bucket row IDs, not only counts, on all 17 occupied-by-either-version buckets.

The [PostgreSQL volatility contract](https://www.postgresql.org/docs/17/xfunc-volatility.html) treats IMMUTABLE as a promise to the optimizer, not a command to refresh persisted artifacts after changing the definition. [Expression indexes](https://www.postgresql.org/docs/17/indexes-expressional.html) store computed expressions. [Stored generated columns](https://www.postgresql.org/docs/17/ddl-generated-columns.html) are computed on writes; a normal index storing that column simply reads the stored generation. [SET EXPRESSION AS](https://www.postgresql.org/docs/17/sql-altertable.html) rewrites existing generated values. This test deliberately changes a previously declared immutable function in scratch to expose a migration contract, not a PostgreSQL bug or a claim that breaking the immutable promise is safe. A valid receipt needs the source rows, active evaluation semantics, and when each involved persisted computation was built. The direct rewrite observation pertains to this particular table and PostgreSQL version.

Replay on Debian 13 amd64 compatible binaries from the official [PostgreSQL server package](https://packages.debian.org/trixie/amd64/postgresql-17/download) and [client package](https://packages.debian.org/trixie/amd64/postgresql-client-17/download), verified against PACKAGE.sha256. Unpack packages in scratch, use their bin directory, and use PyArrow 26.0.1. The runner starts the standalone backend in a temporary cluster without a listening network service and removes only the cluster it created. No identifiers, timestamps, fixture tables, packages or raw native result streams are redistributed.

    set -o pipefail
    sha256sum -c SHA256SUMS
    python -B check.py /path/to/2025-11.parquet /path/to/bin /path/to/writable/scratch | cmp - result.json
