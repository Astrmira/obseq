"""Score two sealed E7 panels in their ordinary value projection."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import runpy

import duckdb
import pandas as pd


PINS = {
    "heldout-keyed-aggregate-cancellation": {
        "CASES.json": "b7421e79d5488b7faa9dee89c606750e9471cebc687852ba7534872a3059fa0b",
        "SEALED_LABELS.json": "fe1f3be17999c0c4cc982d37ffe1b1a0288891331cd60721f8b2196ca5a0c96a",
    },
    "heldout-ordered-intervention-receipts": {
        "CASES.json": "6d906fd606fd000aa136516c249da57217087a13d62fadac9a216b2790c583e3",
        "SEALED_LABELS.json": "3c928017a19470b36fe95885f8ebad4fc04de6f0e3de4863aa906ff79d6b2f06",
        "OBSERVED.json": "9a23baca0e2726d9f9608d623acd8d7b9cdf001d47effc95209d9df2e761c35f",
    },
}


def read(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"frozen source changed: {path.name}")
    return json.loads(data)


def frame(rows, types):
    return pd.DataFrame({f"c{index}": pd.Series([row[index] for row in rows], dtype=kind)
                         for index, kind in enumerate(types)})


def pandas_scores(reference, candidate, types):
    lhs, rhs = frame(reference, types), frame(candidate, types)
    verdicts = {}
    for name, options in (("pandas_default", {}), ("pandas_check_like", {"check_like": True}),
                          ("pandas_dtype_relaxed", {"check_dtype": False})):
        try:
            pd.testing.assert_frame_equal(lhs, rhs, **options)
        except AssertionError:
            verdicts[name] = False
        else:
            verdicts[name] = True
    return verdicts


def materialize(panel, cases):
    if panel.name == "heldout-keyed-aggregate-cancellation":
        # The source relation is a keyed bag, so choose its sorted table as the ordinary gold.
        def key(row):
            return row[0], row[1], row[2] is not None, row[2]

        return [(case["id"], sorted(case["source"], key=key), case["candidate"]) for case in cases], (
            "Int64", "object", "Int64",
        )
    env = runpy.run_path(str(panel/"check.py"))
    archived = read(panel/"OBSERVED.json", PINS[panel.name]["OBSERVED.json"])
    pairs = []
    for case in cases:
        reference, _ = env["expected"](case)
        poststate, events = env["native"](case, "DuckDB")
        if env["observe"](case, (poststate, events)) != archived["cases"][case["id"]]["DuckDB"]:
            raise ValueError("native transaction observations differ from frozen E7")
        pairs.append((case["id"], reference, poststate))
    return pairs, ("Int64", "Int64")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("panels", type=Path)
    p.add_argument("observer_runner", type=Path)
    p.add_argument("e2", type=Path)
    a = p.parse_args()
    if pd.__version__ != "2.2.3" or duckdb.__version__ != "1.4.3":
        raise ValueError("unexpected baseline or native transaction runtime")
    observer = runpy.run_path(str(a.observer_runner))["observer"](a.e2)
    results = {}
    for name, pins in PINS.items():
        directory = a.panels/name
        cases = read(directory/"CASES.json", pins["CASES.json"])
        pairs, types = materialize(directory, cases)
        truth = {r["id"]: r["legal"] for r in read(directory/"SEALED_LABELS.json", pins["SEALED_LABELS.json"])}
        if len(pairs) != 24 or {identity for identity, _, _ in pairs} != truth.keys():
            raise ValueError("unexpected independent cohort")
        outcomes = []
        decisions = {}
        for identity, ref, output in pairs:
            legal = truth[identity]
            observed = observer(ref, output, None, None, None) | pandas_scores(ref, output, types)
            outcomes.append({"id": identity, "legal": legal, "observers": observed})
            for key, verdict in observed.items():
                counts = decisions.setdefault(key, Counter())
                label = "NA" if verdict is None else (
                    "true_accept" if verdict and legal else "true_reject" if not verdict and not legal
                    else "false_accept" if verdict else "false_reject"
                )
                counts[label] += 1
        results[name] = {"legal": sum(truth.values()), "invalid": len(truth)-sum(truth.values()),
                         "summary": decisions, "observations": outcomes}
    print(json.dumps({"panels": results, "pandas": pd.__version__, "transaction_engine": duckdb.__version__},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
