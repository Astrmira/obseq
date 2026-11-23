# E5: stock GX determines NULL and numeric range, not source support

Test stock Great Expectations 1.25.0 with its installed Pandas backend, on full pinned [NOAA OISST](https://www.ncei.noaa.gov/products/optimum-interpolation-sst) January 2 SST and NOAA GOES ABI binary cloud mask BCM. Obtain typed native GDAL packed values, declared variable ranges, and independently check complete GDAL native mask equality to the exact declared fill code. Neither file's values are edited. Raw UInt8/Int16 are transported as exact nullable Int16 without overflow. The alternate representation uses the identical grid and unchanged numeric codes at valid positions, but replaces only the declared fill slots with NA.

| Variable | Grid slots | Native fill / absent | Typed valid numeric range | Numeric violations among supported values |
|---|---:|---:|---|---:|
| GOES BCM | 3,750,000 | 47,162 (255) | 0–1 | 0 |
| OISST SST | 1,036,800 | 345,650 (−999) | −300–4,500 packed units | 0 |

Use stock [GX expectations](https://docs.greatexpectations.io/) with default strict success, backed by native metrics rather than a reimplemented comparator. On **raw packed codes**, ExpectColumnValuesToNotBeNull passes both grids; ExpectColumnValuesToBeBetween rejects each fill code as out of range. On **support-to-NA transport**, Between passes both grids, explicitly reporting the same 47,162 / 345,650 entries in its missing counter rather than as unexpected. The strict NotBeNull expectation then detects precisely those declared fill positions. Even though the parser exposes every slot in both versions, each condition tests a different question. Numeric validity among observed values and coverage of a separately declared domain must not be conflated. Optional record-index matching was not requested; reported native counts are exact.

A hypothetical complete-grid policy would fail both, even if an application checks only raw NotBeNull or only adapted Between. The actual files' fill codes can be legitimate domain absences (e.g. land in SST), not data-quality faults; no complete earth-grid observation is expected. Choose the science support universe explicitly, preserve the source metadata in the adapter, and report both the scoped coverage denominator and observed-value validity. These are intended native APIs on one exact installed backend, not a fault/bug claim about GX or NOAA, nor evidence of a population prevalence or deployment incidence.

Replay (original data files remain private to the test workspace and are not distributed):
```sh
set -o pipefail
sha256sum -c SHA256SUMS
sha256sum -c SOURCES.sha256
PYTHONPATH=/workspace/shared/eab-gx25/deps python3 -B check.py /tmp/r98-goes.nc /tmp/r94-20250102.nc | cmp - RESULTS.json
```
Uses installed GX 1.25.0, Pandas 3.1.1 and /usr/bin/python3 GDAL 3.10.3. No raw samples exported, no acquisition, timing report or Git write.
