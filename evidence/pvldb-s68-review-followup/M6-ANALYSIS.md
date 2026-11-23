# Full-window validator measurements

All 580 fresh workers completed successfully across the frozen 116 SQL windows. TPC-H and TPC-DS use SF10. ClickBench uses all 100 publisher partitions. `AST-RAW.jsonl` preserves every worker. `AST-SUMMARY.json` agrees exactly with the independently replayed public summary.

Each window first takes the median of its five workers. The distributions below summarize those 116 window medians. A worker first executes and fetches the original query, then calls the unchanged public validator. The validator recomputes the complete candidate relation.

| Metric | Median | p90 | Maximum |
| --- | --- | --- | --- |
| Original producer time, s | 1.306512 | 5.712461 | 27.778134 |
| Additional validator time, s | 1.468994 | 6.542399 | 28.089995 |
| Validator/producer ratio | 1.169669 | 2.802846 | 10.878051 |
| Bind/compile diagnostic, s | 0.009227 | 0.016519 | 0.056663 |
| Candidate CTAS diagnostic, s | 1.053466 | 6.036799 | 27.716702 |
| Check on materialized candidates, s | 0.014039 | 0.276887 | 4.894727 |
| End-to-end worker RSS, KiB | 591,414 | 1,929,382 | 7,259,456 |
| Diagnostic worker RSS, KiB | 607,358 | 1,986,870 | 12,374,584 |

The diagnostic stages execute in a second pass after the first validator call in the same worker and retain a materialized candidate relation. Their times describe that separate execution. RSS is the process high-water mark and includes producer allocations. The environment record identifies shared-host load and unflushed OS caches.

## Slowest absolute validator calls

| Window | Producer median, s | Validator median, s | Candidate CTAS median, s | Materialized check median, s | Candidate rows |
| --- | --- | --- | --- | --- | --- |
| ClickBench Q29 | 27.778134 | 28.089995 | 27.716702 | 0.019379 | 77 |
| TPC-DS Q67 | 20.271853 | 20.073149 | 19.534457 | 0.024446 | 1,107 |
| TPC-DS Q4 | 11.524002 | 17.004205 | 16.432347 | 0.012260 | 620 |

ClickBench Q29 evaluates a regular expression on Referer values, aggregates by the resulting host string and applies HAVING before the ordered window. Recomputing that candidate query dominates the measured validation time. The final 77-row relation checks in about 19 ms after materialization.

TPC-DS Q67 joins sales, dates, stores and items, computes an eight-dimension ROLLUP and applies a partitioned rank before the outer window. Its candidate materialization takes about 19.5 seconds. Checking the resulting 1,107-row relation takes about 24 ms.

TPC-DS Q4 builds customer/year aggregates across store, catalog and web sales, then joins six aliases to compare year-over-year ratios. Candidate recomputation accounts for most of its validator duration. Its 620-row materialized relation checks in about 12 ms.

## Largest relations and relative overhead

ClickBench Q33 has the largest candidate relation, 99,997,493 grouped WatchID/ClientIP rows. Its boundary peer pool contains 99,997,489 rows. Its producer, validator, candidate CTAS and materialized check medians are 4.709461, 7.263147, 6.177184 and 2.905009 seconds. Its end-to-end worker RSS is 7,259,456 KiB.

ClickBench Q32 adds a nonempty SearchPhrase filter to that grouping. All 13,172,392 candidate groups belong to its boundary peer pool. Producer, validator, candidate CTAS and materialized check medians are 1.735401, 2.399299, 1.911725 and 0.409878 seconds. The full relation and peer counts are checked against the preexisting native census in every worker.

TPC-DS Q41 has the largest median relative overhead, 10.878051 times its producer duration. Its producer median is about 35 ms and its validator median about 386 ms. The later bind/compile, candidate CTAS and materialized-check medians are about 15, 29 and 8 ms. The extra first-call cost is retained in the end-to-end result. Its attribution to initialization or query planning remains unresolved.

The paired ratio median across windows is 1.169669 for the additional check. Adding the producer gives a median checked-run ratio of 2.169669. The corresponding p90 and maximum are 3.802846 and 11.878051.

Recount the complete profile with `python -B summarize_ast.py`. The ledger entries `s68.ast.*` link these distributions and required window profiles to the raw source digest.
