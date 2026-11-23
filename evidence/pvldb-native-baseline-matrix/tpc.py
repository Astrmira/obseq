"""Score real SF10 TPC outputs under stock and source-established controls."""

import argparse
import ast
from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal
import hashlib
from io import StringIO
import json
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory

import duckdb

from q59 import evaluate as evaluate_q59, load_verifier
from tabular import VERSIONS, compare


def prior(driver, *args):
    old_args = sys.argv
    output = StringIO()
    try:
        sys.argv = [str(driver), *(str(a) for a in args)]
        with redirect_stdout(output):
            env = runpy.run_path(str(driver))
    finally:
        sys.argv = old_args
    for value in env.values():
        if isinstance(value, duckdb.DuckDBPyConnection):
            value.close()
    return env, json.loads(output.getvalue())


def convert(tables):
    """Normalize decimal scale exactly and transport dates in ISO format."""
    kinds, scales = [], []
    for column in zip(*(row for table in tables for row in table)):
        sample = [x for x in column if x is not None]
        types = {type(x) for x in sample}
        if types == {Decimal}:
            kinds.append("int")
            scales.append(max(0, *(-x.as_tuple().exponent for x in sample)))
        elif types == {int}:
            kinds.append("int")
            scales.append(None)
        elif types == {float}:
            kinds.append("float")
            scales.append(None)
        elif types == {bool}:
            kinds.append("bool")
            scales.append(None)
        elif types <= {str, date}:
            kinds.append("text")
            scales.append(None)
        else:
            raise ValueError(f"unsupported TPC column types: {types}")
    def table(rows):
        return [[int(value.scaleb(scale)) if scale is not None and value is not None
                 else value.isoformat() if isinstance(value, date) else value
                 for scale, value in zip(scales, row)] for row in rows]
    return [table(t) for t in tables], kinds, scales


def tpc39(receipt):
    fingerprints = json.loads((receipt/"SF10-SHA256.json").read_bytes())
    source = []
    for name, digest in sorted(fingerprints.items()):
        payload = (receipt/name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("Q39 source receipt changed")
        source.extend(json.loads(line) for line in payload.splitlines())
    def table(arm):
        answer = []
        for row in source:
            warehouse, item = row["key"]
            a, b, c, d = map(float.fromhex, row[arm])
            answer.append([warehouse, item, 1, a, b, warehouse, item, 2, c, d])
        return answer
    first, other = table("t1"), table("t4")
    keys = {tuple(row["key"]) for row in source}
    pos = next(i for i, r in enumerate(other) if (r[0], r[1]+1) not in keys)
    wrong_key, wrong_float = [row.copy() for row in other], [row.copy() for row in other]
    wrong_key[pos][1] += 1
    wrong_key[pos][6] += 1
    wrong_float[pos][3] *= 2
    near_float = [row.copy() for row in other]
    near_float[pos][3] = first[pos][3] * (1 + 5e-7)
    relative = abs(near_float[pos][3] / first[pos][3] - 1)
    if not 1e-9 < relative < 1e-5:
        raise ValueError("Q39 M5 did not cross only the strict tolerance")
    return first, [("native_1_to_4", other, True), ("M1_exact_key_plus_one", wrong_key, False),
                   ("M5_near_float", near_float, False), ("large_float_control", wrong_float, False)], {
                       "source_contract": "sealed independent exact source and ULP receipt",
                       "required_rows": len(first), "M5_relative_to_certified_native": relative}


def cwi_verdicts(path, source, write_answers, expected_sha):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
        raise ValueError("stock CWI tool changed")
    reference, cases, _ = source
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        gold = directory / "reference.ans"
        write_answers(gold, reference)
        result = {}
        for name, rows, _ in cases:
            candidate = directory / "candidate.ans"
            write_answers(candidate, rows)
            proc = subprocess.run([sys.executable, "-IB", str(path), str(gold), str(candidate)],
                                  capture_output=True, text=True)
            verdict = ast.literal_eval(proc.stdout.strip())["class"]
            if verdict not in ("match", "diff") or proc.stderr or proc.returncode != int(verdict == "match"):
                raise ValueError("unexpected stock CWI invocation result")
            result[name] = verdict == "match"
        return result


def observe(oracle, label, reference, entries, facts, keys, pairs=None):
    adapted, kinds, scales = convert([reference, *(r for _, r, _ in entries)])
    gold, *candidates = adapted
    records = []
    for (name, _, truth), candidate in zip(entries, candidates):
        if pairs is not None:
            pairs.append(["benchmark", label, name, truth, gold, candidate])
        records.append({"arm": name, "legal": truth, "generic": oracle(gold, candidate, None, None, None),
                        **compare(gold, candidate, kinds, keys=keys)})
    return {"query": label, "metadata": facts, "decimal_scales": scales, "observations": records}


def main():
    p = argparse.ArgumentParser()
    for name in ("drivers", "fixture_env", "dataset", "q39_receipts", "verifier", "a2_runner", "e2"):
        p.add_argument(name, type=Path)
    p.add_argument("--cwi", type=Path)
    p.add_argument("--pairs", type=Path, help="write comparator inputs to private scratch")
    a = p.parse_args()
    a2 = runpy.run_path(str(a.a2_runner))
    e2 = a2["observer"](a.e2)
    q39 = tpc39(a.q39_receipts)
    q59 = evaluate_q59(a.dataset/"tpcds.duckdb", a.fixture_env/"sql-tpcds-143.json", load_verifier(a.verifier))
    pairs = [] if a.pairs else None
    evaluations = [observe(e2, "tpcds-39", *q39, keys=(0,1), pairs=pairs),
                   observe(e2, "tpcds-59", *q59, keys=(), pairs=pairs)]
    if a.cwi:
        cwi = cwi_verdicts(a.cwi, q39, a2["write"], a2["CWI_SHA"])
        for row in evaluations[0]["observations"]:
            row["stock_cwi"] = cwi[row["arm"]]
    files = {"q59.py": hashlib.sha256(Path(__file__).with_name("q59.py").read_bytes()).hexdigest()}
    for q, engine, expected, stock, negative, tag, keys in (
        (86,"tpcds","full","stock","mut","M4_nullness_in_place_of_grouping",(1,2,3)),
        (11,"tpch","sums","corrected","full","qualification_fraction_on_scale_bound_workload",(0,)),
        (21,"tpch","canon","stock","weak","reverse_secondary_order",(0,)),
    ):
        driver = a.drivers/f"q{q}.py"
        env, receipt = prior(driver, a.fixture_env, a.dataset)
        if not env[expected]:
            raise ValueError("independent source oracle failed to construct its reference")
        label = f"{engine}-{q}"
        entries = [(tag, env[negative], False)]
        if q == 86:
            nonnull = [row for row in env[stock] if row[3] != 0 or (row[1] is not None and row[2] is not None)]
            receipt["M7_detail_rows_removed"] = len(env[stock]) - len(nonnull)
            if len(nonnull) != len(env[stock]):
                entries.append(("M7_drop_null_detail_groups", nonnull, False))
        evaluations.append(observe(e2, label, env[stock], entries, receipt, keys, pairs))
        files[driver.name] = hashlib.sha256(driver.read_bytes()).hexdigest()
    if a.pairs:
        a.pairs.write_text(json.dumps(pairs, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"engine": duckdb.__version__, "scale":10, "versions":VERSIONS,
                      "replayed_independent_source_drivers": files, "queries": evaluations},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
