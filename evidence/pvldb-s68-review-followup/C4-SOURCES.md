# C4 release-pair sources

The issue-to-release mapping comes from the frozen C4 roster. The merged PRs were linked by the issue or by the replay evidence. A dash indicates that the repair commit is unresolved. Visibility means that ordered equality detected at least one faulty arm. An E9 link is counted as positive only when its frozen annotation and issue URL agree.

| Mechanism | Issue | Upstream fix PR | Tested versions | Class | Ordered equality detects fault | ObsEq | E9 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| categorical-membership-logical-equality | [#13393](https://github.com/pola-rs/polars/issues/13393) | [#13412](https://github.com/pola-rs/polars/pull/13412) | 0.20.3 → 0.20.4 | O4 | yes | O4 | 0ba374621546c748 (yes) |
| copy-summary-bound | [#23504](https://github.com/duckdb/duckdb/issues/23504) | [#23693](https://github.com/duckdb/duckdb/pull/23693) | 1.5.4 → 1.5.5 | F6 | yes | O4 | 1704c4485c94173f (yes) |
| group-collation-type | [#8413](https://github.com/duckdb/duckdb/issues/8413) | [#9242](https://github.com/duckdb/duckdb/pull/9242) | 0.8.1 → 0.9.1 | F9 | yes | O4 | 05b3c62745ba9a1c (yes) |
| group-null-reassignment | [#63920](https://github.com/pandas-dev/pandas/issues/63920) | [#63961](https://github.com/pandas-dev/pandas/pull/63961) | 3.0.0 → 3.1.1 | F2 | yes | O3 | — |
| insert-decimal-export | [#13237](https://github.com/duckdb/duckdb/issues/13237) | [#13308](https://github.com/duckdb/duckdb/pull/13308) | 1.0.0 → 1.1.0 | O4 | yes | O4 | e13cd43e02acf948 (yes) |
| melt-timezone | [#55254](https://github.com/pandas-dev/pandas/issues/55254) | [#55270](https://github.com/pandas-dev/pandas/pull/55270) | 2.1.1 → 2.2.0 | F8 | yes | O4 | 24b53cc5eacd14fe (yes) |
| nested-sibling-null-explode | [#6335](https://github.com/pola-rs/polars/issues/6335) | [#6339](https://github.com/pola-rs/polars/pull/6339) | 0.15.15 → 0.15.16 | F2 | yes | O3 | 050c172835a2dd23 (yes) |
| nested-timezone | [#20766](https://github.com/pola-rs/polars/issues/20766) | [#20822](https://github.com/pola-rs/polars/pull/20822) | 1.20.0 → 1.22.0 | F8 | yes | O4 | 06df66ae81378ec0 (yes) |
| null-sort-topn | [#24363](https://github.com/duckdb/duckdb/issues/24363) | [#24399](https://github.com/duckdb/duckdb/pull/24399) | 1.5.5 → 2.0.1 | F2 | yes | O3 | 14420bbd4b81436a (yes) |
| nullable-cumulative-group-type | [#65550](https://github.com/pandas-dev/pandas/issues/65550) | [#65551](https://github.com/pandas-dev/pandas/pull/65551) | 3.0.3 → 3.1.0 | F9 | yes | O4 | 02050e2e7fd2c5bc (yes) |
| pandas-annual-boundaries | [#56134](https://github.com/pandas-dev/pandas/issues/56134), [#56147](https://github.com/pandas-dev/pandas/issues/56147) | [#56831](https://github.com/pandas-dev/pandas/pull/56831) | 2.3.3 → 3.0.0 | F6 | yes | O3 | — |
| pandas-asof-string-boundary | [#50946](https://github.com/pandas-dev/pandas/issues/50946) | [#62943](https://github.com/pandas-dev/pandas/pull/62943) | 2.3.3 → 3.0.0 | F6 | yes | O3 | — |
| pandas-groupby-snapshot | [#63219](https://github.com/pandas-dev/pandas/issues/63219) | [#63232](https://github.com/pandas-dev/pandas/pull/63232) | 2.3.3 → 3.0.0 | F3 | yes | O1 | — |
| pandas-historical-rolling-moments | [#54380](https://github.com/pandas-dev/pandas/issues/54380) | [#63143](https://github.com/pandas-dev/pandas/pull/63143) | 2.3.3 → 3.0.0 | F7 | yes | O3 | — |
| pandas-idempotent-partial-key-write | [#61841](https://github.com/pandas-dev/pandas/issues/61841) | [#62404](https://github.com/pandas-dev/pandas/pull/62404) | 2.3.3 → 3.0.0 | F5 | yes | O5 | — |
| pandas-index-uniqueness-cache | [#57911](https://github.com/pandas-dev/pandas/issues/57911) | [#57958](https://github.com/pandas-dev/pandas/pull/57958) | 2.3.3 → 3.0.0 | F4 | yes | O2 | — |
| pandas-reversed-positional-write | [#65446](https://github.com/pandas-dev/pandas/issues/65446) | [#65864](https://github.com/pandas-dev/pandas/pull/65864) | 2.2.3 → 3.1.1 | F5 | yes | O5 | — |
| pandas-timedelta-cancellation | [#66551](https://github.com/pandas-dev/pandas/issues/66551) | [#66640](https://github.com/pandas-dev/pandas/pull/66640) | 2.2.3 → 3.1.1 | F7 | yes | O3 | — |
| pivot-null-buckets | [#27272](https://github.com/pola-rs/polars/issues/27272) | [#27273](https://github.com/pola-rs/polars/pull/27273) | 1.39.3 → 1.40.0 | F2 | yes | O3 | — |
| polars-cache-lineage | [#29788](https://github.com/pola-rs/polars/issues/29788) | [#29793](https://github.com/pola-rs/polars/pull/29793) | 2.0.0 → 2.1.0 | F4 | yes | O2 | — |
| polars-categorical-series-topk | [#28344](https://github.com/pola-rs/polars/issues/28344) | [#28359](https://github.com/pola-rs/polars/pull/28359) | 1.42.1 → 1.43.0 | O3 | yes | O3 | — |
| polars-grouped-coupled-representative | [#29630](https://github.com/pola-rs/polars/issues/29630) | [#29639](https://github.com/pola-rs/polars/pull/29639) | 1.44.2 → 2.0.0 | O3 | yes | O3 | — |
| precision-ring-measure | [#1365](https://github.com/libgeos/geos/issues/1365) | [#1372](https://github.com/libgeos/geos/pull/1372) | 3.13.1;3.14.1 → 3.15.0 | F10 | yes | O4 | 807d8d0f0d3efba2 (yes) |
| prepared-snapshot-count | [#21207](https://github.com/duckdb/duckdb/issues/21207) | — | 1.4.3 → 2.0.1 | F3 | yes | O1 | 59890e2bc86255d1 (yes) |
| rolling-variance-cancellation | [#46049](https://github.com/pandas-dev/pandas/issues/46049) | [#46431](https://github.com/pandas-dev/pandas/pull/46431) | 1.4.1 → 1.5.0 | F7 | yes | O3 | 0a8573e459bc9e68 (yes) |
| styler-index-representation | [#53464](https://github.com/pandas-dev/pandas/issues/53464) | [#53017](https://github.com/pandas-dev/pandas/pull/53017) | 2.0.1 → 2.1.0 | F1 | yes | O4 | 14c38ae3f4c5ecd8 (yes) |
| uint64-mixed-input | [#12032](https://github.com/pola-rs/polars/issues/12032) | [#12045](https://github.com/pola-rs/polars/pull/12045) | 0.19.11 → 0.19.13 | F1 | yes | O4 | 23d83ce3eb700d2d (yes) |
| upsert-state-and-receipt | [#16698](https://github.com/duckdb/duckdb/issues/16698), [#17143](https://github.com/duckdb/duckdb/issues/17143) | [#18480](https://github.com/duckdb/duckdb/pull/18480) | 1.2.1;1.2.2 → 1.4.0 | F5 | yes | O5 | — |
| valid-segment-intersection | [#565](https://github.com/libgeos/geos/issues/565) | [#570](https://github.com/libgeos/geos/pull/570) | 3.10.2 → 3.10.3 | F10 | yes | O4 | 05a1886dda261bc5 (yes) |

For [#21207](https://github.com/duckdb/duckdb/issues/21207), maintainers added the [`fixed on nightly` label](https://api.github.com/repos/duckdb/duckdb/issues/events/33066292492) on 2026-10-12 and [closed the issue as completed](https://api.github.com/repos/duckdb/duckdb/issues/events/33108312484) on 2026-10-13. The repair commit is unresolved. An earlier candidate was [#20885](https://github.com/duckdb/duckdb/pull/20885). On March 8, 2026 the reporter replied that the issue still reproduced on main. The table gives the tested versions.
