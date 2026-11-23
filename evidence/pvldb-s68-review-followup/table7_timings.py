"""Recount check-only time and variability from the archived Table 7 workers."""

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
from statistics import median


SCALE = 100_000_000


def samples(values):
    if len(values) != 5:
        raise ValueError("Expected exactly five archived worker samples")
    return {"median": median(values), "min": min(values), "max": max(values)}


def add(samples_by_arm, label, rows, repeat, metrics):
    if sorted(row[repeat] for row in rows) != list(range(5)):
        raise ValueError(f"Bad worker roster for {label}")
    samples_by_arm[label] = {name: samples([function(row) for row in rows]) for name, function in metrics.items()}


def summarize(evidence):
    root = evidence / "e6-cross-scale-and-ratio-audit"
    sources = {}

    def content(path):
        raw = path.read_bytes()
        sources[path.relative_to(evidence).as_posix()] = hashlib.sha256(raw).hexdigest()
        return raw

    def lines(group):
        return [json.loads(line) for line in content(root / f"{group}-RAW.jsonl").splitlines()]

    outcomes = defaultdict(dict)
    for group, oracle, label in (
        ("snapshot", "O1", "method"), ("epoch", "O2", "arm"),
    ):
        raw = [row for row in lines(group) if ("repeat" if group == "snapshot" else "rep") in row]
        time_key, rss_key, scaling = (("wall_ns", "hwm_kib", 1e9) if group == "snapshot"
                                       else ("wall_s", "vmhwm_kib", 1))
        for arm in sorted({row[label] for row in raw}):
            add(outcomes[oracle], arm, [row for row in raw if row[label] == arm],
                "repeat" if group == "snapshot" else "rep",
                {"wall_s": lambda row: row[time_key] / scaling, "peak_rss_kib": lambda row: row[rss_key]})

    for group in ("topk", "representative"):
        raw = [row for row in lines(group) if row["n"] == SCALE]
        for arm in sorted({row["arm"] for row in raw}):
            add(outcomes[f"O3-{group}"], arm, [row for row in raw if row["arm"] == arm], "rep", {
                "producer_s": lambda row: row["wall_prod_ns"] / 1e9,
                "check_only_s": lambda row: row["wall_check_ns"] / 1e9,
                "total_s": lambda row: (row["wall_prod_ns"] + row["wall_check_ns"]) / 1e9,
                "within_worker_check_over_producer": lambda row: row["wall_check_ns"] / row["wall_prod_ns"],
                "peak_rss_kib": lambda row: row["final_hwm_kib"],
            })

    raw = [{key: int(value) for key, value in row.items()} for row in csv.DictReader(
        content(root / "geometry-RAW.csv").decode().splitlines())]
    for mode, arm in enumerate(("generation_checksum", "eager_exact", "lazy_filtered")):
        workers = [row for row in raw if row["mode"] == mode and row["n"] == SCALE]
        if any(row["mismatches"] for row in workers):
            raise ValueError("Archive contains a wrong exact-predicate result")
        add(outcomes["O4"], arm, workers, "rep", {
            "wall_s": lambda row: row["ns"] / 1e9, "peak_rss_kib": lambda row: row["rss_kib"]})

    raw = [row for row in lines("intent") if "rep" in row]
    add(outcomes["O5"], "overlay_and_intent", raw, "rep", {
        "apply_s": lambda row: row["apply_wall_s"], "check_only_s": lambda row: row["witness_wall_s"],
        "full_verification_s": lambda row: row["verify_wall_s"],
        "within_worker_check_over_apply": lambda row: row["witness_wall_s"] / row["apply_wall_s"],
        "peak_rss_kib": lambda row: row["vmhwm_kib"],
    })
    compiler = content(evidence / "e6-o4-native-100m-dyadic-queries/ENV.txt").decode().splitlines()
    archived = json.loads(content(root / "RESULT.json"))
    comparable = {
        "O3-topk": ("O3-topk", ("family", "guard")),
        "O3-representative": ("O3-group", ("family",)),
    }
    for output, (prior, arms) in comparable.items():
        for arm in arms:
            expected = archived["endpoint_stages"][prior]["by_scope"][str(SCALE)][arm]
            actual = outcomes[output][arm]
            if abs(actual["check_only_s"]["median"] - expected["checker_stage_median_seconds"]) > 1e-9:
                raise ValueError(f"Archived stage median differs for {output}/{arm}")
            if abs(100 * actual["within_worker_check_over_producer"]["median"]
                   - expected["median_within_trial_checker_over_producer_pct"]) > 5.01e-7:
                raise ValueError(f"Paired ratio differs for {output}/{arm}")
    return {"scope": "Archived workers, no new measurement", "rows_or_calls": SCALE, "workers_per_cell": 5,
            "timing": outcomes, "recorded_geometry_environment": compiler,
            "source_sha256": sources}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.evidence), indent=2, sort_keys=True))
