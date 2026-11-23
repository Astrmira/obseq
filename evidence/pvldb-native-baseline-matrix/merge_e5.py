"""Join the sixteen E5 decisions by cohort, case and arm."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


PACKETS = {"FRAMES": "", "EXTRA": "", "SLT": "slt_", "DBT": "dbt_", "DEEQU": "deequ_"}
IDENTITY = ("cohort", "id", "arm")


def merge(root):
    table = {}
    inputs = {}
    for packet, prefix in PACKETS.items():
        content = (root / f"{packet}-RESULT.json").read_bytes()
        result = json.loads(content)
        inputs[packet] = {"sha256": hashlib.sha256(content).hexdigest(), "versions": result["versions"]}
        seen = set()
        for row in result["observations"]:
            key = tuple(row[field] for field in IDENTITY)
            target = table.setdefault(key, {**dict(zip(IDENTITY, key)), "legal": row["legal"], "e5": {}})
            if key in seen or target["legal"] != row["legal"]:
                raise ValueError(f"duplicate arm or disagreeing labels in {packet}: {key}")
            seen.add(key)
            for method, decision in row.items():
                if method not in (*IDENTITY, "legal"):
                    if decision is not None and type(decision) is not bool:
                        raise ValueError(f"non-boolean verdict from {method}")
                    target["e5"][prefix + method] = decision
        if seen != set(table):
            raise ValueError(f"missing comparison rows in {packet}")
    totals = defaultdict(lambda: defaultdict(Counter))
    observations = [table[key] for key in sorted(table)]
    for row in observations:
        if len(row["e5"]) != 16:
            raise ValueError(f"incomplete E5 configuration list for {row['id']}")
        for method, verdict in row["e5"].items():
            category = "NA" if verdict is None else (
                ("true_" if verdict == row["legal"] else "false_") + ("accept" if verdict else "reject"))
            totals[row["cohort"]][method][category] += 1
    return {"inputs": inputs, "observations": observations, "totals": totals}


def key_sensitivity(benchmark, diagnostic):
    original = {tuple(row[x] for x in IDENTITY): row for row in benchmark["observations"]
                if row["cohort"] == "benchmark"}
    totals = defaultdict(lambda: defaultdict(Counter))
    seen = set()
    for row in diagnostic["observations"]:
        key = tuple(row[x] for x in IDENTITY)
        reference = original[key]
        if key in seen or reference["legal"] != row["legal"] or (
            reference["e5"]["datacompy_keyed"] != row["datacompy_positional"]
        ):
            raise ValueError(f"misaligned or changed positional arm: {key}")
        seen.add(key)
        suite = "ClickBench" if row["id"].startswith("clickbench-") else "TPC"
        for method in ("datacompy_positional", "datacompy_natural_key"):
            verdict = row[method]
            category = "NA_legal" if row["legal"] else "NA_illegal"
            if verdict is not None:
                category = ("true_" if verdict == row["legal"] else "false_") + (
                    "accept" if verdict else "reject")
            totals[suite][method][category] += 1
    if seen != original.keys():
        raise ValueError("diagnostic did not cover all benchmark arms")
    return {**diagnostic, "totals": totals}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("packets", type=Path)
    parser.add_argument("--key-diagnostic", type=Path)
    args = parser.parse_args()
    result = (key_sensitivity(json.loads(args.packets.read_bytes()),
                              json.loads(args.key_diagnostic.read_bytes()))
              if args.key_diagnostic else merge(args.packets))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
