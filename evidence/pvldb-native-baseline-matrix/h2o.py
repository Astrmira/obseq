"""Replay the full H2O Q3 exchange and score its exact changed projection."""

import argparse
import ast
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import runpy
import sys

import duckdb

from tabular import VERSIONS, compare


PINNED_SOURCE = "e29693757889929569326e62552ffb795d188ac321a951004bec27bca972651a"
PINNED_HELPER = "d64c4ecafab8e2fc2534f42402ca959e79f83f972a6dea8c50fc31771d1784f6"
KINDS = ("int", "int", "int", "text", "text", "text", "float", "int", "text", "text", "float")


def pinned(path, digest):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"H2O archived source identity changed: {path.name}")
    return data.decode()


def main():
    parser = argparse.ArgumentParser()
    for name in ("source_observer", "data", "stock", "helpers", "a2_runner", "e2_source"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--pairs", type=Path, help="write comparator inputs to private scratch")
    args = parser.parse_args()
    if duckdb.__version__ != "1.4.3":
        raise ValueError("H2O native runtime changed")
    e2 = runpy.run_path(str(args.a2_runner))["observer"](args.e2_source)
    helper_ast = ast.parse(pinned(args.helpers, PINNED_HELPER))
    helper_ast.body = [node for node in helper_ast.body
                       if isinstance(node, ast.FunctionDef) and node.name in {"str_round", "make_chk"}]
    helper = {}
    exec(compile(helper_ast, str(args.helpers), "exec"), helper)

    source = pinned(args.source_observer, PINNED_SOURCE).split("# Larger faults", 1)[0]
    native = {}
    old_argv = sys.argv
    try:
        sys.argv = [str(args.source_observer), str(args.data), str(args.stock)]
        exec(compile(source, str(args.source_observer), "exec"), native)
    finally:
        sys.argv = old_argv

    q3, code = native["Q"], native["lcode"]
    left, right, first, second = (native[key] for key in ("u", "v", "mu", "mv"))
    def decimal_literal(micros):
        value = Decimal(micros).scaleb(-6)
        return f"'{value:f}'::DOUBLE"

    exchanges = {
        "clean": q3,
        "M2_payload_exchange": f"""SELECT * REPLACE (CASE ({code})
            WHEN {left} THEN {decimal_literal(second)} WHEN {right} THEN {decimal_literal(first)}
            ELSE v2 END AS v2) FROM ({q3})""",
        "positive_control_plus_one": f"SELECT * REPLACE (CASE WHEN ({code})={left} THEN v2+1 ELSE v2 END AS v2) FROM ({q3})",
    }
    checks = {}
    witness = {}
    with native["con"] as con:
        for name, sql in exchanges.items():
            n, x, y, total = con.execute(
                f"SELECT count(*), SUM(v1), SUM(v2), SUM(v2::DECIMAL(18,6)) FROM ({sql})").fetchone()
            columns = con.execute(f"DESCRIBE SELECT * FROM ({sql})").fetchall()
            witness[name] = [list(row) for row in con.execute(f"""SELECT * FROM ({sql})
                WHERE ({code}) IN ({left}, {right}) ORDER BY ({code})""").fetchall()]
            if n != 10_000_000 or len(witness[name]) != 2:
                raise ValueError("unexpected native row or selected witness count")
            checks[name] = {"rows": n, "columns": [[r[0], "ENUM" if r[1].startswith("ENUM(") else r[1]] for r in columns],
                            "exact_schema_sha256": hashlib.sha256(json.dumps(columns).encode()).hexdigest(),
                            "stock_chk": helper["make_chk"]((x, y)), "exact_v2_sum": str(total)}

    clean, swapped, positive = (checks[name] for name in exchanges)
    if clean != swapped or clean["stock_chk"] == positive["stock_chk"]:
        raise ValueError("full H2O intervention did not isolate the expected checksum blindness")
    gold = witness["clean"]
    observations = {name: {"generic": e2(gold, rows, None, None, None), **compare(gold, rows, KINDS)}
                    for name, rows in witness.items()}
    if args.pairs:
        pairs = [["benchmark_witness", "h2o-q3", name, name == "clean", gold, rows]
                 for name, rows in witness.items()]
        args.pairs.write_text(json.dumps(pairs, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"source_rows": clean["rows"], "projection_rows_per_arm": 2, "versions": VERSIONS,
                      "full_native_checks": checks, "exact_projected_exchange_delta": native["payload_expected"],
                      "witness_comparisons": observations}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
