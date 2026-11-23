# E3 F8: aggregate UTC transition counts require joint feasibility

Input: the exact retained [NYC TLC November 2025 Yellow Taxi data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page), with the prior pinned America/New_York TZIF, verified by SHA. Among all 4,181,444 source records, keep the same prospective cohort as the prior endpoint study: both recorded naive pickup/dropoff timestamps must be inside November, at least one in the repeated civil hour. These 14,326 selected records do not represent all trips. Assume only source-zone interpretation and physically ordered pickup≤dropoff. No claim to true source instants, travel-time accuracy or population error rates.

The previous endpoint support result identifies valid individual interpretations. This downstream contract asks whether a **published pair of integer event counts** is attainable jointly: P = pickups before the UTC transition, D = dropoffs before it. The exact cut is 2025-11-02 06:00 UTC, verified from the pinned rule. In any ordered assignment each record is either A=(both at/after cut), B=(crosses from before to at/after), or C=(both before). The opposite crossing is impossible and the proposed category counts are (N−P,P−D,D). For each original row use its admissible category set after native wall-time round trips and exact pair order, not independent per-endpoint defaults.

| Admitted category support | Records |
|---|---:|
| B only | 1,431 |
| A or B | 934 |
| B or C | 2,639 |
| A, B, or C | 9,322 |

For any category subset T, its claimed allocation cannot exceed the number of records with at least one admissible category in T. These inequalities and total N are sufficient, by the integral bipartite matching criterion on allocating each incident record to one unit of quota. With precisely three categories, singleton inequalities are upper bounds and paired inequalities are equivalent to lower bounds on the complement. Thus three individual category lower/upper pairs plus quota conservation suffice; there is no product-enumeration cost. Verify the criterion independently on 1,992 authored quota vectors against literal assignment enumeration.

| Statistic | Sharp possible range |
|---|---:|
| P | 4,070–14,326 |
| D | 0–11,961 |
| P−D | 1,431–14,326 |

Requiring endpoint marginals and P≥D permits 91,556,348 distinct integer count pairs. Joint feasibility admits 79,239,731, removing 12,316,617 product/order-plausible pairs. These are mathematical count vectors, not data quality incidence. At D=11,961, P=13,391 is impossible but P=13,392 is attainable, a difference of one forced crossing. Stock native endpoint-by-endpoint default infers crossing count 2,639, which is legal in isolation, yet its pickup-before count 2,639 violates the jointly derived minimum 4,070. The same defaults produce 1,431 individually unordered assignments. This is scoped output under declared timing semantics, not an engine defect claim.

Native DuckDB 2.0.1 [timezone localization](https://duckdb.org/docs/stable/sql/functions/timestamptz) with exact two-fold counterfactuals and reverse wall-time validation is checked against Arrow 26.0.1 and Python ZoneInfo for every selected physical source row. The two implementations match category support, default projected events and row-level admissibility. No raw rows exported. Reuse this certificate only for the same invariant cohort, cut, rules and paired role semantics; multiple cuts, extra constraints or independently observed runtime truth are not covered.

Replay:
```sh
set -o pipefail
sha256sum -c SHA256SUMS
PYTHONPATH=/tmp/pvl-eab-submission/e4/deps python3 -B check.py \
  /tmp/pvl-eab-submission/e4/inputs/2025-11.parquet \
  /tmp/project-eab-dbt-freshness/deps/pytz/zoneinfo/America/New_York | cmp - RESULTS.json
```
No data acquisition, performance measurement, or Git writes.
