# E3 F9: persisted ANY affinity changes a real typed downstream key

The existing [Geofabrik Liechtenstein GeoPackage](https://download.geofabrik.de/europe/liechtenstein.html) is opened read-only with its exact SHA. Native SQLite and independent GDAL/OGR type and value readout confirm the same 17,914 committed building FID and osm_id string pairs. Only these non-geometric attributes are read. This measures a deliberate reload intervention on genuine OSM source identifiers, not a difference in the official dataset or software defect.

Load exactly the unchanged original Python string values into two private native SQLite tables with identical column declarations as returned by table_info. One table is ordinary with an ANY column, and the other a STRICT table with ANY. Their table-level strictness flag is observably different, so this is not equality of complete schemas. Close/reopen both files and run integrity_check. The [documented ANY behavior](https://www.sqlite.org/stricttables.html#the_any_datatype) means ordinary stores numeric-looking text as integers in this cohort, while STRICT preserves insertion type.

| Witness | Ordinary | STRICT |
|---|---:|---:|
| Persisted SQLite storage class | 17,914 integer | 17,914 text |
| Cross-engine native JSON type in DuckDB after SQLite json_object | 17,914 UBIGINT | 17,914 VARCHAR |
| Integrity check | OK | OK |

Both copies preserve row count, numeric sum, and exact per-FID integer-cast equality. However, under a typed identifier observer that compares uncoerced SQLite JSON member expressions, **0/17,914** same-FID keys compare equal across the two editions. This is not just typeof output: it changes the downstream typed lookup. DuckDB 1.4.3 sees the same numeric/string split independently. The result is distinct from binary64 precision collapse: all actual values are canonical positive decimal digits and exactly representable as bounded integers.

The verified domain permits a repair: explicitly serialize ordinary storage as TEXT, then check the complete keyed relation against the admitted source strings (all recovered here). Do not generalize to leading zeros, signs/formatting, noncanonical numerals, or larger identifiers; conversion can erase distinctions on those domains. A deployment requiring source text identity should retain an explicit TEXT storage/serialization contract or a tested strict policy, not assume ANY declarations or successful file integrity checks establish it.

Replay from this directory:
```sh
set -o pipefail
sha256sum -c SHA256SUMS
PYTHONPATH=/tmp/pvl-eab-submission/e1/input/duck143:/tmp/pvl-eab-submission/e4/deps \
  python3 -B check.py /tmp/pvl-eab-submission/e4/inputs/osm/liechtenstein.gpkg /workspace/shared | cmp - RESULTS.json
```
SQLite 3.53.1, DuckDB 1.4.3, installed PyArrow and system GDAL/OGR. No source export, external operation, timing comparison or Git write.
