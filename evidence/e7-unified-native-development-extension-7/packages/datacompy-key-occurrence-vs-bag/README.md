# E5: DataComPy occurrence pairing is not a keyed bag comparison

Use the first 2,048 rows of the pinned original H2O left CSV with a
defined id1; inspect only small exact integers id1/id2/id3 and
nullable payloads. This produces ten repeated group keys. Content
is benchmark-generated; no raw rows are included. Fix the intended
relation to an order-independent, NULL-safe **whole-row multiset**
with multiplicity. Source selection is deterministic, not sampling
failure prevalence.

Stock DataComPy 0.16.8 Compare(join_columns=['g']).matches() with
Pandas 2.2.3 accepts the unchanged positive control but rejects
three exactly equivalent reorders: global reverse, per-group rotate,
and a reverse with authored duplicate occurrences. The installed
[DataComPy 0.16.8 implementation](https://github.com/capitalone/datacompy/blob/v0.16.8/datacompy/core.py)
adds a within-join-key occurrence ordinal when duplicates exist; the
compared row matching can therefore depend on source occurrence order.
That is a mismatch to this experiment's declared bag contract,
not an allegation about its supported row-order contract.

On the admitted nullable Int64 domain, canonicalize each input by a
stable full tuple sort (group, field A, field B; NULL first), then
apply the same stock operation. All four legal cases pass. Three
separate bad cases are still rejected: a within-key field-only
swap preserving marginals, replacement of one exact duplicate by
another with row count unchanged, and a missing duplicate. An
independent Python tuple Counter and native DuckDB typed EXCEPT ALL
in both directions agree exactly on all seven cases, including
multiplicities and the nullable fields.

Full tuple normalization is the correct shape-preserving way to give
the occurrence comparator the same sequence for equal admitted bags.
It does not fix a lossy value/type comparison, a mismatched join domain,
or an input contract allowing multiple valid outputs. The admitted
integers are far below binary64's consecutive exact integer limit.
If value equivalence or declared types differ, establish admission
before either starting comparator. No runtime or production claims.

    set -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B run.py PINNED_H2O_LEFT_CSV | cmp - RESULT.json

Uses the three already-installed named runtimes, DuckDB 1.4.3.
