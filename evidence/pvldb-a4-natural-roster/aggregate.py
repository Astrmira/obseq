"""Summarize observed release-pair detections, keeping unavailable cells explicit."""

import argparse
from collections import defaultdict
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def observations(roster, matrix):
    added = roster / "E5-LEGACY.json"
    legacy = {(r["id"], r["arm"]): r for r in read(added)["observations"]} if added.is_file() else {}
    for name, field, release in (("OLD-PILOT", "rows", "old"), ("NEW-PILOT", "rows", "new"),
                                 ("PAIRED-PANDAS-2.3.3", "observations", "2.3.3"),
                                 ("PAIRED-PANDAS-3.0.0", "observations", "3.0.0")):
        counts = defaultdict(int)
        for row in read(roster / f"{name}.json")[field]:
            family = row["family"]
            key = family, f"{release}:{counts[family]}"
            counts[family] += 1
            e5 = legacy.pop(key) if added.is_file() else None
            if e5 is not None and e5["legal"] != row["legal"]:
                raise ValueError(f"legacy E5 replay disagrees with the frozen label: {key}")
            yield family, row["legal"], row["observers"] | (e5["e5"] if e5 else {})
    if legacy:
        raise ValueError("some legacy E5 replay arms have no frozen match")
    extras = defaultdict(dict)
    for packet, prefix in (("EXTRA", ""), ("SLT", "slt_"), ("DBT", "dbt_"), ("DEEQU", "deequ_")):
        file = matrix / f"{packet}-RESULT.json"
        if not file.is_file():
            continue
        for row in read(file)["observations"]:
            if row["cohort"] != "natural":
                continue
            cell = extras[(row["id"], row["arm"])]
            if "legal" in cell and cell["legal"] != row["legal"]:
                raise ValueError("inconsistent native comparator truth")
            cell["legal"] = row["legal"]
            verdicts = row.get("verdicts", {k: v for k, v in row.items() if k not in {"cohort", "id", "arm", "legal"}})
            cell.update({prefix + key: verdict for key, verdict in verdicts.items()})
    for name in ("NATURAL", "NATURAL-EXTENDED"):
        for row in read(matrix / f"{name}-RESULT.json")["observations"]:
            extra = extras[(row["family"], row["version"])]
            if extra and extra["legal"] != row["legal"]:
                raise ValueError("native comparison modules disagree on the oracle label")
            yield row["family"], row["legal"], row["generic"] | row["tool_verdicts"] | {
                tool: verdict for tool, verdict in extra.items() if tool != "legal"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("roster", type=Path)
    p.add_argument("matrix", type=Path)
    args = p.parse_args()
    roster = {r["family"] for r in read(args.roster / "ROSTER.json")}
    datasets = defaultdict(list)
    all_tools = set()
    for family, legal, decisions in observations(args.roster, args.matrix):
        datasets[family].append((legal, decisions))
        all_tools.update(decisions)
    if set(datasets) != roster or not all(any(not legal for legal, _ in rows) for rows in datasets.values()):
        raise ValueError("natural scores do not cover the exact release-pair roster")

    by_family = {}
    totals = defaultdict(lambda: defaultdict(int))
    for family, rows in sorted(datasets.items()):
        methods = {}
        for tool in sorted(all_tools):
            illegal_verdicts = [r.get(tool) for valid, r in rows if not valid]
            legal_verdicts = [r.get(tool) for valid, r in rows if valid]
            tested = [decision for decision in illegal_verdicts if decision is not None]
            misses = tested.count(True)
            detections = tested.count(False)
            if tested:
                totals[tool]["pairs_with_determinate_illegal_arm"] += 1
                totals[tool]["pairs_with_any_fault_detected"] += int(detections > 0)
                totals[tool]["pairs_with_every_illegal_arm_detected"] += int(detections == len(illegal_verdicts))
            if any(decision is not None for decision in legal_verdicts):
                totals[tool]["pairs_with_determinate_legal_arm"] += 1
                totals[tool]["pairs_with_any_legal_arm_rejected"] += int(False in legal_verdicts)
            methods[tool] = {"detected": detections, "missed": misses, "illegal_na": illegal_verdicts.count(None),
                             "legal_rejected": legal_verdicts.count(False), "legal_accepted": legal_verdicts.count(True),
                             "legal_na": legal_verdicts.count(None)}
        by_family[family] = methods
    print(json.dumps({"release_pairs": len(roster), "method_totals": totals,
                      "families": by_family}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
