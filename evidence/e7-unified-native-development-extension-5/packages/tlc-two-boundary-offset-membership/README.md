# E2/E3: projected membership for two independently tied OFFSET boundaries

A single projected pool is insufficient when OFFSET skips part of one peer band and LIMIT ends inside a later band. Two independently constrained peer slices can produce overlapping projected values, so the same visible tuple may witness either boundary, but one occurrence cannot pay both quotas. Exact bag membership requires only per-value integer intervals, without enumerating physical witnesses.

Let A(v), B(v) be the projected multiplicities of two distinct boundary bands and M be the bag of all mandatory middle rows. Let l and r be the two boundary quotas. For a proposed bag N require M≤N and let x=N−M. Require Σx=l+r. Assign t(v) of its occurrences of value v to the first boundary. Exact membership holds if and only if, for every v, the intervals

    max(0, x(v)−B(v)) ≤ t(v) ≤ min(x(v), A(v))

are nonempty, and the sums of lower and upper endpoints bracket l. The condition is sufficient because sums of integer intervals contain every integer between their endpoints, and source occurrences from distinct bands are independent. Equal score bins collapse to a single selected quota, which is outside the two-band test here. This checks the declared projected **bag**, not source identity or a list whose boundary score positions must remain visible.

Related work distinguishes per-snapshot membership from query equivalence: [FormalSQL in Logos](https://arxiv.org/html/2608.15709v1) models all legal lists and their bag images for comparing full query outcome relations, while [LASSO §5](https://arxiv.org/html/2610.38294v1) describes deterministic sorting refinements for reproducible execution comparison. The controls here apply an explicit secondary physical order as one legal refinement, not a run or assessment of either of those full systems. The result below is for an already admitted source with one defined observation contract.

## Native and exact controls

The source is the [NYC TLC public November 2025 yellow taxi](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) Parquet with 4,181,444 rows. The predeclared 16 query cells use distinct partially selected pickup-minute bands and project only dropoff location. Timestamp semantics are the stored zone-free civil value and binary minute order. Use native DuckDB 2.0.1 for the stock query shape and two opposite explicit physical-ID refinements; use PyArrow 26.0.1 for a separately read exact source bag. This is an authored workload on the original input, not vendor stock TLC SQL, a count of naturally emerging nondeterminism, or a claim about timezone localization.

- All **48** native query results pass. The opposite legal refinements produce different projected bags in **all 16** cells, so one refined golden would reject another legal result even at projected-bag level.
- All **128** prospectively specified physical quota shifts by one source occurrence also project to legal bags. There is no projected-contract failure to detect in those controls. A physical-origin contract would answer a different question.
- A separately recorded deterministic extremal test constructs two pooled-admissible bags per cell by maximizing the number of occurrences forced into each band. All **32** pass the length, mandatory bag and pooled per-value capacity observer but violate at least one boundary quota and are rejected by the interval check. The forced-band excess at these extrema ranges from 22 to 33 occurrences. These are authored feasibility witnesses, not native errors or prevalence estimates.
- A tiny literal enumerator independently checks **963** finite projected candidate bags against subset selection.

Use the pinned source and named engine versions. Bytes, including authored candidate values, remain local. The pre-execution receipts bind both the original prospective case and the separately motivated extreme-control amendment.

    set -e -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B check.py /path/to/2025-11.parquet | cmp - RESULT.json
    python3 -B stress.py /path/to/2025-11.parquet | cmp - STRESS.json
