# Four factorized moments for H2O Q3 association faults

The 10M-input Q3 already exhibits a same-count, same-sum swap of two right
payloads. This adds a scoped deterministic association observer that catches
that swap without constructing a second reference join. The stock benchmark
and its reported result are unchanged. The candidate is a separate DuckDB
replay exposing source-row CSV ordinals in a single-threaded, ordered scan;
the independent reference is Python's CSV parser and grouped integer sums.

For each left occurrence (i), right occurrence (j), reserve (j=0) for
no match and choose (M) greater than every right ordinal. Encode an association
as (z=Mi+j). The audit fixes a prime (p) larger than every code and every
admitted absolute multiplicity error. It compares the four exact modular sums
of (z^k), (k=0,1,2,3). If a discrepancy has support (s \\le 4) on pair codes,
the first (s) equations form an invertible Vandermonde matrix. Thus a
nonzero admitted discrepancy changes at least one moment. For the tested
rectangle exchange, the count and linear moment cancel; the quadratic
difference is (2M(i-i')(j'-j)) with the orientation used by the test,
and is nonzero. Across all 10,000,000 output associations, the clean replay
matches all four independent moments. The exchange preserves the exact sum of
each projected value column and shifts the quadratic moment by −129,512,954.

Group each input by the join key. The binomial expansion of ((Mi+j)^k)
lets the reference multiply the left and right per-group power sums, not
enumerate pairs. For an unmatched left group use the singleton (j=0).
SQL equality treats the left null group the same way; null-safe equality
would require a separate contract. This particular right input is unique and
nonnull on the join key (checked from the file); the formula also applies to
many-to-many groups using a power sum over all right occurrences. The input
reference reads each source once after digest verification, and the candidate
still needs to be read. No runtime or speedup is claimed.

Payload identities are not authenticated just by attaching IDs. The native
one-micro-unit mutation keeps all four moments while changing a value. The
fixture uses a clean value comparison as a positive control, not a general
payload witness. Reserve exact typed payload binding, dual EXCEPT ALL, or an
equivalent exact oracle for a full result claim. A five-code signed
multiplicity difference shows why the four outputs cannot cover every fault:
its first four moments vanish and its fifth does not. This is an abstract
boundary witness, not a claim of five mistakes in the real Q3 run. A deliberately
mis-encoded unmatched sentinel is also detected, but affects too many
positions to rely on the sparse theorem. A reversed partition merge checks
order insensitivity without pretending to re-sort the underlying CSV.

The technique uses existing [factorized aggregation](https://arxiv.org/abs/1307.0441)
and the same [Vandermonde principle as Reed–Solomon checks](https://flintlib.org/doc/tutorials/algebra/reed-solomon.html).
The contribution here is operational: exact inputs and a live counterexample
that the publisher-style sums missed, plus the observer's admission and failure
boundaries. See the [benchmark definition](https://duckdb.org/2023/04/14/h2oai)
and prior original-input Q3 evidence.

Run `python run.py <admitted-10M-generator-output-directory>` with DuckDB
2.0.1 Python bindings, then compare the JSON with `RESULT.json`. The pinned
file hashes, code bound, sentinel count, equal exact DECIMAL stock sums, and
same-moment negative controls are executable assertions. See full 10M stock
Join execution
for the unchanged queries. No 5GB run or benchmark performance is inferred.
