# E7 archived native replay extension 10 (add-only)

Six distinct archived packages actually executed: four byte-identical native results and two matching deterministic semantic projections. The prior 94 fresh executions are not rerun; cumulative 100 actual (58 authored development, 42 scoped transfer) plus one separate old receipt-only. Of the 100 actual, 98 are full byte-identical receipts and two match deterministic semantics after excluding specifically listed nondeterministic diagnostics. The original independent 108 remain a separate cohort. Frozen E3 Census and OSM package replays are cross-listed transfer cases, not new E3 findings or newly authored development fixtures. The overlapping H2O stock projection replay passed but is not counted again.

For actual GEOS wedges and native Q39, the two fresh aggregate outputs are included in observed/. Timing and RSS are excluded from the orientation comparison, not recomputed in analysis. Q39 retains exact threshold and cardinality checks plus the full single-thread semantic receipt, while permitting specified four-thread roundoff diagnostics to vary within the observed bound. See SCOPE.tsv. The official lakeFS/lakectl release ran with loopback, telemetry/version/audit traffic disabled, private temporary metadata and fixed archive/binary hashes. Use the official local archive with SHA-256 dc02b075ddcbb0984f96f6be2e0e08d74bd0967920ec89dd00a97b5d400ad8eb to extract the two binaries into an owned path specified as LAKE_BIN. The selector checks both binaries' digests before running; binaries are not distributed.

    set -o pipefail
    sha256sum -c SHA256SUMS
    python3 -IB replay.py --inputs INPUT-ROLES.example.json | cmp - NEW-REPLAY.tsv

Set absolute local paths for pinned sources and existing dependencies. Run any subset by exact case ID. Add --include-prior with all published --prior-root directories (initial unified replay, extensions 4–9; seven roots total) for all prior and current packages. Prior manifests, original Git blob IDs, and SHA-256 contents are verified. No new source downloads, generators, macros, or Calc reruns. The 100 package IDs do not imply 100 independent datasets or completion of the larger inventory.

With the pinned roots present as sibling folders in the research branch
checkout, there is a single-command full adapter entrypoint:

    python3 -IB replay-all.py --inputs YOUR_ABSOLUTE_INPUT_BINDINGS.json

This invocation covers the 100 executable packages and one distinct
receipt-only archive entry listed in REPLAY.tsv. The wrapper verifies
the seven sibling manifests before invocation. See check.py for the
offline inventory/receipt crosscheck; that is not an additional native
execution.
