"""Recount the same-host Table 7, geometry pressure and Q39 follow-up."""

from collections import defaultdict
import csv
import json
import runpy
from statistics import median


PACKET = "evidence/pvldb-s69-followup"
PREVIOUS = "evidence/pvldb-s68-review-followup"
SCALE = 100_000_000


def records(path):
    return [json.loads(row) for row in path.read_bytes().splitlines()]


def numeric_csv(path):
    with path.open(encoding="ascii", newline="") as stream:
        return [{key: int(value) for key, value in row.items()} for row in csv.DictReader(stream)]


def five(rows, repeat):
    if sorted(row[repeat] for row in rows) != list(range(5)):
        raise ValueError("Expected the five distinct worker repeats")
    return sorted(rows, key=lambda row: row[repeat])


def stats(values):
    if len(values) != 5 or any(value <= 0 for value in values):
        raise ValueError("Expected five positive observations")
    return {"median": median(values), "min": min(values), "max": max(values)}


def geometry(rows):
    values = {}
    for rate in (1, 10, 100):
        arms = [
            five([row for row in rows if row["mode"] == mode and row["per_mille"] == rate], "repeat")
            for mode in (0, 1)
        ]
        hard = SCALE // 1000 * rate
        for mode, workers in enumerate(arms):
            for row in workers:
                expected = (SCALE, hard if mode else 0, 0 if mode else hard,
                            hard if mode else 0, 0 if mode else hard, SCALE - hard)
                if tuple(row[k] for k in ("n", "fallbacks", "mismatches", "negative", "zero", "positive")) != expected:
                    raise ValueError("Pressure worker failed its exact sign and fallback census")
        values[str(rate)] = {
            "plain_binary64_s": stats([r["ns"] / 1e9 for r in arms[0]]),
            "filtered_exact_s": stats([r["ns"] / 1e9 for r in arms[1]]),
            "filtered_over_plain": stats([b["ns"] / a["ns"] for a, b in zip(*arms, strict=True)]),
            "fallbacks_per_filtered_worker": hard, "wrong_signs_per_binary64_worker": hard,
        }
    if len(rows) != 30:
        raise ValueError("Unexpected geometry pressure roster")
    return values


