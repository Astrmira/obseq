# F5: explicit native road-layer update masks distinguish omitted and NULL fields

Select the first 16 qualifying native road features in FID order from the SHA-pinned original Geofabrik Liechtenstein GeoPackage. Create four tiny disposable GPKGs containing only those unchanged typed features, with nonempty original name or a deliberately blanked name. The correct OGR UpdateFeature mask includes ref=NULL and maxspeed=0; the mutant mask also includes name=NULL. In the correct call the name field is unset as well as omitted from the API mask. The real update calls run in native transactions, close, and reopen. Independent native SQLite reads and integrity checks verify the three attribute values and unmodified native geometry bytes; OGR checks all untouched attributes and original WKB. Neither source data nor temporary geometry is distributed.

| Observer | With original nonempty name | With name blank before both edits |
|---|---:|---:|
| Explicit OGR assignment-mask distinction | different | different |
| Exact matched typed feature values |16/16 changed|0/16 changed|
| Native GPKG integrity, geometry and row count |same|same|
| Native non-null name count |different|same|

The omitted-versus-NULL distinction is an update contract, not something an output-only comparator can reconstruct on an initial state where both effects are equal. This is a new geographic feature-write workflow, not office sparse cells or the earlier publisher TLC JSON patch. Findings do not assert any source corruption or prevalence.

    set -eo pipefail
    sha256sum -c SHA256SUMS
    /usr/bin/python3 -B run.py PINNED_OSM_GPKG | cmp - RESULT.json
