# Native Polars SQL grouped MIN projection: an engine-version and alias discriminator

Input table `q(v)`: A, a, a, B (literal ASCII). Group by lowercase A/a/a and B; minimum original string in first group is uppercase A, second B. Independent Python explicit bins, SQLite binary collation, and sorted multisets (not output order or SQL result-field names).

`SELECT MIN(v),COUNT(*) FROM q GROUP BY LOWER(v)`:
- Installed official Polars 1.31.0: rejects the query in the SQL layer.
- Installed official Polars 1.35.2: silently returns (a,1),(a,3), changing both representatives but retaining group sizes.
- Installed official Polars 2.1.0: gives expected (A,3),(B,1).

Adding only the distinct SQL output alias `MIN(v) AS lo` recovers correct results on all three. Aliasing only COUNT does not help the older versions. A SQL-derived table that names the lowercased column `k` and then groups by that column succeeds on all three. By contrast, relying on a same-scope SELECT alias in GROUP BY was rejected by both tested 1.x versions. With Polars 1.35.2, the unoptimized native plan places the MIN **outside** the grouped aggregate and groups by the lowercased `v` under the name `v`; with MIN alias the aggregate is computed inside. In 2.1.0 the direct query assigns a fresh internal key name and computes raw v MIN inside aggregation. No application-specific shim was called; qualifies as a native planning difference, not unsupported aggregation or an alias typo. Even direct GROUP BY v rather than an expression has a failing unaliased MIN on older versions; don't claim expression grouping is necessary.

Official release/tag: https://github.com/pola-rs/polars/releases/tag/py-2.1.0 ; official 2.x context: https://pola.rs/posts/polars-2-1-changelog/ . Related but not this exact fix: https://github.com/pola-rs/polars/pull/30939 (reviewed separately). That newer patch recomputes nonaggregate expressions of keys, with CASE and constant regressions, and was dated after the 2.1.0 release, so cannot explain the shift observed here. Do not claim first fixed release or exact introducing/fixing commit from three wells. For E7, split historical silent incorrect, unsupported, and current-match strata; specifying native version and exact SQL text is essential. The safe rewrite is demonstrated only for the scoped ASCII example, not an arbitrary preprocessor or SQL portability claim.

Reproduce `PYTHONPATH=<installed version site> python verify.py` for 1.31.0 (e5.json), 1.35.2 (e1.json), 2.1.0 (e4.json); then `python check.py`. No installs, Git changes, or issue posting.
