"""Score the frozen E7 coherent-representative panel with E2 common observers."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import runpy


CASE_SHA = "4c1862db300aaa915957701225e7bc3fb692cf9c202f6db764c3fb61c1d158a2"
LABEL_SHA = "bf950fdd516e48ade8824c7a276fcd39ce962b4b88aa6830ad238092d4bb7745"
VISIBLE = ("g", "s", "d", "p", "t")


def pinned(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("frozen independent cohort bytes changed")
    return json.loads(data)


def default_output(source):
    totals = defaultdict(list)
    for row in source:
        if row["s"] is not None:
            totals[row["g"]].append([row[key] for key in VISIBLE])
    answer = []
    for _, rows in sorted(totals.items()):
        score = min(row[1] for row in rows)
        answer.append(min((row for row in rows if row[1] == score),
                          key=lambda row: tuple((value is not None, value) for value in row)))
    return answer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("panel", type=Path)
    parser.add_argument("observer_module", type=Path)
    parser.add_argument("e2_source", type=Path)
    args = parser.parse_args()
    inputs = pinned(args.panel / "CASES.json", CASE_SHA)
    # Freeze the reference from source rows before reading any candidate or sealed label.
    references = {row["id"]: default_output(row["source"]) for row in inputs}
    truth = {row["id"]: row["accepted"] for row in pinned(args.panel / "SEALED_LABELS.json", LABEL_SHA)}
    if len(inputs) != 24 or references.keys() != truth.keys():
        raise ValueError("independent panel count or identity mismatch")
    test = runpy.run_path(str(args.observer_module))["observer"](args.e2_source)
    observations = []
    counts = defaultdict(Counter)
    for row in inputs:
        case = row["id"]
        candidate = [[entry[key] for key in VISIBLE] for entry in row["candidate"]]
        observed = test(references[case], candidate, None, None, None)
        for name, verdict in observed.items():
            category = ("NA" if verdict is None else ("true_" if verdict == truth[case] else "false_")
                        + ("accept" if verdict else "reject"))
            counts[name][category] += 1
        observations.append({"case": case, "legal": truth[case], "observers": observed})
    print(json.dumps({
        "cases": 24, "legal": sum(truth.values()), "invalid": 24 - sum(truth.values()),
        "visible_fields": VISIBLE, "observers": counts, "observations": observations,
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
