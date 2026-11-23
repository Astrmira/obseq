# E7 archived native replay extension 8 (add-only)

Ten previously uncounted archive packages ran against their original release receipts and matched bytes: two authored controls and eight scoped external-transfer packages. Prior 76 are carried forward without rerunning them. Cumulative total: 86 actual (55 authored, 31 scoped transfer), plus one prior receipt-only. The independent 108 are separate. Two additional exact local passes were held in reserve, not included. See SCOPE.tsv for exclusions, scope overlap and corrected runtime bindings.

External transfers reuse a few inputs intentionally: TweetIDs widths across separate comparator languages, HVFHV fold durations versus three-event order, and distinct ClickBench native operations. They are not independent data samples. TweetIDs originate from three already-local original source objects pinned by TWEET-COMMIT.txt and per-case INPUTS.sha256; raw inputs are not distributed. No downloads, new data generation, macros or Calc runs. Polars cent-contract portability is not counted separately from a near-identical local variant. Archive file hashes pin source content; the report is not a trace of all 117 inventoried candidates.

    set -o pipefail
    sha256sum -c SHA256SUMS
    python3 -IB replay.py --inputs INPUT-ROLES.example.json | cmp - NEW-REPLAY.tsv

The input map points at local existing source files and pinned dependency sites. Set equivalent absolute paths on another machine; current prior source scripts may retain legacy absolute policy paths. The selector checks every loaded file against the original manifest. Omit IDs to run this delta, or select any subset by ID. To replay the entire sequence, add --include-prior and --prior-root for each unpacked pinned original replay and extensions 4, 5, 6, and 7. BASE-PINS.json and MANIFEST.json bind the published prior root and original source commit separately.
