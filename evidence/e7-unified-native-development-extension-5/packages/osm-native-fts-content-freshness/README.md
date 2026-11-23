# E3 F4: a stale search index can pass physical integrity and count checks

Use the exact previously admitted [Geofabrik Liechtenstein road layer](https://download.geofabrik.de/europe/liechtenstein.html), all 14,665 FID/name pairs. Source is SHA-pinned and read-only. Stage those unchanged names in SQLite 3.53.1 with a native FTS5 *external-content* inverted index and explicitly chosen ASCII tokenizer. A separate literal tokenizer enumerates all 4,075 positional postings (term, FID, offset) and independently checks full native fts5vocab on every phase. A deterministic frequent eligible term is selected by predeclared rule, not reported in the packet.

In scratch, swap existing real labels between 64 matching and 64 nonmatching FIDs, preserving the exact bag of names and total per-token occurrences. Commit the content update but do not maintain the existing index. Close/reopen. This is a deliberate stale derived-state intervention, not a failure in the input, renderer or native engine.

| Phase | Native MATCH cardinality | Wrong inclusions / missing FIDs | FTS internal check | Content-bound check |
|---|---:|---:|---|---|
| Initial coherent | 196 | 0 / 0 | OK | OK |
| Content swap only | 196 | 64 / 64 | OK | rejects |
| Install trigger late | 196 | 64 / 64 | OK | rejects |
| Targeted positional refresh | 196 | 0 / 0 | OK | OK |
| Reverse swap with trigger | 196 | 0 / 0 | OK | OK |

In both stale phases, the database generic integrity check also says OK, non-MATCH projection through the same FTS table shows all current rows and labels, and global token occurrence counts match the current full corpus. The native MATCH query instead returns stale posting IDs and then looks up those rows' **current** labels: 64 returned labels contain no matching token, and 64 correct row IDs are absent. Across the whole positional index, there are 249 wrong and 249 missing postings. This verifies a distinct semantic hole in a count-only or physical integrity observer.

SQLite documents [external content semantics](https://www.sqlite.org/fts5.html#external_content_table_pitfalls) and [FTS integrity scope](https://www.sqlite.org/fts5.html#the_integrity_check_command): rank=0 checks internal validity; rank=1 additionally binds external content (the expected mismatch here returns SQLITE_CORRUPT_VTAB, not necessarily damaged database bytes). Future write triggers do not replay history. Where the complete changed FIDs and **exact previously indexed labels** are known, the fixture atomically removes old postings with the old labels and inserts the new ones for just 128 rows, after which the content-bound check and every exact posting pass. If that old binding is untrusted or missing, this experiment does not justify targeted removal; rebuild from a verified current source under the declared tokenizer instead. Only the contained UPDATE trigger path is tested, not all insert/delete or write-bypass forms.

Replay:
```sh
set -o pipefail
sha256sum -c SHA256SUMS
python3 -IB check.py /tmp/pvl-eab-submission/e4/inputs/osm/liechtenstein.gpkg /workspace/shared | cmp - RESULTS.json
```
Exact source IDs/labels and temporary databases are not exported. No timing, network acquisition, install, or Git writes.
