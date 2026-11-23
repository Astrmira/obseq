"""Recount the equal-length controls and check coverage against the original runs."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


RUNS = ("TPCH-SF1", "TPCH-SF10", "TPCDS-SF1", "TPCDS-SF10", "CLICKBENCH")
CONTROLS = {
    "membership": "same_count_absent_member",
    "multiplicity": "same_count_excess_multiplicity",
    "order": "same_count_wrong_order",
}


def summarize(root):
    sources = {}

    def records(name):
        data = (root / name).read_bytes()
        sources[name] = hashlib.sha256(data).hexdigest()
        return [json.loads(line) for line in data.splitlines()]

    counts = defaultdict(Counter)
    distinct = set()
    windows_with_control = set()
    native, shape, equal_length = 0, 0, 0
    for label in RUNS:
        old = records(f"VERIFY-{label}.jsonl")
        new = records(f"SAME-CARDINALITY-{label}.jsonl")
        for before, after in zip(old, new, strict=True):
            key = (before["suite"], before["query"], before["sql_sha256"])
            if key != (after["suite"], after["query"], after["sql_sha256"]) or "error" in after:
                raise ValueError(f"window identity or execution changed for {label} {key}: {after}")
            distinct.add(key)
            prior = before["observations"]
            observed = after["observations"]
            if set(observed) - set(prior) - set(CONTROLS.values()):
                raise ValueError(f"unexpected control for {label} {key}")
            for arm, row in prior.items():
                if observed[arm] != row:
                    raise ValueError(f"original result changed for {label} {key} {arm}")
                if arm.startswith("native_"):
                    native += int(row["accepted"])
                elif arm == "shape_negative_control":
                    shape += int(not row["accepted"])
            unavailable = after["same_cardinality_unavailable"]
            for category, arm in CONTROLS.items():
                if arm in observed:
                    check = observed[arm]
                    if check["accepted"] or check["observed_rows"] != check["required_rows"]:
                        raise ValueError(f"equal-length control escaped or changed size: {label} {key} {arm}")
                    counts[category]["rejected"] += 1
                    equal_length += 1
                    windows_with_control.add(key)
                else:
                    counts[category][unavailable[category]] += 1
    return {
        "distinct_sql_windows": len(distinct),
        "distinct_sql_windows_with_equal_length_control": len(windows_with_control),
        "suite_scale_window_runs": shape,
        "native_outputs_accepted": native,
        "shape_controls_rejected": shape,
        "equal_length_controls_rejected": equal_length,
        "equal_length_by_kind": dict(counts),
        "source_sha256": sources,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.receipts), indent=2, sort_keys=True))
