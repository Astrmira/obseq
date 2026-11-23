"""Replay and score five archived natural pandas release-pair families."""

import argparse
from collections import Counter
import json
from pathlib import Path
import runpy
import subprocess
import sys

import numpy as np
import pandas as pd


GROUPBY = "e9-supplemental-f3-pandas-groupby-snapshot"
UNIQUENESS = "e9-supplemental-f4-pandas-index-uniqueness-cache"
PARTIAL = "e9-supplemental-f5-pandas-partial-key-write"
BOUNDARIES = "e9-supplemental-f6-pandas-ordered-boundaries"


def one_row(value):
    return [[value]]


def column(values):
    return [[value] for value in values]


def outputs(root):
    def replay(package, script, *args):
        data = subprocess.check_output([sys.executable, "-B", str(root/package/script), *args])
        result = json.loads(data)
        if (result["pandas"], result["numpy"]) != (pd.__version__, np.__version__):
            raise ValueError("native release differs from its scoring process")
        return result

    source = replay(GROUPBY, "replay.py")
    for mode, case in source["cases"].items():
        yield "pandas-groupby-snapshot", mode, case["expected"], case["got"], ("Int64", "Int64")
    for row in replay(UNIQUENESS, "check.py", "native")["rows"]:
        yield "pandas-index-uniqueness-cache", str(row["offset"]), one_row(row["expected"]), one_row(row["warmed_child"]), ("boolean",)
    value = replay(PARTIAL, "check.py", pd.__version__)
    for mode in ("first_assignment", "same_assignment_repeated", "qualified_tuple_control"):
        yield "pandas-idempotent-partial-key-write", mode, column(value["rhs_value_contract"]), column(value[mode]), ("Float64",)
    for row in replay(BOUNDARIES, "check.py", "one")["rows"]:
        actual, expected = row["actual"], row["expected"]
        case = str(row["issue"]) + ":" + str(row["shift"])
        if row["issue"] == 50946:
            yield "pandas-asof-string-boundary", case, one_row(expected), one_row(actual), ("object",)
        else:
            yield "pandas-annual-boundaries", case, column(expected), column(actual), ("object",)


def main():
    p = argparse.ArgumentParser()
    for name in ("archive_root", "a3_runner", "a2_runner", "e2"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    if pd.__version__ not in ("2.3.3", "3.0.0") or np.__version__ != "2.3.5":
        raise ValueError("unexpected stock release or NumPy version")
    pandas_scores = runpy.run_path(str(a.a3_runner))["pandas_scores"]
    e2 = runpy.run_path(str(a.a2_runner))["observer"](a.e2)
    rows = []
    for family, case, reference, candidate, types in outputs(a.archive_root):
        rows.append({"family": family, "case": case, "legal": reference == candidate,
                     "observers": e2(reference, candidate, None, None, None) |
                                  pandas_scores(reference, candidate, types)})
    counts = Counter(row["family"] for row in rows if not row["legal"])
    if len(rows) != 19 or (pd.__version__ == "3.0.0" and counts) or (pd.__version__ == "2.3.3" and len(counts) != 5):
        raise ValueError("natural replay disagrees with the source evidence")
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "observations": rows,
                      "failures_by_family": counts}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
