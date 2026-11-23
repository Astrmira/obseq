"""Offline evidence check, with separately selectable native comparator replay."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from zoneinfo import reset_tzpath


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
MATRIX = EVIDENCE / "pvldb-native-baseline-matrix"
SCORER = EVIDENCE / "e7-original-native-one-command/bundle/e7-scored"
A2 = EVIDENCE / "pvldb-a2-q39-real-output/run.py"
E2 = EVIDENCE / "submission-e-series-native-evidence/e23/check.py"


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_files():
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        if expected != digest(ROOT / name):
            raise ValueError(f"artifact checksum mismatch: {name}")
    numbers = read(ROOT / "NUMBERS.json")["numbers"]
    for row in numbers:
        if row["source_sha256"] != digest(ROOT / row["artifact_path"]):
            raise ValueError(f"ledger source mismatch: {row['id']}")
    recount = runpy.run_path(str(ROOT / "scripts/recount_numbers.py"))
    recount["verify"](ROOT, numbers)
    return len(numbers)


def matrix_counts(rows):
    counts = defaultdict(Counter)
    for row in rows:
        for tool, result in (row["generic"] | row["tool_verdicts"]).items():
            outcome = "NA" if result is None else (
                ("true_" if result == row["legal"] else "false_") + ("accept" if result else "reject"))
            counts[tool][outcome] += 1
    return counts


def replay_receipts():
    verifier = runpy.run_path(str(SCORER / "check.py"))
    predicted = verifier["predictions"](read(SCORER / "BLIND.json"))
    if predicted != read(SCORER / "PREDICTIONS.json"):
        raise ValueError("original adjudication changed")
    original = read(MATRIX / "ORIGINAL-RESULT.json")
    later = read(MATRIX / "LATER-RESULT.json")
    later_rows = [row for row in later["observations"] if row["arm"] != "alternate_decimal_diagnostic"]
    if matrix_counts(original["observations"]) != original["counts"]:
        raise ValueError("original-108 summary changed")
    if matrix_counts(later_rows) != later["comparison_cell_summary_excluding_alternate_decimal"]:
        raise ValueError("later-138 summary changed")
    result = subprocess.check_output([sys.executable, "-B", str(MATRIX / "holdout_summary.py"), str(MATRIX)])
    if json.loads(result) != read(MATRIX / "HOLDOUT-MATRIX.json"):
        raise ValueError("holdout family matrix changed")
    for suffix in ("NATURAL", "NATURAL-EXTENDED"):
        natural = read(MATRIX / f"{suffix}-RESULT.json")
        for name, expected in natural["source_sha256"].items():
            if digest(EVIDENCE / name) != expected:
                raise ValueError(f"E9 source mismatch: {name}")
    roster = EVIDENCE / "pvldb-a4-natural-roster"
    result = subprocess.check_output([sys.executable, "-B", str(roster / "aggregate.py"), str(roster), str(MATRIX)])
    pair_summary = json.loads(result)
    if pair_summary != read(roster / "FAMILY-MATRIX.json"):
        raise ValueError("natural release-pair aggregate changed")
    verify_contracts = runpy.run_path(str(roster / "verify_contracts.py"))["audit"]
    c4 = verify_contracts(EVIDENCE)
    if c4 != read(roster / "CONTRACT-CHECKS.json"):
        raise ValueError("natural contract decisions changed")
    a1 = EVIDENCE / "pvldb-a1-query-inventory"
    summarize_controls = runpy.run_path(str(a1 / "summarize_controls.py"))["summarize"]
    windows = summarize_controls(a1)
    if windows != read(a1 / "SAME-CARDINALITY-SUMMARY.json"):
        raise ValueError("equal-length window control summary changed")
    epoch = EVIDENCE / "pvldb-a5-epoch-writer"
    result = subprocess.check_output([sys.executable, "-B", str(epoch / "contract_inventory.py"), str(EVIDENCE)])
    contracts = json.loads(result)
    if contracts != read(epoch / "CONTRACT-INVENTORY.json"):
        raise ValueError("contract source census changed")
    benchmark = read(MATRIX / "BENCHMARK-E5-RESULT.json")
    sensitivity = runpy.run_path(str(MATRIX / "merge_e5.py"))["key_sensitivity"]
    keys = read(MATRIX / "BENCHMARK-DATACOMPY-KEYS.json")
    if sensitivity(benchmark, keys) != keys:
        raise ValueError("DataComPy key sensitivity summary changed")
    q59 = read(MATRIX / "Q59-INDEPENDENT-RESULT.json")
    if {arm: row["accepted"] for arm, row in q59["decisions"].items()} != q59["typed_window_verdicts"]:
        raise ValueError("Q59 independent labels and typed verifier differ")
    timings = EVIDENCE / "e6-o1-native-sqlite-single-file-100m"
    output = subprocess.check_output([sys.executable, "-B", str(timings / "summarize.py"),
                                      str(timings / "RAW.jsonl")])
    if json.loads(output) != read(timings / "SUMMARY.json"):
        raise ValueError("archived SQLite timing summary changed")
    for cohort, totals in benchmark["totals"].items():
        rows = [{"generic": {}, "tool_verdicts": row["e5"], "legal": row["legal"]}
                for row in benchmark["observations"] if row["cohort"] == cohort]
        if matrix_counts(rows) != totals or any(len(row["tool_verdicts"]) != 16 for row in rows):
            raise ValueError(f"benchmark matrix summary changed for {cohort}")
    annotation = EVIDENCE / "e9-independent-annotation-and-adjudication"
    output = subprocess.check_output([sys.executable, "-B", str(annotation / "check.py")])
    if json.loads(output) != read(annotation / "RESULT.json"):
        raise ValueError("Paired public-issue annotation and adjudication summary changed")
    development = set()
    for file in EVIDENCE.glob("e7-*/MANIFEST.json"):
        for entry in read(file)["cases"]:
            development.add(entry["case_id"])
            for name, pinned in entry["blobs"].items():
                path = file.parent / "packages" / entry["case_id"] / name
                if digest(path) != pinned["sha256"]:
                    raise ValueError(f"development/transfer manifest mismatch: {entry['case_id']}/{name}")
    return {"original_contracts_replayed": len(predicted),
            "public_issue_model_annotations_replayed": 300,
            "later_cases_recounted": len({(r["panel"], r["id"]) for r in later_rows}),
            "natural_release_pairs_recounted": pair_summary["release_pairs"],
            "natural_contract_arms_replayed": len(c4["observations"]),
            "equal_length_window_controls_recounted": windows["equal_length_controls_rejected"],
            "benchmark_comparisons_recounted": len(benchmark["observations"]),
            "development_contracts_recounted": sum(contracts["counts"]["development"].values()),
            "development_and_transfer_package_ids_verified": len(development)}


def replay_comparators():
    invocations = (
        ("original.py", [SCORER, MATRIX / "ORIGINAL-REFERENCES.json", A2, E2], "ORIGINAL"),
        ("later.py", [EVIDENCE, EVIDENCE / "pvldb-a3-independent-panel/run.py",
                      EVIDENCE / "pvldb-a3-heldout-value-observers/run.py", A2, E2], "LATER"),
        ("natural.py", [EVIDENCE, A2, E2], "NATURAL"),
        ("natural_extension.py", [EVIDENCE, A2, E2], "NATURAL-EXTENDED"),
    )
    env = {**os.environ, "PYTHONTZPATH": str(ROOT / "zoneinfo")}
    for program, args, name in invocations:
        output = subprocess.check_output([sys.executable, "-B", str(MATRIX / program), *map(str, args)], env=env)
        if json.loads(output) != read(MATRIX / f"{name}-RESULT.json"):
            raise ValueError(f"native comparator replay changed for {name}")
    sys.path.insert(0, str(EVIDENCE / "pvldb-a1-query-inventory"))
    import duckdb
    import pyarrow as pa
    from verify_windows import call

    with duckdb.connect() as db:
        db.execute("CREATE TABLE t (id VARCHAR, k INTEGER); INSERT INTO t VALUES ('a', 2), ('b', 1), ('c', 1)")
        query = "SELECT id FROM t ORDER BY k DESC LIMIT 2"
        arms = {name: pa.table({"id": values}) for name, values in (
            ("native", ["a", "b"]), ("peer", ["a", "c"]), ("absent", ["a", "Z"]),
            ("duplicate", ["a", "a"]), ("order", ["b", "a"]),
        )}
        accepted = {name for name, verdict in call(db, query, arms).items() if verdict["accepted"]}
        if accepted != {"native", "peer"}:
            raise ValueError("typed ordered window smoke test changed")
        db.execute("CREATE TABLE ci (v VARCHAR COLLATE NOCASE, k INTEGER); "
                   "INSERT INTO ci VALUES ('A', 1), ('z', 2)")
        query = "SELECT v FROM ci ORDER BY k LIMIT 1"
        variants = {letter: pa.table({"v": [letter]}) for letter in ("A", "a", "z")}
        if {k for k, v in call(db, query, variants).items() if v["accepted"]} != {"A"}:
            raise ValueError("projected text identity inherited NOCASE")
        db.execute("INSERT INTO ci VALUES ('a', 1)")
        if {k for k, v in call(db, query, variants).items() if v["accepted"]} != {"A", "a"}:
            raise ValueError("case-sensitive legal peer membership changed")


def replay_native_archive(bindings, system_python, scratch, timeout):
    """Run the pinned producer archive with isolated per-case scratch directories."""
    if not bindings.is_file():
        raise FileNotFoundError(bindings)
    runner = EVIDENCE / "e7-archived-native-replay-extension-10/replay-all.py"
    command = [sys.executable, "-IB", str(runner), "--inputs", str(bindings.resolve()),
               "--system-python", str(system_python), "--json"]
    if scratch is not None:
        command.extend(("--scratch", str(scratch)))
    if timeout is not None:
        command.extend(("--timeout", str(timeout)))
    result = subprocess.run(command, stdout=subprocess.PIPE, text=True)
    records = [json.loads(line) for line in result.stdout.splitlines()]
    if len(records) != 101 or len({r["id"] for r in records}) != 101:
        raise ValueError(f"archive runner returned {len(records)} of the 101 expected statuses")
    counts = Counter(r["status"] for r in records)
    return {"status_counts": counts, "skipped_missing_inputs": counts["NA_input_binding"],
            "records": records}, result.returncode == 0 and set(counts) <= {
                "PASS", "PASS_stable", "NA_input_binding"}


def replay_original_producers(environment):
    packet = EVIDENCE / "e7-original-native-one-command"
    output = subprocess.check_output([sys.executable, "-B", str(packet / "replay.py"), str(environment.resolve())])
    if json.loads(output) != read(packet / "RESULT.json"):
        raise ValueError("original producer replay changed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparators", action="store_true", help="rerun pinned E2/E5 tools and the A1 smoke test")
    parser.add_argument("--native-inputs", type=Path, help="replay the 101 archived packages using named local input roles")
    parser.add_argument("--original-environment", type=Path, help="replay the original 108 native producers")
    parser.add_argument("--system-python", type=Path,
                        default=Path(os.environ.get("OBSEQ_SYSTEM_PYTHON", "/usr/bin/python3")))
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--timeout", type=int, help="override individual native producer timeouts in seconds")
    args = parser.parse_args()
    reset_tzpath([str(ROOT / "zoneinfo")])
    entries = verify_files()
    summary = {"numbers_sources_verified": entries, **replay_receipts()}
    if args.comparators:
        replay_comparators()
        summary["native_comparator_matrices_replayed"] = 4
        summary["typed_window_smoke_test"] = "passed"
    if args.original_environment:
        replay_original_producers(args.original_environment)
        summary["original_native_producers"] = "replayed"
    success = True
    if args.native_inputs:
        summary["native_archive"], success = replay_native_archive(
            args.native_inputs, args.system_python, args.scratch, args.timeout)
    print(json.dumps(summary, sort_keys=True, indent=2))
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
