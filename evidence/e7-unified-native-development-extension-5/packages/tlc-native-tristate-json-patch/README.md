# E3 F5: JSON patch intent is not implied by a nullable scalar read

The declared output always contains `passenger_count` with a nullable integer: omitted patch means KEEP, explicit CLEAR means set to a present JSON null, and WRITE supplies an integer. That presence contract is intentionally different from [RFC 7396 JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396.html), where a patch member with null deletes the target member. [Stock SQLite json_patch](https://www.sqlite.org/json1.html#the_json_patch_function) explicitly follows that convention. We measure the consequences of applying a mismatched convention, not a defect in Merge Patch.

Use the full intact [NYC TLC November 2025 Yellow Taxi Parquet](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page). To make an authored intervention stream without inventing new measurement values, pair each source count with its physical predecessor as the existing value (4,181,443 pairs). Source NULL constructs no supplied patch member, numeric zero constructs explicit CLEAR, and the rest supplies WRITE. This does not assert that the publisher uses these policies or that paired physical rows are revisions of the same trip.

| Native transformation | Incorrect presence or value | Incorrect nullable scalar |
|---|---:|---:|
| Explicit typed KEEP/CLEAR/WRITE assignment | 0 | 0 |
| Merge Patch with correctly omitted KEEP members | 19,942 | 0 |
| Serialize omitted KEEP as explicit null, then Merge Patch | 1,034,682 | 1 |
| Fallback to the old value with COALESCE | 19,942 | 19,942 |

The full stream has 1,014,740 KEEP, 19,942 CLEAR, and 3,146,761 WRITE rows. Under the first Merge Patch mismatch, every explicit CLEAR becomes absent while its extracted scalar remains NULL. Under omission coercion, just one missing-source row follows a nonmissing predecessor: a scalar check misses all other unintended deletions even though target membership changes. This is why visible end state and field identity both have to match the declared contract; it does not estimate spontaneous failure in a deployed patch service.

The full cohort executes native DuckDB JSON functions against an independent exact PyArrow projected oracle. Native SQLite matches the exact oracle on a prespecified first-4,096 pair check and a separately sealed first-KEEP-boundary 12-pair control. The former has 48 explicit clears and no KEEP; the latter has eight KEEP including the one scalar-visible omission. Neither comparison requires recursive patches, duplicated object keys, ordered JSON documents, or non-integral values.

    set -e -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B check.py /path/to/2025-11.parquet | cmp - RESULT.json
    python3 -B keep_boundary.py /path/to/2025-11.parquet | cmp - BOUNDARY.json

No trips or raw JSON documents are distributed.
