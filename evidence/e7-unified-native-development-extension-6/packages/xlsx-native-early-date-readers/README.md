# E4 / O4 — Early 1900 serials in unchanged SpreadsheetBench XLSX bytes

From the fixed E4 release sample (2,000 paths, SHA-256 pins in RESULTS.json), all 14 qualifying files (6 inputs, 8 answers) were opened in GDAL 3.10.3’s read-only native XLSX driver and openpyxl 3.1.5. Their 49 early style-classified serials include time-only formats, not necessarily intended calendar dates. The three early cells returned as *typed Date* by GDAL were **one day earlier** than the Excel-1900 arithmetic reference. Openpyxl agreed with the reference for all three. GDAL returned String fields on the remaining 46; those strings are not judged wrong, since the typed-date comparison does not apply. Two observed same-column controls were String fields too. No phantom serial 60 was observed. These are cells, not distinct independent tasks, and certainly not a general bug rate.

An independent authored calibration puts serials 1,59,61,70 across a skipped row, exercising FID alignment: native GDAL returns one day early for 1 and 59 and the reference day for 61 and 70. Distinguish this authored evidence from the actual original workbook observations. These are native *reader* findings, not a stale-cache or Calc recalculation result.

Replay: provide the SpreadsheetBench v0.1 archive and per_file.csv from the E4 2K audit, unmodified. Both are identified by hash in RESULTS.json. Native Python needs osgeo GDAL; calling Python needs openpyxl. No network, workbook macros, links, or formula evaluation. Only aggregate results distributed.

    sha256sum -c PREFREEZE.sha256
    python -B check.py ARCHIVE MANIFEST | cmp - RESULTS.json
    python -B calibration.py | cmp - CALIBRATION.json
