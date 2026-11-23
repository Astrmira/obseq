"""Score frozen TPC-DS SF10 Q39 candidates through E2 predicates and stock CWI."""

import argparse
import ast
from collections import Counter
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile


CWI_SHA = "65171e4a8a54b5330fba5c97c4d705f34410c62748d9180cb2e161b628a7540f"
E2_FUNCTIONS = {"canonical", "sumcols", "tol", "schema", "tests"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observer(path):
    module = ast.parse(path.read_bytes(), filename=str(path))
    required = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name in E2_FUNCTIONS]
    if {node.name for node in required} != E2_FUNCTIONS:
        raise ValueError("frozen E2 predicate definitions not found")
    environment = {"json": json, "Fraction": Fraction, "math": math, "Counter": Counter}
    exec(compile(ast.Module(body=required, type_ignores=[]), str(path), "exec"), environment)
    return environment["tests"]


def write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        csv.writer(stream, delimiter="\t", lineterminator="\n").writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("native", type=Path)
    parser.add_argument("fingerprints", type=Path)
    parser.add_argument("cwi", type=Path)
    parser.add_argument("e2", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    import pandas
    if pandas.__version__ != "2.2.3" or sha(args.cwi) != CWI_SHA:
        raise ValueError("stock comparator/runtime identity mismatch")
    expected = json.loads(args.fingerprints.read_bytes())
    payload = []
    for name, fingerprint in sorted(expected.items()):
        path = args.native / name
        if sha(path) != fingerprint:
            raise ValueError(f"source payload drift: {name}")
        payload.extend(json.loads(line) for line in path.read_text().splitlines())
    keys = {tuple(row["key"]) for row in payload}
    if len(keys) != len(payload) or len(keys) != 2433:
        raise ValueError("Q39 native output domain mismatch")

    def table(arm):
        rows = []
        for row in payload:
            i, k = row["key"]
            a, b, c, d = map(float.fromhex, row[arm])
            rows.append([i, k, 1, a, b, i, k, 2, c, d])
        return rows

    a, b = table("t1"), table("t4")
    position = next(i for i, r in enumerate(b) if (r[0], r[1] + 1) not in keys)
    c, d = [row.copy() for row in b], [row.copy() for row in b]
    c[position][1] += 1
    c[position][6] += 1
    d[position][3] *= 2
    # The two native rows were sealed against the separate exact source reference.
    # The two invalid controls reproduce the pre-existing E8 mutations.
    cases = [
        ("native_1_to_4", 0, 1, True), ("native_4_to_1", 1, 0, True),
        ("M1_exact_key_plus_one", 0, 2, False), ("large_float_control", 0, 3, False),
    ]
    compare = observer(args.e2)
    values = (a, b, c, d)
    observed = []
    with tempfile.TemporaryDirectory() as tmp:
        paths = [Path(tmp) / f"{index}.ans" for index in range(4)]
        for path, rows in zip(paths, values):
            write(path, rows)
        hashes = list(map(sha, paths))
        for label, gold, candidate, legal in cases:
            p = subprocess.run([sys.executable, "-IB", str(args.cwi), str(paths[gold]), str(paths[candidate])],
                               capture_output=True, text=True)
            verdict = ast.literal_eval(p.stdout.strip())["class"]
            if verdict not in ("match", "diff") or p.stderr or p.returncode != int(verdict == "match"):
                raise ValueError("invalid stock CWI receipt")
            tests = compare(values[gold], values[candidate], hashes[gold], hashes[candidate], None)
            tests["stock_cwi"] = verdict == "match"
            observed.append({"arm": label, "legal": legal, **tests})
    result = {
        "benchmark": "TPC-DS", "query": 39, "scale": 10, "population": len(a),
        "rows_with_native_drift": sum(x != y for x, y in zip(a, b)),
        "stock_cwi_sha256": sha(args.cwi), "e2_source_sha256": sha(args.e2),
        "pandas": pandas.__version__, "observations": observed,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "RESULT.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    with (args.output / "RESULT.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(observed[0]))
        writer.writeheader()
        writer.writerows(observed)


if __name__ == "__main__":
    main()
