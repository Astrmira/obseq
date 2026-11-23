# EA&B × Arrow: a presence-and-type carrier across native Parquet VARIANT

**Result.** Native DuckDB 2.0.1 forwards a key's operation through a narrow projection using `variant_exists` plus a guarded child tag and typed value, from **actually unshredded** and integer-shredded native Parquet VARIANT. This does not reconstruct whole-object JSON in the SQL projection. Independent stock PyArrow 22.0.0 and 26.0.1 readers recover the same operations from two selected raw leaves and their ancestor validity in the shredded file. PyArrow 19.0.1 cleanly rejects both honest file annotations before decoding data. That is a pinned reader boundary, not a claim about Arrow Rust, Spark, or all Arrow readers.

This extends the previous native Parquet VARIANT packet, which used whole-object reconstruction for the positive result, and the E3 TLC merge-patch oracle, which establishes why field intent matters. No TLC sample was rerun.

## Native witness and independent projection

DuckDB `v2.0.1` source ID `8d78114e90` natively creates both files. `COPY … SHREDDING {'v':'VARIANT'}` is confirmed by both newer Arrow readers to write a `Variant(1)` group with required `metadata` and `value` only, **no** `typed_value`. `SHREDDING {'v':'STRUCT(k INTEGER)'}` writes a true INT32 child with native VARIANT fallback. Merely omitting the option is not an unshredded control; the local build auto-selected a shredding schema even on tiny exploratory inputs. See the [DuckDB VARIANT documentation](https://duckdb.org/docs/2.0/sql/data_types/variant) and the [v2.0.1 COPY option source](https://github.com/duckdb/duckdb/blob/v2.0.1/extension/parquet/parquet_extension.cpp#L217-L262).

For the same admitted source rows, PyArrow's explicit nested selection of `v.typed_value.k.value` and `v.typed_value.k.typed_value` (plus row ID) produces the following. Parent and nested-group validity are retained with the selected columns.

| Authored row | Selected raw signal | Operation for `k` |
|---|---|---|
| Outer SQL NULL | Outer struct null | No patch event (this protocol) |
| Object `{}` | Object group valid; both children null | Keep |
| Object `{"k":null}` | Raw child `00`; typed child null | Delete key |
| Object `{"k":0}` created with native INT32 | Raw child null; typed child integer 0 | Set numeric zero |
| Object `{"k":"0"}` | Raw child `05 30`; typed child null | Set the string `"0"` |
| Valid scalar root `23` | Outer struct valid; object group null | Out of scope for this object-only carrier |
| Object `{"b":17}` | Object group valid; both selected children null | Keep `k`; not a replay of sibling `b` |

The `{"b":17}` control keeps the sibling in the unselected residual root value, showing why this is a **key-specific** projection. The scalar-root guard is necessary: a general [RFC 7396](https://www.rfc-editor.org/rfc/rfc7396) patch can replace the entire target when it is not an object. Its value is not recovered from the two selected leaves. Outer SQL NULL is an authored no-event marker for this test, not an RFC patch literal `null`. This is not a claim that an arbitrary DuckDB constructor preserves top-level Variant null separately from SQL NULL.

For the actual native wire, the unshredded reader validates the full binary object encodings of the four object controls, with no typed leaves. For the shredded reader, the same five-operation carrier can be derived independently from the projected leaves on these exact literals. This is an authored-literal oracle, **not** a reimplementation of an arbitrary VARIANT decoder. Both newer readers return ordinary Arrow structs rather than a semantic VARIANT extractor in this replay. The leaf distinctions follow [Parquet Variant Shredding, Objects](https://parquet.apache.org/docs/file-format/types/variantshredding/#objects). Neither the requested column list nor the Arrow output type measures bytes read internally.

**Typed leaf selection depends on source type, not just JSON spelling.** A separate two-row control gives the same whole JSON `{"k":0}` for native INT32 and JSON-to-VARIANT UINT64. Despite the same `STRUCT(k INTEGER)` declaration, the former writes a real typed INT32 zero and the latter writes a binary numeric fallback, read by DuckDB as INT64. Hence inspecting schema alone does not prove that the typed leaf contains the value. This is specific to the executed build and constructors.

## Effects after forwarding

Native DuckDB `variant_exists(v,'k')` returns false for absent, true for present-null, and SQL NULL for the outer null row. By contrast `variant_typeof(variant_extract(v,'k'))` reports `VARIANT_NULL` for both absent and present-null; `TRY_CAST(variant_extract(v,'k') AS INTEGER)` further makes numeric zero and string `"0"` identical. The useful projection combines path presence with `variant_type(v,'k')` and forwards an explicit operation tag, nullable INT32 and nullable string. It gates on the root object type and avoids casting an out-of-scope input as an object action. The output is materialized into ordinary typed Parquet and reread before it is passed to stock `json_merge_patch`. The optimized and disabled-optimizer native queries agree on the fixture, not a general pushdown guarantee.

Across three authored targets (missing `k`, `k` already null with a sibling, and nonnull `k` with a sibling), each native input format passed **12/12** object effects plus **3/3** no-event effects. The independent raw-leaf-derived carrier also passed all 15 effects. The oracle distinguishes actual key presence, JSON kind, typed value, and the unchanged sibling. The bare nullable integer scalar projection passes **7/12** for either “omit every null” or “delete for every null,” but they fail on different missing/null cases; both turn the string into a number.

No speed, I/O volume, unrestricted decoder, or cross-engine semantic extraction claim. These are isolated, tiny authored native files; all filesystem paths in the script are local and automatic extension installation/loading is disabled.

## Replay

Use existing pinned local packages (no installation in the replay). Parameters are DuckDB 2.0.1, PyArrow 19.0.1, 22.0.0, 26.0.1, then a writable scratch folder. Each Arrow reader runs in a separate process.

    set -e -o pipefail
    python3 -IB check.py DUCKDB_SITE ARROW19_SITE ARROW22_SITE ARROW26_SITE WRITABLE_SCRATCH | cmp - RESULT.json
    sha256sum -c SHA256SUMS