def timing(root):
    packet = root / PACKET
    values, table_cells, outliers = {}, {}, {}

    def store(name, result, shown=False):
        values[name] = result
        if shown:
            table_cells[name] = result
            midpoint = result["median"]
            if result["min"] < .7 * midpoint or result["max"] > 1.3 * midpoint:
                outliers[name] = result
        return result["median"]

    def arms(filename, arm_key, repeat, expected):
        grouped = defaultdict(list)
        for row in records(packet / filename):
            grouped[row[arm_key]].append(row)
        if set(grouped) != set(expected):
            raise ValueError(f"Unexpected arms in {filename}")
        return {arm: five(workers, repeat) for arm, workers in grouped.items()}

    reference = json.loads((root / "evidence/e6-o1-native-sqlite-single-file-100m/REFERENCE.json").read_bytes())
    expected_o1 = {"sqlite_native_read": reference["aggregate"], "sqlite_backup_only": reference["aggregate"],
                   "sqlite_backup_logical": reference["logical"], "raw_file_sha256": reference["physical"]}
    o1 = arms("O1-RAW.jsonl", "method", "repeat", expected_o1)
    medians = {}
    for method, workers in o1.items():
        if any(r["n"] != SCALE or r["valid"] is not True or r["result"] != expected_o1[method] for r in workers):
            raise ValueError(f"Wrong snapshot measurement result for {method}")
        medians[method] = store(f"O1.{method}.seconds", stats([r["wall_ns"] / 1e9 for r in workers]),
                                method != "sqlite_backup_only")
    for method in ("raw_file_sha256", "sqlite_backup_logical"):
        values[f"O1.{method}.over_native_read"] = medians[method] / medians["sqlite_native_read"]

    expected_o2 = {"producer": [100, 299991302], "exact": [SCALE, 0], "epoch": True}
    o2 = arms("O2-RAW.jsonl", "arm", "rep", expected_o2)
    medians = {}
    for arm, workers in o2.items():
        if any(r["result"] != expected_o2[arm] or r["duckdb"] != "1.4.3" for r in workers):
            raise ValueError(f"Wrong epoch measurement result for {arm}")
        medians[arm] = store(f"O2.{arm}.seconds", stats([r["wall_s"] for r in workers]), arm != "exact")
    values["O2.epoch.over_producer_pct"] = 100 * medians["epoch"] / medians["producer"]

    expected_epoch_controls = {
        "irrelevant_column": (True, 0, True), "rolled_back_relevant": (True, 0, True),
        "committed_relevant": (False, 1, False), "simulated_missed_token": (True, 1, False),
    }
    epoch_controls = json.loads((packet / "O2-CONTROLS.json").read_bytes())["result"]
    if {k: tuple(r[name] for name in ("epoch", "typed_diffs", "producer_equal"))
        for k, r in epoch_controls.items()} != expected_epoch_controls:
        raise ValueError("The epoch correctness controls did not reproduce")
    expected_topk = {"cases": 6, "rows": SCALE, "cutoff": 9999, "strict_winners": 1, "tied_members": 9975}
    expected_rep = {"cases": 6, "physical_rows": SCALE, "original_group_count": 100,
                    "allowed_distinct_tied_members": 9872}
    for filename, expected in (("TOPK", expected_topk), ("REP", expected_rep)):
        if json.loads((packet / f"{filename}-CONTROLS.json").read_bytes()) != expected:
            raise ValueError(f"The {filename} full-input census differs from the archive")

    for filename, prefix, third in (("TOPK", "O3.topk", "guard"), ("REP", "O3.representative", "claimed")):
        for arm, workers in arms(f"{filename}-RAW.jsonl", "arm", "rep", ("producer", "family", third)).items():
            if any(r["n"] != SCALE for r in workers):
                raise ValueError("O3 measurement did not cover the 100M source")
            prods = [r["wall_prod_ns"] / 1e9 for r in workers]
            checks = [r["wall_check_ns"] / 1e9 for r in workers]
            store(f"{prefix}.{arm}.producer_seconds", stats(prods), arm == "producer")
            if arm != "producer":
                store(f"{prefix}.{arm}.check_seconds", stats(checks), arm != "claimed")
                store(f"{prefix}.{arm}.total_seconds", stats([p + c for p, c in zip(prods, checks, strict=True)]))
                store(f"{prefix}.{arm}.check_over_producer", stats([c / p for p, c in zip(prods, checks, strict=True)]))
            elif checks != [0] * 5:
                raise ValueError("Producer-only worker unexpectedly records check time")

    geom_path = f"{PREVIOUS}/geometry-native/NEW-RAW.csv"
    geom = numeric_csv(root / geom_path)
    geom_arms = [five([r for r in geom if r["mode"] == mode], "rep") for mode in (1, 2, 3)]
    eager, filtered, plain = geom_arms
    if any(r["n"] != SCALE or r["mismatches"] for workers in geom_arms for r in workers):
        raise ValueError("Unexpected sign result in the native geometry panel")
    store("O4.binary64.seconds", stats([r["ns"] / 1e9 for r in plain]), True)
    store("O4.filtered.seconds", stats([r["ns"] / 1e9 for r in filtered]), True)
    store("O4.eager_over_filtered", stats([a["ns"] / b["ns"] for a, b in zip(eager, filtered, strict=True)]))

    o5_path = f"{PREVIOUS}/o5-data/COST-RAW.jsonl"
    o5 = records(root / o5_path)
    for size in (3, 1000, 100000):
        workers = five([r for r in o5 if r["overlay_rows"] == size], "repeat")
        if any(r["backing_rows"] != SCALE or r["pinned_cpu"] != 95 for r in workers):
            raise ValueError("O5 workers are from a different scale or host environment")
        store(f"O5.{size}.witness_over_apply", stats([r["witness_wall_ns"] / r["apply_wall_ns"] for r in workers]))
        store(f"O5.{size}.verify_seconds", stats([r["verify_wall_ns"] / 1e9 for r in workers]))
        if size == 3:
            for arm in ("apply", "witness"):
                store(f"O5.{size}.{arm}_seconds", stats([r[f"{arm}_wall_ns"] / 1e9 for r in workers]), True)
    return {"timing": values, "table7_time_cells": table_cells, "table7_cells_outside_30_pct": outliers}


