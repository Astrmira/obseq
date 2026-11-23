# E7 independent holdout: ordered intervention receipts under native SQL execution

A fresh 24-case panel authored from the typed interface alone was sealed independently of the runner, balanced 12 legal and 12 illegal. Root froze the observer and its output before opening the new labels. This panel does not alter or inspect any prior holdout. It tests a named single-key assignment and outcome contract, not an arbitrary SQL equivalence contract.

| Observer | False admits of 12 illegal per engine | False rejects of 12 legal per engine |
|---|---:|---:|
| Post-state only | 9 | 0 |
| Committed post-state | 7 | 0 |
| Committed post-state plus write event count | 4 | 0 |
| Committed post-state plus unordered semantic event bag | 3 | 0 |
| Committed post-state plus ordered typed events | 0 | 0 |

Two native semantics produce matching post-state and ordered committed receipts on every case: SQLite AFTER UPDATE inside the transaction and DuckDB UPDATE RETURNING fed into an explicit receipt table inside the same transaction. These are separate adapters, not interchangeable engine features. The declared COMMIT or ROLLBACK branch executes in the engine; comparison uses that agreed outcome and the durable receipt rows. Explicit same-value updates count as events; KEEP and a missing target do not. In this contract a NULL assignment means CLEAR, nonnull integer assignment means WRITE. The model is closed over the stated tables, uses single-key update statements, and observes the order across statements, not arbitrary native trigger or RETURNING row order. It does not claim proof against an untrusted reporter or cover cascades, concurrency, lineage, or external effects.

The 48 engine-by-case decisions are paired replays of the same 24 fixtures. The balanced, authored cohort does not estimate production fault prevalence or cross-engine independence. Exact engine versions are in OBSERVED.json. Reproduce from the packet, without downloading a data set:

    set -e -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B check.py CASES.json | cmp - OBSERVED.json
    python3 -IB score.py | cmp - SCORES.json
