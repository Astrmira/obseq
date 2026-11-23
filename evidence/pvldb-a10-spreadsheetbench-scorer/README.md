# A10 SpreadsheetBench V1 grading sensitivity

The official `compare_workbooks` at commit
`49b73a94775fb489063f60ca1865e3a650079a79` compares cached values in
`answer_position` with openpyxl `data_only=True`. Its separate
recalculation script offers Excel COM and LibreOffice backends.
This replay calls the original comparison function with explicit
paths, using the frozen original workbooks and A6's Calc 7.3.7.2
exports. The package identifies the dataset and grader by SHA-256.

| A6 target | Cells in grading ranges | Files intersecting | Tasks intersecting |
| --- | ---: | ---: | ---: |
| Missing original cache | 1,198 / 2,389 | 27 / 49 | 19 / 33 |
| Dominant TEXTAFTER cluster | 42,042 / 42,042 | 1 / 1 | 1 / 1 |

Of the 50 targeted answer files, 49 passed original versus original.
Comparing original versus recalculated changed 26 of those 49 from
pass to fail, across 19 distinct tasks. The 26 include the one
TEXTAFTER file and 25 files whose missing-cache cells intersect
grading ranges. The one original self-comparison failure lacks a
worksheet named by the task's grading ranges. The file-level comparison can
depend on other changes in the same grading range, so the missing
cache intersection and the score change are reported side by side.

The result measures sensitivity to the selected recalculation path
on this targeted subset. The 42,042 changes in the dominant answer
file share a single unsupported-function mechanism. Released
leaderboard accuracy and source-independent misgrading rates require
separate evidence. Workbooks, cell values, ranges and task IDs are
kept private. The published receipt uses hashed workbook and task labels.

```sh
python -IB run.py PINNED_V1_ARCHIVE A6_PRIVATE_WORKSPACE STOCK_EVALUATION_PY EVALUATOR_SHA256
```

Replay with openpyxl 3.1.5 and tqdm 4.67.1. The input workbook
archive is SpreadsheetBench 912 v0.1, and the scorer fingerprint
is in `REMOTE-INPUTS.sha256`.

[Official evaluator](https://github.com/RUCKBReasoning/SpreadsheetBench/blob/49b73a94775fb489063f60ca1865e3a650079a79/evaluation/evaluation.py) · [Recalculation script](https://github.com/RUCKBReasoning/SpreadsheetBench/blob/49b73a94775fb489063f60ca1865e3a650079a79/evaluation/open_spreadsheet.py) · A6 diagnosis
