# A1 review of the 30 frozen queries

Xu Cao, Wenxuan Xiao · 2026-11-23

The [per-query review](SQL-AUDIT.tsv) covers the five frozen queries in
each of six suites. Each SQL hash matches the [selection](HUMAN-AUDIT-QUEUE.tsv).
The review uses the original query, pinned schema and engine semantics, with
labels recorded before opening the [static results](INVENTORY.json) for the
selected queries. The sample was selected for coverage of distinct signatures.

## Reviewed mechanisms

| Label | Meaning in the review | Queries |
| --- | --- | ---: |
| a | Incomplete final order can select different projected members at a LIMIT boundary | 4 |
| b | Explicit order allows different visible rows within a peer group | 7 |
| c | LIMIT inside a subquery or CTE | 0 |
| d | An arbitrary representative can affect the projected value | 0 |
| e | Order-sensitive floating reduction among the functions in the experiment plan | 3 |
| f | Fixed projected multiset under the declared semantics and any explicit order | 18 |
| a0 | LIMIT without ORDER BY allows different projected members | 1 |
| corr | Floating correlation reduction outside the planned function list | 1 |

Labels `a` and `b` can overlap. For an unordered query classified as `f`, the
result multiset is fixed and its presentation order is free. The labels describe
possible behavior under the SQL and schema. Instance evidence uses the pinned
snapshots and is documented separately below.

## Agreement with the static inventory

| Axis | Resolved agreements | Cases with an unresolved automatic result |
| --- | ---: | ---: |
| a | 25/25 | 5 |
| b | 21/21 | 9 |
| c | 30/30 | 0 |
| d | 30/30 | 0 |
| e | 29/29 | 1 |
| Total | 135/135 | 15 |

The five axes give 150 possible cells. The static inventory resolves 135,
including 3 positive and 132 negative agreements. Twenty-one queries have
resolved results on all five axes. On `a` and `b`, a present explicit order
with `dependency_unresolved` remains unresolved for its applicable axes.
`c` and `d` use `nested_limits` and `explicit_representative`. For `e`, a
known floating input or exact input with a documented native statistical
binding is positive. A remaining unresolved operand type leaves the cell
unresolved. The supplementary `a0` and `corr` mechanisms are recorded in the
reviewed labels outside this five-axis agreement calculation.

## Cases that clarify the analyzer's scope

- ClickBench Q18 has an unordered LIMIT that can change the bag. TPC-DS
  Q38 also has a LIMIT without order, applied to a scalar COUNT whose single
  row always fits. The two `top_limit` and `no_order_key` entries therefore
  cover different result semantics. [ClickBench native comparison](../pvldb-a7-typed-candidates/README.md)
- TPC-DS Q49 has six `RANK()` windows. Equal inputs to each rank receive the
  same rank, and the final order includes the projected key `(channel,item)`.
  Q39's qualified order covers the projections through its equijoins.
  The two queries account for two of the nine unresolved presentation-order
  decisions. [Per-query evidence](SQL-AUDIT.tsv)
- H2O GroupBy Q8 returns scalar top values. Equal-valued source rows yield
  the same projected values. Q9's `CORR` is a floating reduction even though
  its inputs are integers. Q2's `SUM(v1)` uses integer aggregation. [Pinned schema](SCHEMAS.json) · [DuckDB aggregates](https://duckdb.org/docs/lts/sql/functions/aggregates.html) · [DuckDB 1.4.3 correlation binding](https://raw.githubusercontent.com/duckdb/duckdb/v1.4.3/extension/core_functions/aggregate/algebraic/corr.cpp)
- ClickBench Q28's `AVG(STRLEN(URL))` uses integer accumulation, while its
  inventory operand remains unresolved. DuckDB binds the integer input of
  TPC-DS Q39's `STDDEV_SAMP` to a double accumulator. H2O Q4's floating
  average and Q6's standard deviation account for the other two positive
  `e` results. [DuckDB 1.4.3 average](https://raw.githubusercontent.com/duckdb/duckdb/v1.4.3/extension/core_functions/aggregate/algebraic/avg.cpp) · [DuckDB 1.4.3 standard deviation](https://raw.githubusercontent.com/duckdb/duckdb/v1.4.3/extension/core_functions/aggregate/algebraic/stddev.cpp)
- TPC-H Q10 and TPC-DS Q46 have possible cutoff ambiguity under their schemas.
  Their upper cutoff peer groups had size one at SF1 and SF10. For Q20, the
  generated `supplier` tables had 10,000 and 100,000 distinct non-null names
  from 10,000 and 100,000 rows, respectively. This resolves Q20's order for
  these two snapshots. [TPC-H SF1](TPCH-SF1-CUTOFFS.jsonl) · [TPC-H SF10](TPCH-SF10-CUTOFFS.jsonl) · [TPC-DS SF1](TPCDS-SF1-CUTOFFS.jsonl) · [TPC-DS SF10](TPCDS-SF10-CUTOFFS.jsonl)
