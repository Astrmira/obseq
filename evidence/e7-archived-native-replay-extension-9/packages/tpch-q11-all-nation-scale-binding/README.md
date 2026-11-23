# EA&B: the SF10 Q11 qualification/workload difference holds for all 25 nations

The [TPC-H 3.0.1 specification §2.4.11](https://www.tpc.org/TPC_Documents_Current_Versions/pdf/TPC-H_v3.0.1.pdf#page=47) distinguishes runtime fraction 0.0001/SF from the fixed qualification sample's 0.0001. On the complete SHA-identified native DuckDB-generated SF10 input, the earlier stock Q11 audit showed the bundled qualification fraction silently produces no rows for Germany, while the scale-bound workload produces 8,685. That finding is not particular to the qualification nation.

On the same 8-table SF10 cohort, substitute all **25 allowed nation values** in the digest-verified Q11 body. The fraction is the only other substitution; do not alter joins, ordering, decimal expressions, scale, or selection. This is a census of SQL parameter settings on one fixed generated input, not a performance benchmark, engine bug, or official TPC compliance run.

- **25/25** queries at fraction 1/10,000 give an empty result.
- **25/25** corresponding queries at SF10 workload fraction 1/100,000 are nonempty, with **8,406 to 10,364 rows** each.
- Across the 25 scale-bound outputs, there are **234,669 nation/part memberships**. Their score order allows ties because Q11 does not specify a secondary key; 33 entries are in excess of per-nation distinct score counts.
- The maximum over all nations of the richest single part's share is **573376495/15987281108891 ≈ 3.58645×10⁻⁵**, well below the qualifier's 10⁻⁴. An empty output is therefore exact for the unscaled literal, not a numerical or engine failure.

For each nation, a separately written exact integer-cents group computation and Python summation replace the original query's repeated decimal aggregation and threshold comparison. The keyed bags of all 50 native SQL results match the reference, without inventing any peer order. The Germany result has additionally been independently audited by the prior Python source accumulation. This repeatable output should identify the scale and both parameters, not just the query number. Applying the qualification literal across all permitted names cannot reveal the nonempty runtime behavior on this generated scale.

Use the linked Q11/Q21 replay ingredients: hash-pinned DuckDB 1.4.3 and signed TPCH extension, complete SF10 DB and table-count receipt. The query bytes come from the signed extension and their digest must match. Set E to the directory with input/duck143 and input/ext143/tpch.duckdb_extension; set W to the writable scratch containing tpch.duckdb. SQL, corpus and raw answer keys are not bundled.

    set -o pipefail
    sha256sum -c SHA256SUMS
    python -IB check.py "$E" "$W" | cmp - result.json
