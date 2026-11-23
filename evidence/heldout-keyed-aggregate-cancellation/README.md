# E7 independent F7 holdout: keyed values lost by exact summaries

An independently authored, blinded 24-case panel tests exact committed values at each stable integer key, including NULL, multiplicity and group identity. Input row order is irrelevant. The panel contains 12 legal and 12 illegal cases, authored from the interface before access to this study's observations. Its two file digests were recorded before use. The observer and its result were frozen before opening the new labels.

| Observer | False admissions of 12 illegal (each engine) | False rejections of 12 legal (each engine) |
|---|---:|---:|
| Total row count and distinct-key count | 10 | 0 |
| Per-group row count, nonnull count, and sum | 8 | 0 |
| Add per-group exact sum of squares and extrema | 5 | 0 |
| Compare each group's entire positionless value bag | 5 | 0 |
| Compare each complete keyed, nullable bag | 0 | 0 |

Native SQLite and DuckDB agree on every decision. The exact checker compares signed multiplicities after UNION ALL and GROUP BY over the full keyed value; the bag control removes only the key. No floating arithmetic, absent value coercion, probabilistic hash, or relational set deduplication is used. Identical counters for the two middle observers are an outcome for this panel, not equivalence of those observers. If the consumer only promises group aggregates, some differences can instead be legal; this panel explicitly promises keyed output.

The earlier frozen SQLite query execution failed on a SQL assembly error, before any observations were produced; the corrected assembly was re-frozen without changing queries' meaning, cases or labels. Neither discarded execution nor any pre-existing holdout contributes an observation. The 48 paired engine decisions are not independent sets of cases and do not estimate natural production rates.

Replay with the pinned versions in OBSERVED.json, no native data download:

    set -e -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B check.py CASES.json | cmp - OBSERVED.json
    python3 -IB score.py | cmp - SCORES.json
