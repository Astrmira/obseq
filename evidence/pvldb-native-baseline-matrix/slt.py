"""Run four pinned stock DuckDB Python SQLLogicTest configurations."""

import argparse
import ast
from collections import Counter, defaultdict
import contextlib
import hashlib
from importlib.metadata import version
import io
import json
import math
from pathlib import Path
import pathlib
import re
import sys
import tempfile

import _duckdb
import duckdb

from file_and_shape import entries


PORT = "66b0687fd7b21d22eb8c2216c5e26030dc6a3286"
ARCHIVE = "61358f00600c1c49821e0ffc937b019cb42c187a7fc1dfa7fddbd1b3415840f6"
BINARY = "f8dba4b1f5c8e5f6e872f83e3b327f94c6f962f2bd3cb0acf5551cf60bbfaba2"
FUNCTIONS = {"native", "mode_rows", "stock_expected", "testtext", "digest", "HostRunner"}
TYPES = {int: ("I", "BIGINT"), float: ("R", "DOUBLE"), str: ("T", "VARCHAR")}
MODES = ("nosort", "rowsort", "valuesort", "rowsort_hash_threshold1")


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def boot(root, old_adapter, upstream_seal):
    if duckdb.__version__ != "1.4.3" or sha(Path(_duckdb.__file__)) != BINARY:
        raise ValueError("stock SLT engine binary changed")
    if sha(root / "upstream.tar.gz") != ARCHIVE or version("termcolor") != "3.1.0":
        raise ValueError("stock SLT upstream runtime changed")
    for line in upstream_seal.read_text().splitlines():
        expected, name = line.split()
        if sha(root / name) != expected:
            raise ValueError(f"extracted SLT upstream source changed: {name}")
    sys.path.insert(0, str(root / "upstream"))
    from duckdb_sqllogictest import SQLLogicParser
    from duckdb_sqllogictest.result import ExecuteResult, SQLLogicContext, SQLLogicDatabase, SQLLogicRunner, TestException

    definitions = [node for node in ast.parse(old_adapter.read_bytes()).body
                   if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in FUNCTIONS]
    if {node.name for node in definitions} != FUNCTIONS:
        raise ValueError("missing archived stock SLT harness functions")
    namespace = {**globals(), **locals()}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(old_adapter), "exec"), namespace)
    return {name: namespace[name] for name in FUNCTIONS}


def carrier(left, right):
    columns = list(zip(*(left + right)))
    tags = []
    for column in columns:
        items = [item for item in column if item is not None]
        types = {type(item) for item in items}
        if not types:
            tags.append(TYPES[str])
            continue
        if len(types) != 1 or next(iter(types)) not in TYPES:
            return None
        tag, name = TYPES[next(iter(types))]
        if ((tag == "I" and any(not -2**63 <= item < 2**63 for item in items))
                or (tag == "R" and any(not math.isfinite(item) for item in items))
                or (tag == "T" and any(item.strip() != item or item in {"NULL", "(empty)"}
                                        or any(not 32 <= ord(ch) <= 126 for ch in item) for item in items))):
            return None
        tags.append((tag, name))
    return tags or None


def query(rows, tags):
    def value(item, typ):
        if item is None:
            encoded = "NULL"
        elif typ in {"VARCHAR", "DOUBLE"}:
            encoded = "'" + str(item).replace("'", "''") + "'"
        else:
            encoded = str(item)
        return f"CAST({encoded} AS {typ})"

    if not rows:
        select = ", ".join(f"CAST(NULL AS {kind}) AS c{i}" for i, (_, kind) in enumerate(tags))
        return f"SELECT {select} WHERE FALSE"
    fields = ", ".join(f"record.c{i}" for i in range(len(tags)))
    schema = ", ".join(f"c{i} {kind}" for i, (_, kind) in enumerate(tags))
    values = ", ".join("ROW(" + ", ".join(value(cell, kind) for cell, (_, kind) in zip(row, tags)) + ")"
                       for row in rows)
    return (f"SELECT {fields} FROM UNNEST([{values}]::STRUCT({schema})[]) "
            "WITH ORDINALITY AS fixture(record, ordinal) ORDER BY ordinal")


def decide(db, harness, reference, candidate):
    verdicts = dict.fromkeys(MODES)
    errors = {}
    tags = carrier(reference, candidate)
    if tags is None:
        return verdicts, dict.fromkeys(MODES, "no_lossless_joint_sql_literal_declaration")
    expectation, actual = query(reference, tags), query(candidate, tags)
    for statement, rows in ((expectation, reference), (actual, candidate)):
        if db.execute(statement).fetchall() != list(map(tuple, rows)):
            return verdicts, dict.fromkeys(MODES, "no_lossless_sql_fixture_roundtrip")
    type_text = "".join(tag for tag, _ in tags)

    def apply(mode, test):
        result, detail, _ = harness["native"](test)
        if result == "error":
            errors[mode] = next((line.strip()[:200] for line in detail.splitlines() if line.strip()), "runner_error")
        else:
            verdicts[mode] = result == "accept"

    for mode in MODES[:3]:
        gold = harness["mode_rows"](reference, type_text, mode, harness["stock_expected"])
        test = harness["testtext"](actual, type_text, mode, "\n".join(gold))
        apply(mode, test)
    hash_mode = MODES[-1]
    if len(reference) * len(tags) > 1:
        gold_hash = harness["digest"](expectation, type_text, "rowsort")
        test = harness["testtext"](actual, type_text, "rowsort", gold_hash, "hash-threshold 1\n\n")
        apply(hash_mode, test)
    else:
        errors[hash_mode] = "gold_below_explicit_hash_threshold"
    return verdicts, errors


def main():
    p = argparse.ArgumentParser()
    for name in ("matrix", "panels", "representative", "value_driver", "slt_root", "old_adapter", "upstream_seal"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    harness = boot(a.slt_root, a.old_adapter, a.upstream_seal)
    observations, totals = [], defaultdict(lambda: defaultdict(Counter))
    with duckdb.connect(config={"enable_external_access": False, "threads": 1}) as db:
        pairs = entries(a.matrix, a.panels, a.representative, a.value_driver)
        for cohort, identity, arm, legal, reference, candidate in pairs:
            verdicts, errors = decide(db, harness, reference, candidate)
            for mode, verdict in verdicts.items():
                tag = "NA" if verdict is None else (("true_" if verdict == legal else "false_") + ("accept" if verdict else "reject"))
                totals[cohort][mode][tag] += 1
            observations.append({"cohort": cohort, "id": identity, "arm": arm, "legal": legal,
                                 "verdicts": verdicts, "errors_or_na": errors})
    print(json.dumps({"port": PORT, "duckdb": duckdb.__version__, "adapter_sha256": sha(a.old_adapter),
                      "totals": totals, "observations": observations}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
