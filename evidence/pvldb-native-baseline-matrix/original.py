"""Compare the original 108 frozen case payloads to verified fixed exemplars."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import runpy

from later import token
from tabular import VERSIONS, compare


ROW_FIELDS = {"events", "groups", "ids", "items", "pairs", "points", "values"}
SCALARS = {int: "int", bool: "bool", str: "text", float: "float"}


def carrier(left, right, family):
    if family == "F1":
        for value in (left, right):
            for key in {"value", "integer", "max", "difference"} & value.keys():
                value[key] = int(value[key])
    if family == "O4-dateserial":
        return ([[str(left["serial"])]], [[str(right["serial"])]], ["text"], ())

    if "numbers" in left:
        left, right = left["numbers"], right["numbers"]
    fields = left.keys() | right.keys()
    if (len(fields) == 1 and next(iter(fields)) in ROW_FIELDS
            and all(isinstance(value, list) for value in (*left.values(), *right.values()))):
        field = next(iter(fields))
        def records(record):
            return [value if isinstance(value, list) else [value] for value in record[field]]
        a, b = records(left), records(right)
        keys = ()
    elif family == "F9":
        a, b = [left["repr"]], [right["repr"]]
        keys = ()
    else:
        # Preserve missing fields, nested values, and typed nulls distinctly.
        a, b = [[field, value] for field, value in sorted(left.items())], [
            [field, value] for field, value in sorted(right.items())]
        keys = (0,)

    widths = {len(row) for row in a + b}
    if not widths and family == "F2":
        return a, b, ["text", "text"], keys
    if len(widths) != 1:
        raise ValueError(f"unsupported table shape for {family}: {widths}")
    kinds, encode = [], []
    for values in zip(*(a + b)):
        types = {type(value) for value in values if value is not None}
        if len(types) == 1 and next(iter(types)) in SCALARS:
            kinds.append(SCALARS[next(iter(types))])
            encode.append(False)
        else:
            kinds.append("text")
            encode.append(bool(types))
    def table(rows):
        return [[token(value) if typed else value for typed, value in zip(encode, row)] for row in rows]
    return table(a), table(b), kinds, keys


def reference(case, family, index, selections):
    source = case["inputs"]
    if family == "O4-wkb":
        return {"hex": source["referenceHex"]}
    if family == "O4-numtext":
        return {"text": source["reference"]}
    if family == "O4-pointset":
        return {"points": source["points"]}
    return selections[family][index - 1]


def main():
    p = argparse.ArgumentParser()
    for name in ("frozen", "selections", "a2_runner", "e2_source"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    def read(path):
        raw = path.read_bytes()
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    hashes = {}
    original = read(a.frozen / "BLIND.json")
    truth = {item["case_id"]: item["predicted_legal"] for item in read(a.frozen / "PREDICTIONS.json")}
    selections = read(a.selections)
    adjudicate = runpy.run_path(str(a.frozen / "check.py"))["legal"]
    e2 = runpy.run_path(str(a.a2_runner))["observer"](a.e2_source)
    if set(truth) != {r["case_id"] for r in original} or len(truth) != 108:
        raise ValueError("expected the full original-108 cohort")
    observations, counts = [], defaultdict(Counter)
    for row in original:
        identity = row["case_id"]
        family, index = identity.removeprefix("E7H-").rsplit("-", 1)
        candidate = row["candidate"]
        gold = reference(row, family, int(index), selections)
        if not adjudicate(row | {"candidate": gold}):
            raise ValueError(f"reference is illegal for {identity}")
        legal = truth[identity]
        if type(legal) is not bool or adjudicate(row) != legal:
            raise ValueError(f"frozen adjudication mismatch for {identity}")
        lhs, rhs, kinds, keys = carrier(gold.copy(), candidate.copy(), family)
        generic = e2(lhs, rhs, None, None, None)
        tools = compare(lhs, rhs, kinds, keys=keys)
        for name, verdict in (generic | tools["tool_verdicts"]).items():
            outcome = "NA" if verdict is None else (
                ("true_" if verdict == legal else "false_") + ("accept" if verdict else "reject"))
            counts[name][outcome] += 1
        observations.append({"id": identity, "family": family, "legal": legal, "gold": gold,
                             "reference_rows": lhs, "candidate_rows": rhs, "carrier_types": kinds,
                             "generic": generic, **tools})
    print(json.dumps({"cases": len(observations), "versions": VERSIONS, "inputs_sha256": hashes,
                      "counts": counts, "observations": observations}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
