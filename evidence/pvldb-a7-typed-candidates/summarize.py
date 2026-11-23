"""Reconcile full ClickBench receipts with the A1 inventory and optional Arrow files."""

import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
from math import comb
from pathlib import Path
import re


PACKET = Path(__file__).resolve().parent
PHASE = re.compile(r"^(\S+) (download_exit=0|query_exit=0|id_cast_exit=0|cutoff_exit=0)$")


def jsonl(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def candidate_tables(directory, manifest):
    import pyarrow as pa

    names = {row["candidate"] for row in manifest.values()}
    if names != {path.name for path in directory.glob("*.arrow")}:
        raise ValueError("private Arrow roster differs from the capture manifest")
    tables = {}
    for key, row in manifest.items():
        payload = (directory / row["candidate"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != row["candidate_sha256"]:
            raise ValueError(f"candidate digest mismatch: {row['candidate']}")
        table = pa.ipc.open_file(payload).read_all()
        if (table.num_rows, table.num_columns) != (row["rows"], row["columns"]):
            raise ValueError(f"candidate shape mismatch: {row['candidate']}")
        tables[key] = table
    for q in range(1, 44):
        a, b = (tables[q, t] for t in (8, 1))
        if a.schema != b.schema:
            raise ValueError(f"thread-dependent Arrow schema: Q{q}")
        a_rows, b_rows = [list(zip(*(col.to_pylist() for col in table.columns))) for table in (a, b)]
        receipt = manifest[q, 1]
        if (a_rows == b_rows, Counter(a_rows) == Counter(b_rows)) != (
            receipt["same_order_as_first_arm"], receipt["same_bag_as_first_arm"],
        ):
            raise ValueError(f"thread comparison differs on recovered tables: Q{q}")


def phases(path):
    records = {}
    for line in path.read_text().splitlines():
        matched = PHASE.match(line)
        if matched:
            records[matched.group(2)] = datetime.fromisoformat(matched.group(1))
    entries = list(records.values())
    if len(entries) != 4 or entries != sorted(entries):
        raise ValueError("run log lacks a complete successful phase sequence")
    return {name: int((end - start).total_seconds()) for name, start, end in
            zip(("queries_and_checks", "id_cast", "cutoff_census"), entries, entries[1:])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--private-candidates", type=Path)
    args = parser.parse_args()
    inventory = {int(r["query"]): r for r in json.loads(args.inventory.read_bytes()) if r["suite"] == "clickbench"}
    acquisition = (PACKET / "FULL-ACQUISITION.json").read_bytes()
    acquisition_sha = hashlib.sha256(acquisition).hexdigest()
    shards = json.loads(acquisition)
    if [r["part"] for r in shards] != list(range(100)):
        raise ValueError("unexpected source acquisition roster")
    result = json.loads((PACKET / "FULL-RESULT.json").read_bytes())
    if (result["acquisition_sha256"], result["source_shards"], result["source_rows"],
        result["successful_queries_by_threads"]) != (acquisition_sha, len(shards), 99_997_497, {"1": 43, "8": 43}):
        raise ValueError("execution and acquisition receipts disagree")
    rows = jsonl(PACKET / "FULL-CANDIDATES.jsonl")
    manifest = {(r["query"], r["threads"]): r for r in rows}
    if len(rows) != 86 or set(manifest) != {(q, t) for q in range(1, 44) for t in (1, 8)}:
        raise ValueError("expected one capture per query and thread count")
    sql_fields = ("query", "threads", "status", "rows", "columns", "same_order_as_first_arm", "same_bag_as_first_arm")
    with (PACKET / "FULL-QUERIES.csv").open(newline="") as stream:
        ledger = {(int(row["query"]), int(row["threads"])): row for row in csv.DictReader(stream)}
    if ledger.keys() != manifest.keys():
        raise ValueError("unexpected query ledger roster")
    for key, r in manifest.items():
        if (
            any(ledger[key][name] != str(r[name]) for name in sql_fields)
            or r["candidate"] != f"q{r['query']:02d}-t{r['threads']}.arrow"
            or r["status"] != "ok"
            or r["acquisition_sha256"] != acquisition_sha
            or r["sql_sha256"] != inventory[r["query"]]["sql_sha256"]
        ):
            raise ValueError(f"capture, ledger, and SQL identity mismatch: {key}")
    if args.private_candidates:
        candidate_tables(args.private_candidates, manifest)
    window_rows = jsonl(PACKET / "FULL-CUTOFFS.jsonl")
    windows = {r["query"]: r for r in window_rows}
    if len(window_rows) != len(windows) or windows.keys() != {
        q for q, r in inventory.items() if r["top_limit"] and r["order_keys"]
    }:
        raise ValueError("cutoff census is missing a static ORDER BY/LIMIT query")
    for q, window in windows.items():
        if window["status"] != "verified" or window["sql_sha256"] != inventory[q]["sql_sha256"]:
            raise ValueError(f"cutoff execution or SQL changed for Q{q}")

    ordered = {q for (q, t), r in manifest.items() if t == 1 and not r["same_order_as_first_arm"]}
    bag = {q for (q, t), r in manifest.items() if t == 1 and not r["same_bag_as_first_arm"]}
    split = {q for q, r in windows.items() if r["lower_boundary_split"] or r["upper_boundary_split"]}
    family = result["two_independent_family_checks"]
    if not all(family["observed_membership"].values()):
        raise ValueError("independent source check failed")
    ids = json.loads((PACKET / "FULL-ID-CAST.json").read_bytes())
    if set(ids["columns"]) != {"WatchID", "UserID"} or ids["duckdb"] != result["duckdb"]:
        raise ValueError("wrong ID cast receipt")
    id_effects = {}
    for name, receipt in ids["columns"].items():
        check = receipt["exact_reference_and_native"]
        if check["population"] != result["source_rows"] or check["original_nulls"] != 0:
            raise ValueError(f"unexpected ID scan population: {name}")
        id_effects[name] = {
            "one_side_loss": {"numerator": check["unilateral_lost_pairs"],
                              "denominator": check["source_exact_nonnull_pairs"]},
            "both_sides_false_pairs": check["both_false_pairs"],
            "collided_exact_keys": check["collided_exact_keys"],
            "distinct_exact_keys": check["distinct"],
        }
    print(json.dumps({
        "source_shards": len(shards),
        "source_bytes": sum(r["bytes"] for r in shards),
        "source_rows": result["source_rows"],
        "candidate_count": len(manifest),
        "cutoff_census": {"tested_queries": sorted(windows), "split_queries": sorted(split)},
        "thread_comparison": {"different_order": sorted(ordered), "different_bag": sorted(bag),
                              "different_order_same_bag": sorted(ordered - bag),
                              "bag_difference_with_split_cutoff": sorted(bag & split)},
        "q25_projected_legal_bags": comb(family["q25_boundary_rows"], family["q25_available_boundary_slots"]),
        "id_effects": id_effects,
        "stage_wall_seconds": phases(PACKET / "FULL-RUN.log"),
        "queries": [
            {"query": q, "order_dependency": r["order_dependency"], "order_keys": r["order_keys"],
             "top_limit": r["top_limit"], "cutoff": windows.get(q), "different_order": q in ordered,
             "different_bag": q in bag, "native_rows": {t: manifest[q, t]["rows"] for t in (1, 8)}}
            for q, r in sorted(inventory.items())
        ],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
