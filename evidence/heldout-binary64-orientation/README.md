# E7 O4: independently sealed binary64 orientation distinctions

A fresh author sealed 24 six-coordinate decimal-string inputs and exact
dyadic sign labels without seeing any adapter output. The executor
froze every GEOS, naive, certified, and exact-decimal prediction at
2026-11-21 22:01:54 UTC before opening the labels. This is not the
previous known cancellation stress panel
and not any earlier holdout.

The target is the sign of the exact value of the determinant after
rounding the input tokens to binary64, not after preserving the exact
decimal string. The frozen bounded grid is as stated in PROTOCOL.md.
Certified orientation with the [published orient2d initial bound](https://www.cs.cmu.edu/~quake/robust.html)
uses a dyadic fallback when the rounded sign is not certified. The
stock comparison is [native GEOSOrientationIndex_r](https://libgeos.org/doxygen/geos__c_8h.html)
in GEOS 3.13.1; plain float uses ordinary binary64 subtraction and
multiplication. Exact decimal arithmetic is a separate contract
comparison, not a failing floating implementation.

All 24 certified results match, with 14 fallbacks. Stock GEOS and
plain float both happen to match all 24. Seven negatives, seven zeros
and ten positives were sealed. Preserving the decimal values instead
changes four answers. Neither the fallbacks nor the four different
contracts are native failures. The zero plain errors here do not
contradict the explicitly authored prior 200 mismatching cases, and
do not establish that the plain predicate is exact in general.
No population estimate or geographic orientation claim.

    set -o pipefail
    sha256sum -c SHA256SUMS
    python3 -IB run.py CASES.json | cmp - PREDICTIONS.json
    python3 -IB score.py | cmp - RESULT.json

Use the already installed named GEOS native library. All fixtures,
descriptions and labels are authored. No source geometry distributed.
