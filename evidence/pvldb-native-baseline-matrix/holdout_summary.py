"""Aggregate all measured holdout methods by frozen case family or panel."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def observations(read):
    rows = {}
    for packet, cohort in (("ORIGINAL", "original"), ("LATER", "later")):
        for row in read(packet)["observations"]:
            arm = row.get("arm", "frozen_candidate")
            if arm == "alternate_decimal_diagnostic":
                continue
            group = row.get("family", row.get("panel"))
            identity = row["id"] if cohort == "original" else f"{group}/{row['id']}"
            key = cohort, identity, arm
            if key in rows:
                raise ValueError("duplicate holdout observation")
            if group == "heldout-group-role-and-fold-joint":
                group += "/fold" if arm in {"native_duration_member", "earliest_only"} else "/group_role"
            rows[key] = group, row["legal"], row["generic"] | row["tool_verdicts"]

    for packet, prefix in (("EXTRA", ""), ("SLT", "slt_"), ("DBT", "dbt_"), ("DEEQU", "deequ_")):
        seen = set()
        for row in read(packet)["observations"]:
            key = row["cohort"], row["id"], row["arm"]
            if key[0] == "natural":
                continue
            _, legal, decisions = rows[key]
            if key in seen or row["legal"] != legal:
                raise ValueError("extra methods disagree on the holdout denominator")
            seen.add(key)
            verdicts = row.get("verdicts", {k: v for k, v in row.items() if k not in {"cohort", "id", "arm", "legal"}})
            decisions.update({prefix + method: verdict for method, verdict in verdicts.items()})
        if seen != rows.keys():
            raise ValueError(f"{packet} inputs omit a holdout observation")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=Path)
    args = parser.parse_args()
    def read(packet):
        return json.loads((args.matrix / f"{packet}-RESULT.json").read_bytes())

    rows = observations(read)
    groups = defaultdict(lambda: defaultdict(Counter))
    cases = defaultdict(set)
    denominators = defaultdict(Counter)
    for (cohort, identity, _), (group, legal, decisions) in rows.items():
        cases[cohort].add(identity)
        key = f"{cohort}/{group}"
        denominators[key]["legal" if legal else "illegal"] += 1
        for name, verdict in decisions.items():
            outcome = "NA" if verdict is None else (
                ("true_" if verdict == legal else "false_") + ("accept" if verdict else "reject"))
            groups[key][name][outcome] += 1
    print(json.dumps({"cases": {k: len(v) for k, v in cases.items()}, "observations": len(rows),
                      "group_denominators": denominators, "methods_by_group": groups}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
