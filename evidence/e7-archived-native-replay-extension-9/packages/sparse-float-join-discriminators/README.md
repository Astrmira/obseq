# EA&B: exact equality-join repair for a certified finite lossy-key domain

The ClickBench precision audit showed that a direct binary64 cast can change almost every integer's value while creating no key collisions in one fixed partition. The public TweetIDs control has an actual two-key collision. This packet constructs and natively verifies the precise join repair for either case without asserting that the rounded scalar preserves its original value.

For an externally admitted finite exact key domain S, let b(x) be the canonical binary64 image. Both sides start with exact x, and use the same cast and the same versioned classifier before losing precision. For each non-singleton fiber S_b, assign its members canonical different ranks (here the integer ordering within that fiber). The emitted comparison token is (b(x), rank(x)), with implicit rank zero in singleton fibers. Equality of these tokens is then equivalent to exact integer equality in S, so pair IDs and multiplicities in any equality join of admitted rows are unchanged. Preserve a separate typed NULL state in accordance with a declared NULL policy; the experiment deliberately uses NULL-safe equality. A one-side round-trip without such a shared comparison domain is a different contract.

Within one m-key collision class, any fixed-width discriminator supporting arbitrary same-domain recombinations must distinguish all m keys: shared tags for two distinct keys would falsely match in a one-row cross-side query. Hence ceiling(log2(m)) conditional bits suffice and are necessary in that narrow uniform per-class field model. This is not a lower bound for compression, globally learned side information, or a single fixed pair of relations (known disjoint classes can instead be skipped). The bits are conditional on an already available trusted classifier and omit the class catalog, sparse routing positions, codec/file overhead and producer work. Stock execution uses an explicit native integer tag column, **not** a claim of a four-bit storage format. This is ordinary conditional dictionary coding, related to the [Arrow dictionary index contract](https://arrow.apache.org/docs/format/Columnar.html#dictionary-encoded-layout), applied to a known cast loss rather than a new encoding primitive.

## Native checks on pinned public cohorts

Use three unchanged [COVID-19 TweetIDs collection](https://publichealth.jmir.org/2020/2/e19273/) hours from its published commit 2fe736f409ffe51d3f115ba4fc3b8dc3da1213d9, and one unchanged [ClickBench publisher partition](https://datasets.clickhouse.com/hits_compatible/athena_partitioned/hits_0.parquet). NumPy/PyArrow supply native typed materialization. Plain Python integer ties-to-even gives an independent oracle for binary64 bucket membership. DuckDB 2.0.1 uses native INT64/DOUBLE joins, compares exact IDs in each direction of the membership difference, and also reruns the repaired join from a relation that has no original integer column at all. Per-key multiplicities represent the same native pairs without materializing 16 million duplicates. TweetIDs additionally verify every resulting key pair directly. No literal IDs, hash table, raw data, or case-specific discriminator map is distributed.

| Frozen split | Exact pairs incl. one authored NULL pair | Both-cast pairs | With shared rank | Conditional discriminator bits over source occurrences on both sides |
|---|---:|---:|---:|---:|
| TweetIDs self | 22,744 | 22,746 | 22,744 | 4 |
| TweetIDs integer-order parity | 1 | 2 | 1 | 2 |
| ClickBench UserID original-ordinal parity | 16,818,333 | 16,818,333 | 16,818,333 | 0 |

The sidecar is prospective: if both original exact keys or the tag are already lost within a collision class, these two experiments do not make them recoverable. Expanding the domain or changing source identity/cast version may require regenerating tags. Never accept unexpected new members silently. No range/sorting arithmetic, source authenticity, universal engine guarantee, traffic prevalence, or latency claim.

Replay with DuckDB 2.0.1, PyArrow 26.0.1 and NumPy 2.5.5; retrieve only unchanged input files from the pinned public references and verify the exact hashes:

    set -o pipefail
    sha256sum -c SHA256SUMS
    python -B check.py /path/to/three/tweet-id/files /path/to/hits_0.parquet | cmp - result.json