def metrics(root):
    packet = root / PACKET
    values = timing(root)
    if values != json.loads((packet / "TABLE7-RESULT.json").read_bytes()):
        raise ValueError("Archived Table 7 summary does not match the worker receipts")
    sources = {"O1": "O1-RAW.jsonl", "O2": "O2-RAW.jsonl", "O3.topk": "TOPK-RAW.jsonl",
               "O3.representative": "REP-RAW.jsonl"}
    for label, value in values["timing"].items():
        oracle, *_ = label.split(".")
        if oracle in {"O1", "O2", "O3"}:
            name = ".".join(label.split(".")[:2]) if oracle == "O3" else oracle
            path = f"{PACKET}/{sources[name]}"
        elif oracle == "O4":
            if label != "O4.eager_over_filtered":
                continue
            path = f"{PREVIOUS}/geometry-native/NEW-RAW.csv"
        else:
            if not label.endswith(("witness_over_apply", "verify_seconds")):
                continue
            path = f"{PREVIOUS}/o5-data/COST-RAW.jsonl"
        unit = "seconds" if label.endswith("seconds") else "percent" if label.endswith("pct") else "ratio"
        yield (f"s69.table7.{label.lower()}", path, value, 5, unit,
               "Five fresh 8352V workers per arm. O1/O2 separate-arm comparisons divide medians. "
               "O3/O4/O5 paired comparisons take the median of paired ratios.")
    yield ("s69.table7.time_cells_outside_30_pct", f"{PACKET}/TABLE7-RESULT.json",
           values["table7_cells_outside_30_pct"], len(values["table7_time_cells"]), "displayed time cells",
           "Fresh same-host O1–O3 plus prior same-host O4 native and three-overlay O5. Ratios are not time cells.")

    pressure = geometry(numeric_csv(packet / "PRESSURE-RAW.csv"))
    for rate, value in pressure.items():
        yield (f"s69.o4.pressure.{rate}_per_mille.same_call", f"{PACKET}/PRESSURE-RAW.csv", value, 5,
               "worker pairs", "100M calls per worker. Same non-specialized caller and input sequence per arm.")

    ast_path = f"{PREVIOUS}/AST-RAW.jsonl"
    workers = records(root / ast_path)
    if (len(workers) != 580 or any(row["status"] != "ok" for row in workers)
            or len({(row["suite"], row["query"], row["repeat"]) for row in workers}) != 580):
        raise ValueError("Unexpected AST worker count")
    ast = json.loads((root / f"{PREVIOUS}/AST-SUMMARY.json").read_bytes())
    if ast["failures"] or ast["workers"] != len(workers) or ast["complete_windows"] != 116:
        raise ValueError("Archived AST worker roster was incomplete")
    yield ("s69.ast.successful_workers", ast_path, len(workers), 580, "fresh workers",
           "All 116 full-scale SQL windows completed five successful workers each.")

    q39_checker = runpy.run_path(str(packet / "q39_bound.py"))
    distance = json.loads((root / f"{PREVIOUS}/Q39-M5-DISTANCE.json").read_bytes())
    bound = q39_checker["verify_native"](packet / "Q39-STATS.csv.gz", packet / "q39-native",
                                       distance["source_parts_sha256"])
    stored = json.loads((packet / "Q39-RESULT.json").read_bytes())
    if stored != bound or bound["archived_projection_check"]["M5_hex"] != distance["mutant_hex"]:
        raise ValueError("Archived Q39 proof does not match the group statistics")
    original = json.loads((root / "evidence/e7-archived-native-replay-extension-10/packages"
                           / "tpcds-sf10-q39-exact-threshold/q39-result.json").read_bytes())
    for key, old_key in (("groups", "tested_jan_feb_groups"),
                         ("inventory_rows", "enumerated_nonnull_source_rows"),
                         ("paired_output_keys", "output_groups"),
                         ("min_nonzero_cv_squared_threshold_gap", "min_nonzero_abs_cv2_gap_to_threshold"),
                         ("exact_threshold_ties", "exact_equal_threshold_groups")):
        if bound[key] != original[old_key]:
            raise ValueError(f"Q39 group census differs from the independent original: {key}")
    yield ("s69.q39.max_cv_relative_bound", f"{PACKET}/Q39-STATS.csv.gz",
           bound["max_cv_relative_bound_fraction"], bound["groups"], "relative error, rational",
           "Order-independent analytic bound from exact integer groups and DuckDB 1.4.3 source.")
    yield ("s69.q39.threshold_ambiguous_groups", f"{PACKET}/Q39-STATS.csv.gz",
           bound["threshold_ambiguous_groups"], bound["groups"], "January/February groups",
           "Groups whose certified interval can alter the strict CV > 1 decision.")
