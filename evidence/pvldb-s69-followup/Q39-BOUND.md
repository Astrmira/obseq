# An a priori bound for the SF10 Q39 inventory groups

This certificate covers the one- and four-thread executions of the stock Q39
from DuckDB 1.4.3 (commit `d1dc88f950`). The query computes the sample standard
deviation of an integer quantity, divides by its integer-input average, and
filters each month on `CV > 1` before joining January and February. See the
[aggregate update, merge and finalization](https://github.com/duckdb/duckdb/blob/v1.4.3/extension/core_functions/include/core_functions/aggregate/algebraic/stddev.hpp)
and [integer AVG](https://github.com/duckdb/duckdb/blob/v1.4.3/extension/core_functions/aggregate/algebraic/avg.cpp).
The proof uses the input integers and source operations. Native output residuals
do not enter its calculation.

Let a nonempty group have size `n`, sum `S`, sum of squares `Q`, minimum
`m` and maximum `X`. Put `R = X - m`, `M2 = (n Q - S²)/n`, and let
`u = 2⁻⁵³` be the binary64 unit roundoff. Inputs are nonnegative integers.
The checker verifies the small-count and magnitude conditions used below.
All operands fit far below overflow. In the mean induction below, a subset
with positive sum has delivered mean at least `1/(2n) ≥ 2⁻¹⁷`, and an
all-zero subset has exact mean zero. Nonzero differences between these
binary64 means or integer inputs are thus at least `2⁻⁶⁹` before rounding.
The corrections square or multiply at most two of those differences, with
count factors bounded by `2¹⁶`. Their floating sums cannot introduce a
nonzero quantity below the grid of the summands. The rounded divisions,
products and square root involved are well within the normal range.
A one-element group has NULL sample deviation. A zero-mean group
fails the query predicate. In a nonzero constant group the updates and merges
have zero mean differences and zero second moment exactly.

## Mean error in the running state

Represent the computation as a binary tree of disjoint subsets. A sequential
update is a merge with a singleton; an empty-state copy adds no error. At a
node with child sizes `a,b`, `k = a+b`, the ideal merged mean is an affine
blend with weight `b/k`. With the delivered child means held fixed, either
the rounded difference, divide and add in the singleton update, or the
rounded difference and ratio followed by the explicit FMA in combine, perturbs
that blend by at most `12uX`. In detail, the child means are at most `2X`
in magnitude and their difference is at most `2X` under the invariant
below. The two roundings before the final addition or FMA contribute at most
`6uX` and the final rounding at most `3uX`. The same bound allows a
contracted add/multiply with fewer roundings. Since the blend is convex,
induction bounds each delivered subset mean error by `12(k-1)uX`.
The checked condition `48n²uX < 1` gives a group-wide mean error below
`1/(4n)`, hence below `R/4` for `R ≥ 1` and below `X/4`.

## Second moment error for any merge tree

The exact local second moment correction is `w δ²`, where `δ` is the
difference of the exact child means and `w = ab/k`. The sum of these
nonnegative corrections over the tree equals `M2`. With the delivered
means substituted, their exact difference lies within `12(k-2)uX` of
`δ`, and its magnitude is at most `2R`. The substitution therefore
perturbs the correction by at most `36 w k u X R`.

- In a merge, rounding the difference twice in the error product, its
  square, the two count multiplications and the division contributes at
  most `8u` times the correction evaluated at the delivered child means,
  which is at most `32u w R²`.
- In a singleton update, the exact correction for the delivered inputs
  equals the product of the old and ideal-new mean differences. The computed
  new mean contributes at most `24u X R` to that product. The two
  subtractions and multiplication contribute at most `24u R²`, using
  `|δ| ≤ 2R` for the delivered difference and `12uX ≤ R` for the new-mean
  error. This bound also allows a fused final product and addition.

The sum of `wk = ab` over the tree is `n(n-1)/2`, because each unordered
leaf pair belongs to exactly one split. Also `w ≤ k/4 ≤ n/4`. Thus the sum
of absolute local correction errors is at most `u L`, where

    L = (18 X R + 8 R²) n (n-1) + 24 (n-1) (X R + R²).

Each correction reaches the output through at most `2(n-1)` rounded
additions. The accumulated summation error is at most
`4nu (M2 + u L)`, by bounding the product of rounding factors along
each path. The resulting relative error in the second moment is at most

    ε = 2u L / M2 + 4nu.

## Output and predicate bounds

Integer AVG accumulates an exact sum. With these counts and values, the sum
and count conversions are exact. A widened division and conversion to
binary64 contribute at most `3u` relative error. For the CV, the division
by `n-1`, square root, and division by the delivered mean give a combined
relative bound of `2ε + 16u` for `ε ≤ 1/4`. For example, the variance
division has relative perturbation at most `ε + 2u`, and square root
contracts it by a factor at most one before its own rounding. Moving the
mean error into the denominator introduces at most `4u` and both division
and square-root rounding are covered by the remaining allowance. The
query's `1.000` multiplier converts exactly to binary64 one.

The shipped verifier computes the resulting radius `B = 2ε + 16u` as a
rational and compares the exact squared endpoints
`CV²(1-B)²` and `CV²(1+B)²` with one using integer arithmetic. It also
checks both archived projected means and CVs and reapplies the three
negative controls from the original CWI comparison. The separate 2 ULP
receipt is the maximum **observed** numerical deviation of those archived
native arms. The analytic bound is scoped to the fixed inventory workload
and engine operations above.
