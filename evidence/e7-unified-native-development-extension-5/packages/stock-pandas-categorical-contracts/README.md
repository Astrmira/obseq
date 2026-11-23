# E5: category representation and category order are different comparators

Use the exact pinned November 2025 [NYC TLC Yellow Taxi release](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page), full 4,181,444-row PULocationID native Parquet Int32 projection. There are 260 observed zone categories, no missing IDs in this source, and no row order or logical value changes. Construct two legal dictionary layouts over the entire projection: numeric zone order versus first physical occurrence. No claim of actual model bugs, operational prevalence, or source edits.

The [Pandas categorical contract](https://pandas.pydata.org/docs/user_guide/categorical.html) separates logical labels from index codes, and, when ordered, gives semantics to category order. Native Pandas 3.1.1 tests both. An independent fixed mapping oracle verifies every native code and confirms that an ABI consumer incorrectly keeping the old dictionary would misread 4,180,250 rows (code ranks differ for 259 of 260 categories). Arrow 26.0.1 verifies the complete decoded arrays exactly equal to the original native projection, even though its dictionary-array equality rejects the codebook change.

Three distinct acceptance contracts:
- **Unordered labels, no code ABI:** both are legal and exactly equal after decoding typed labels. Native Pandas DataFrame.equals accepts; default assert_frame_equal and exact numeric mode both reject because they also check categorical internals. Disabling only the categorical check admits the simple label contract on this controlled data.
- **Unordered labels, stable code ABI:** DataFrame.equals still accepts, but raw code-plus-old-dictionary use demonstrably changes decoded identities. Bind the dictionary version/order, or supply and verify the permutation from new codes to the expected code space. A decoded scalar check cannot certify code stability.
- **Ordered categories:** same labels and the same two codebooks still yield different native categorical minima. DataFrame.equals and default strict frame assertions reject. In this installed Pandas build, disabling categorical checks alone accepts those ordered frames despite their differing observable minima. Do not apply that switch as a blanket solution where category order determines results.

The packed Arrow dictionary checks are in-memory, not a storage/I/O comparison. Explicit ordered interpretation was tested with Pandas native ordered categoricals, and the code permutation was verified on every nonnull occurrence. All option outputs in RESULTS.json relate to this exact adapter and cohort, and not to all Pandas or Arrow releases.

Replay:
```sh
set -o pipefail
sha256sum -c SHA256SUMS
PYTHONPATH=/tmp/pvl-eab-submission/e4/deps:/workspace/shared/eab-gx25/deps \
  python3 -B check.py /tmp/pvl-eab-submission/e4/inputs/2025-11.parquet | cmp - RESULTS.json
```
No source rows, dictionary contents, timing, installs, acquisitions or Git changes.
