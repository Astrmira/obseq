# EA&B E7: prospective JSON presence and shape labels across three engines

Independent author sealed 24 small authored inputs and expected labels without
reading any adapter output. The executor froze the protocol/code and
sealed all native predictions at 2026-11-21 21:07:52 UTC, then read the
author's already digested label file. The independent expected results agree
with all 24 predictions from each of the three native engines: DuckDB 2.0.1,
PostgreSQL 17.12 and SQLite 3.53.1. Agreement includes first failure positions,
typed terminal values (for example false versus integer zero), and literal
special-character object keys. These probes do not reuse an older holdout.

A path step declares key or index explicitly. Check container type before
looking up the child, and keep the child encoded as JSON until the next step
or terminal classification. DuckDB and SQLite use native type probes and
entry enumeration; SQLite additionally preserves scalar JSON tags while
transporting child values. PostgreSQL uses native type probes and guarded
text/integer JSONB child access. The final output is either a precise value
or a precise non-value reason, rather than only an SQL NULL. See
[DuckDB JSON functions](https://duckdb.org/docs/2.0/data/json/json_functions),
[SQLite JSON functions](https://www.sqlite.org/json1.html) and
[PostgreSQL 17 JSON functions](https://www.postgresql.org/docs/17/functions-json.html).
None is characterized as returning a wrong default; this is an explicitly
chosen cross-engine evidence contract.

There were eight value cases, two explicit JSON nulls, three missing keys,
three missing indices and eight wrong containers. A null-only status
channel that projects all four non-value classes to one sentinel collapses
16 cases. Even a label-only decoder tuned to this panel could recover at
most 8/16 of those labels from that sentinel alone. That is a structural
information bound for the restricted observer, not a measured baseline
invocation or population accuracy estimate. No general claim about malformed
JSON, duplicate keys, large/fractional numbers, native JSONPath escaping,
production prevalence or performance.

Replay the frozen predictions using DuckDB Python 2.0.1, Python SQLite
3.53.1, and a local PostgreSQL 17.12 binary directory:

    set -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B run.py CASES.json PG_BIN_DIR SCRATCH_DIR | cmp - PREDICTIONS.json
    python3 -B score.py | cmp - RESULT.json

Only authored inputs and labels are distributed; no private data or exact
paths to the private source are required. PostgreSQL runs standalone
without listening and cleans only its generated temporary cluster.
