# E5: SpecBridge's stock tie grader, tolerance matching, and exact identifiers

[SpecBridge](https://arxiv.org/abs/2611.04318) already checks tied cutoffs against the complete pool, and the [published stock function](https://github.com/Xyc-arch/specbridge-artifact/blob/a51be850a113a6b7c0ada57ad3c7806c6c3f25a4/specbridge/pd/spec/render.py#L682) accepted all 15 independently legal native SQL cutoff variants from the frozen E2 receipt. The harness verifies the upstream file digest, compiles only its unchanged grade function, and reuses it. It is a direct comparator unit run, not a fresh full run of the upstream task generator or any reported benchmark.

When a group contains approximate numeric values, admissibility is an assignment problem. At the default scalar tolerance, reference values (1, 1.0000014) and candidate values (1.0000005, 0.9999995) permit a bijection: the first candidate may match either reference, but the second can match only the first. The stock path rejects that answer, then accepts the identical group in the opposite row order. It behaves the same way at a cut group with a larger explicit pool. The pairwise fallback initially commits the flexible candidate to the constrained candidate's only partner; tolerances do not form equivalence classes. No claim follows about incidence in SpecBridge data.

For an independent reference, use [SciPy maximum bipartite matching](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.maximum_bipartite_matching.html) with the same row admissibility relation, cross-checked by literal permutations. In all 441 authored default-tolerance two-row fixtures, 199 groups have a feasible matching. Across both candidate row orders, 40 of 398 legal variants are rejected, all 40 attributable to order differences in this grid; no illegal variant is accepted in this grid. These finite counts are not a rate for any external corpus. Matching is applied to the admissibility graph, not to closeness of vectors or transitive clustering.

A separate single-row arm checks identifier representation: stock tolerance accepts native distinct integers 2^53 and 2^53+1 as approximate numeric values. Using the existing stock string comparison and declaring those values to be opaque exact text rejects the mutation, no replacement grader needed for that case. This adjustment does not turn approximate peer matching into equivalence. The claims concern explicitly declared typed output contracts; they are not a claim that the authors' intended general numeric tolerance was itself a mistake.

## Replay

Use the linked stock file at the pinned commit (file not redistributed) and [the sealed E2/E3 results](../../../submission-e-series-native-evidence/e23/result.json). The plan fixes both digests. Python with SciPy 1.17.0:

    python3 -IB check.py STOCK_RENDER_PY E23_RESULT | cmp - result.json
    python3 -IB check.py STOCK_RENDER_PY E23_RESULT --csv | cmp - cases.csv
    sha256sum -c SHA256SUMS
