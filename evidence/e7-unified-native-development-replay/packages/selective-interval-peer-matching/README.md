# Exact approximate-peer verification by interval indexing and stock matching

The stock SpecBridge counterexample is a false rejection caused by choosing the wrong valid partner for a tied row. A general bipartite graph correctly handles the ambiguity, but all-pairs construction may erase its practicality. This packet applies ordinary interval lookup and [SciPy maximum bipartite matching](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.maximum_bipartite_matching.html) instead of building a new general matching implementation. Algorithmic predecessor for the one-dimensional case is [Glover's convex matching](https://doi.org/10.1002/nav.3800140304).

## Contract

Rows have an exact composite identifier (possibly empty), and d finite numeric columns with declared nonnegative absolute tolerances a and relative tolerances 0≤r<1. A column accepts pair (x,y) iff |x−y|≤max(a,r max(|x|,|y|)). This packet represents the declared numbers exactly as rationals; it does not promise identical behavior to a binary-floating implementation at roundoff boundaries. NaN, missing values, decimal quantization contracts, and changes of coordinates are outside this model unless first given explicit separate semantics. Duplicate source rows have distinct indexed capacity. A complete group requires a bijection; a cutoff candidate may inject into its larger allowed pool. Exact keys and group boundaries are not approximated.

## One approximate dimension

For x≥0 the relative admissible interval is [(1−r)x,x/(1−r)], and for x<0 reverse the factors. Opposite nonzero signs cannot meet the relative bound if r<1. The absolute and relative intervals both contain x, so their union has endpoints min of the lower bounds and max of the upper. Both endpoints are nondecreasing in x. Sort the source pool and the candidate scalars within their exact key. In the order of increasing candidate, discard unused source values below its lower endpoint, then match to the first unused value inside its interval or reject. A discarded value cannot help any later candidate. In an existing full matching for the suffix, if the earliest possible value v is assigned later and current candidate uses w≥v, swapping v and w preserves eligibility: the later lower endpoint is ≤v≤w and its upper endpoint is ≥ the current upper endpoint ≥w. If v is unused, replace w directly. Thus this scalar case costs sorting plus a linear sweep, without constructing a dense bipartite graph.

## Several approximate dimensions

Separate per-column matchings are not sufficient. With reference {(0,0),(2,2)} and candidate {(0,2),(2,0)}, both individual columns match exactly and no row pair matches. The same source row must meet all constraints.

For each exact key, sort its source rows independently by each approximate column, retaining original row indices. For a candidate row, count possible partners in each exact window by two binary searches. Use its shortest window, and test all the other columns only within that window. A true partner belongs to every window and cannot be missed; any retained edge has been checked against all windows. Run sparse maximum matching on precisely the remaining adjacency. Since pivot choice is per row, it adapts when different columns disambiguate different parts of a tied group. With m pool rows, n candidate rows and d columns, pre-match work is O(dm log m+dn log m+dΣ_i min_j W_ij), where W_ij is the exact window count and memory is O(dm+E+n). This is not a uniform subquadratic claim: E can still be quadratic where admissible rows are truly dense.

## Reproducible controls

450 signed rational authored cases compare adaptive sparse admission versus an independent true dense graph; 21 also compare literal injections. 1,156 scalar cases and 19,196 interval predicate calls verify the closed-boundary exact criterion. A predeclared 20,000-row two-axis fixture alternates which dimension separates rows. It has 400,000,000 all-pairs possibilities, 100,010,000 candidates on the best global axis, and 20,000 candidates with the row-adaptive pivot; all 20,000 form the exact perfect matching. These are operation counts in an authored fixture, not latency, production prevalence, or a new general matching algorithm.

Replay with Python and SciPy 1.17.0:

    python3 -IB check.py | cmp - result.json
    sha256sum -c SHA256SUMS
