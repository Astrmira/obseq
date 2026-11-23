# E5: stock DVC checks byte identity, not keyed semantic equality

Run [official DVC 3.66.1](https://pypi.org/project/dvc/3.66.1/) without SCM or configured remote, on independently sealed and already scored [24 keyed F7 cases](../../../heldout-keyed-aggregate-cancellation/README.md). Each of the 48 native `dvc add` operations tracks one source/candidate JSONL byte string using the same format and requested order. Read the native YAML pointer and verify its recorded size and MD5 independently. This is native version management and correctly distinguishes bytes; its physical equality answer is put beside the named unordered keyed-data contract, not presented as a DVC defect.

Byte equality accepts 2 of 12 legal unordered cases and rejects all 12 illegal cases. The other 10 legal key-preserving rearrangements have distinct physical fingerprints. No claim to exhaust DVC configuration, cryptographic adversarial cases, lakeFS behavior, or wide pipeline semantics. This is the same panel used in the separately published common native-tool comparisons, not a fresh blind corpus. Official PyPI dependencies were isolated in scratch, no global package/environment changes, telemetry disabled, no configured network remote, and no packages included in the artifact. Exact release archive hashes are in DEPENDENCY-LOCK.json.

    set -e -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B check.py PINNED_CASES PINNED_LABELS DVC_SITE SCRATCH_DIR | cmp - RESULT.json
