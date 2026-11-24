"""Recount the second-review measurements from individual sealed observations."""

from collections import Counter, defaultdict
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import runpy
from statistics import median
import struct


PACKET = "evidence/pvldb-s68-review-followup"


def metrics(root):
    packet = root / PACKET
    results = []

    def read(path):
        return json.loads((root / path).read_bytes())

    def add(name, filename, value, denominator, unit, scope):
        results.append((name, f"{PACKET}/{filename}", value, denominator, unit, scope))

    for name in ("M1", "M2", "DVC", "SPREADSHEET"):
        for line in (packet / f"{name}-PREEXECUTION.sha256").read_text().splitlines():
            digest, filename = line.split("  ", 1)
            if hashlib.sha256((packet / filename).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Pre-execution code or plan changed for {name}/{filename}")

    rows = read(f"{PACKET}/M1-RESULT.json")["observations"]
    if len({r["id"] for r in rows}) != 42:
        raise ValueError("The C1/C2 same-information roster must contain 42 distinct arms")
    for method in ("obseq_accepts", "python_assert_accepts", "dbt_singular_accepts", "dbt_stock_source_freshness"):
        counts = Counter(dict.fromkeys(("true_accept", "true_reject", "false_accept", "false_reject", "not_applicable"), 0))
        for row in rows:
            verdict = row[method]
            if verdict is None:
                counts["not_applicable"] += 1
                continue
            accepted = verdict == "pass" if isinstance(verdict, str) else verdict
            label = "true_" if row["legal"] == accepted else "false_"
            counts[label + ("accept" if accepted else "reject")] += 1
        add(f"s68.m1.{method}", "M1-RESULT.json", dict(counts), len(rows), "paired execution arms",
            "C1 F3/F4/F5 and all 12 C2 pairs. Explicit identical witnesses for the three assertion arms. "
            "Stock freshness checks recent loaded_at timestamps on F4 and C2, with F3/F5 inapplicable.")

    dvc = read(f"{PACKET}/DVC-RESULT.json")
    observations = dvc["observations"]
    actual = {"cases": len(observations),
              "tracked_changed": sum("tracked" in r["after_change"] for r in observations),
              "omitted_changed": sum("omitted" in r["after_change"] for r in observations)}
    if actual != dvc["summary"] or any(r["before_change"] or r["after_tracked_repro"] or
            r["refreshed_output"] != r["expected_output"] for r in observations):
        raise ValueError("DVC native status/repro receipts disagree")
    add("s68.m1.dvc_dependency_invalidation", "DVC-RESULT.json", actual, len(observations), "native DVC stages",
        "Three WAL changes and three UDF definition changes, with and without explicitly declared dependencies.")

    binding = read(f"{PACKET}/M2-RESULT.json")
    rows = binding["results"]
    if Counter(r["family"] for r in rows) != {"O1": 6, "O2": 9, "O5": 6}:
        raise ValueError("Unexpected binding-injection roster")
    for arm in ("execution_bound", "request_layer"):
        counts = Counter(dict.fromkeys(("true_accept", "true_reject", "false_accept", "false_reject"), 0))
        for row in rows:
            accepted = row[f"{arm}_accept"]
            if accepted != (row[f"{arm}_witness"] == row["reference"]):
                raise ValueError("Binding verdict differs from its recorded witness")
            label = "true_" if row["legal"] == accepted else "false_"
            counts[label + ("accept" if accepted else "reject")] += 1
        add(f"s68.m2.{arm}", "M2-RESULT.json", dict(counts), len(rows), "native SQLite execution arms",
            "12 binding faults and 9 legal controls across O1 snapshot handles, O2 commit/epoch coupling and O5 intent.")
    crash = [r for r in rows if r["execution"] == "crash_after_write"]
    if len(crash) != 3 or any(r["injected_process_exit"] != 73 for r in crash):
        raise ValueError("Missing real subprocess crash injections")

    sheet = read(f"{PACKET}/SPREADSHEET-RESULT.json")
    rows = sheet["observations"]
    if len({r["task"] for r in rows}) != 19 or not all(r["gold_self_comparison"] for r in rows):
        raise ValueError("Spreadsheet task roster or original self-comparison changed")
    for mode in ("openpyxl_save", "isolated_cell"):
        both = sum(all(v[mode] for v in r["comparisons"].values()) for r in rows)
        add(f"s68.spreadsheet.{mode}.both_mutually_exclusive_formulas_accepted", "SPREADSHEET-RESULT.json",
            both, len(rows), "tasks", "Pinned stock grader accepts both =1000000000 and =-1000000000 "
            "without recalculation. At least one candidate per task is wrong independently of the unknown gold value.")
    add("s68.spreadsheet.populated_cache_controls_rejected", "SPREADSHEET-RESULT.json",
        sum(not r["populated_cache_control_accepts"] for r in rows), len(rows), "tasks",
        "A populated string-cache control at the same edited cell is rejected by the pinned stock grader.")

    module = runpy.run_path(str(packet / "sources.py"))
    full_labels = module["labels"](root / "evidence")
    positives = [{key: row[key] for key in ("id", "url", "category")}
                 for row in full_labels.values() if row["status"] == "yes"]
    if positives != read(f"{PACKET}/E9-ADJUDICATED-POSITIVES.json")["positive_rows"]:
        raise ValueError("The positive slice differs from the original paired ratings and adjudication")
    c4 = module["render"](root / "evidence", read(f"{PACKET}/C4-UPSTREAM-LOOKUP.json"))
    if c4 != read(f"{PACKET}/C4-SOURCES.json") or module["markdown"](c4) != (packet / "C4-SOURCES.md").read_text(encoding="utf-8"):
        raise ValueError("Rendered C4 source table changed")
    add("s68.c4.e9_positive_links", "C4-SOURCES.json", c4["summary"]["linked_distinct_positive_issues"],
        c4["summary"]["e9_positive_count"], "frozen positive public issues",
        "Distinct frozen E9 positive labels whose IDs and issue URLs match a native C4 release-pair family.")
    add("s68.c4.release_pairs_with_fix_link", "C4-SOURCES.json", c4["summary"]["release_pairs_with_fix_link"],
        c4["summary"]["release_pairs"], "release pairs", "Verified upstream merged-PR links. DuckDB issue 21207 remains unresolved.")

    queue_rows = list(csv.DictReader((packet / "E9-HUMAN-REVIEW-QUEUE.tsv").read_text(encoding="utf-8").splitlines(), delimiter="\t"))
    valid_statuses = {"yes", "no", "unknown"}
    valid_classes = {*(f"F{i}" for i in range(1, 11)), "O3", "O4", "other", "unknown"}
    if [(r["id"], r["issue_url"]) for r in queue_rows] != [(r["id"], r["url"]) for r in positives]:
        raise ValueError("Human review queue roster differs from the 82 frozen E9 positives")
    for row in queue_rows:
        if any(not (row[k] or "").strip() for k in row):
            raise ValueError(f"Incomplete human review entry: {row['id']}")
        if row["human_wrong_result"] not in valid_statuses or row["human_category"] not in valid_classes:
            raise ValueError(f"Invalid human review label: {row['id']}")
    human_status = Counter(dict.fromkeys(("yes", "no", "unknown"), 0))
    human_status.update(r["human_wrong_result"] for r in queue_rows)
    confirmed_pairs = [(r, p) for r, p in zip(queue_rows, positives, strict=True) if r["human_wrong_result"] == "yes"]
    cond_class_agree = sum(r["human_category"] == p["category"] for r, p in confirmed_pairs)
    joint_agree = sum(r["human_wrong_result"] == "yes" and r["human_category"] == p["category"]
                      for r, p in zip(queue_rows, positives, strict=True))
    confirmed_classes = Counter(dict.fromkeys([*(f"F{i}" for i in range(1, 11)), "O3", "O4", "other"], 0))
    confirmed_classes.update(r["human_category"] for r, _ in confirmed_pairs)
    add("s68.e9.human_review.status_counts", "E9-HUMAN-REVIEW-QUEUE.tsv", dict(human_status), len(queue_rows),
        "reviewed model-adjudicated positives",
        "Human review of all 82 frozen E9 positives against upstream discussions, fixes and reproductions.")
    add("s68.e9.human_review.wrong_result_agreement", "E9-HUMAN-REVIEW-QUEUE.tsv", human_status["yes"], len(queue_rows),
        "reviewed model-adjudicated positives",
        "Frozen model-adjudicated positives confirmed as evidenced wrong results by human review.")
    add("s68.e9.human_review.conditional_class_agreement", "E9-HUMAN-REVIEW-QUEUE.tsv", cond_class_agree,
        len(confirmed_pairs), "human-confirmed wrong results",
        "Primary mechanism class agreement among human-confirmed wrong-result issues.")
    add("s68.e9.human_review.joint_agreement", "E9-HUMAN-REVIEW-QUEUE.tsv", joint_agree, len(queue_rows),
        "reviewed model-adjudicated positives",
        "Exact joint agreement on both wrong-result confirmation and primary mechanism class across all 82 positives.")
    add("s68.e9.human_review.confirmed_classes", "E9-HUMAN-REVIEW-QUEUE.tsv", dict(confirmed_classes),
        len(confirmed_pairs), "human-confirmed wrong results",
        "Human-verified primary mechanism class distribution among the confirmed wrong-result issues.")

    table = runpy.run_path(str(packet / "table7_timings.py"))["summarize"](root / "evidence")
    if table != read(f"{PACKET}/TABLE7-ARCHIVED.json"):
        raise ValueError("Archived worker timings changed")
    for oracle, arms in table["timing"].items():
        for arm, times in arms.items():
            add(f"s68.table7.{oracle.lower()}.{arm}", "TABLE7-ARCHIVED.json", times,
                table["workers_per_cell"], "worker measurements",
                "Archived 100M-row/call workers. Every metric includes median and min/max. Ratios use paired workers.")

    raw = list(csv.DictReader((packet / "geometry-pressure/RAW.csv").read_text().splitlines()))
    cells = defaultdict(list)
    for row in raw:
        cells[int(row["per_mille"]), int(row["mode"])].append({k: int(v) for k, v in row.items()})
    if set(cells) != {(rate, mode) for rate in (1, 10, 100) for mode in range(3)}:
        raise ValueError("Incomplete geometry pressure matrix")
    for (rate, mode), workers in sorted(cells.items()):
        if sorted(r["repeat"] for r in workers) != list(range(5)) or any(r["n"] != 100_000_000 for r in workers):
            raise ValueError("Incomplete geometry pressure worker roster")
        expected_errors = rate * 100_000 if mode == 0 else 0
        expected_fallbacks = rate * 100_000 if mode == 1 else 0
        if any(r["mismatches"] != expected_errors or r["fallbacks"] != expected_fallbacks for r in workers):
            raise ValueError("Pressure predicate outcomes differ from analytic exact signs")
        value = {"wall_s": {"median": median(r["ns"] for r in workers) / 1e9,
                            "min": min(r["ns"] for r in workers) / 1e9,
                            "max": max(r["ns"] for r in workers) / 1e9},
                 "wrong_signs_per_run": expected_errors, "fallbacks_per_run": expected_fallbacks}
        add(f"s68.o4.pressure.{rate}_per_mille.mode{mode}", "geometry-pressure/RAW.csv", value,
            100_000_000, "predicate calls per worker", "Five authored pressure workers per cell. "
            "Modes 0/1/2 are binary64, filtered exact and eager exact. Shared remote host.")

    distance = read(f"{PACKET}/Q39-M5-DISTANCE.json")
    def bits(value):
        return struct.unpack(">Q", struct.pack(">d", value))[0]
    reference = float(Fraction(distance["exact_reference"]))
    original = float.fromhex(distance["native_1_thread_hex"])
    mutated = original * float.fromhex(distance["scale_factor_hex"])
    ulps = abs(bits(mutated) - bits(reference))
    if mutated.hex() != distance["mutant_hex"] or ulps != distance["distance_from_rounded_reference_ulp"]:
        raise ValueError("Q39 M5 mutation arithmetic changed")
    outside = ulps - distance["rounding_envelope_ulp"]
    if outside != distance["distance_outside_envelope_ulp"]:
        raise ValueError("Q39 envelope distance changed")
    add("s68.q39.m5.distance_outside_envelope_ulp", "Q39-M5-DISTANCE.json", outside,
        distance["rounding_envelope_ulp"], "binary64 representable steps",
        "Existing SF10 M5 mutation changes the January mean at warehouse/item (1,259), with exact reference 1093/4.")

    for name, value, denominator, unit, path, scope in existing_numbers(root):
        results.append((name, path, value, denominator, unit, scope))
    results.extend(runtime_metrics(root))
    return results


def runtime_metrics(root):
    packet = root / PACKET
    summarize = runpy.run_path(str(packet / "summarize_ast.py"))["summarize"]
    ast = summarize(packet / "AST-PROVENANCE.json", packet / "AST-RAW.jsonl")
    if ast != json.loads((packet / "AST-SUMMARY.json").read_bytes()):
        raise ValueError("Published AST timing summary differs from its workers")
    if ast["workers"] != 580 or ast["complete_windows"] != 116 or ast["failures"]:
        raise ValueError("Full-window timing has incomplete or failed workers")
    yield ("s68.ast.completed_windows", f"{PACKET}/AST-RAW.jsonl", ast["complete_windows"], 116,
           "SQL windows", "Five fresh full-scale workers per window, TPC SF10 and all publisher ClickBench partitions.")
    for name, value in ast["distribution"].items():
        unit = "nanoseconds" if name.endswith("_ns") else "KiB" if name.endswith("_kib") else "ratio"
        yield (f"s68.ast.{name}", f"{PACKET}/AST-RAW.jsonl", value, 116, unit,
               "Median, interpolated p90 and max across per-window five-worker medians. "
               "Unchanged validator recomputes candidates. Staged phases reuse a separately materialized relation. "
               "Shared remote host, no system cache drop. RSS includes producer allocations.")
    profiles = {"slowest_validator": ast["slowest_validator"],
                "largest_candidate": ast["largest_candidate"],
                "largest_boundary_peer_group": ast["largest_boundary_peer_group"],
                "clickbench_q32": next(r for r in ast["per_query"] if r["suite"] == "clickbench" and r["query"] == 32),
                "max_relative_overhead_window": max(ast["per_query"], key=lambda r: r["validator_over_producer"])}
    for name, value in profiles.items():
        yield (f"s68.ast.{name}", f"{PACKET}/AST-RAW.jsonl", value, 116, "per-window profiles",
               "Five-worker median times, candidate and peer counts for the required slow/large-window analysis.")

    geometry_path = f"{PACKET}/geometry-native/NEW-RAW.csv"
    geometry = packet / "geometry-native"
    provenance = json.loads((geometry / "MEASUREMENT-PROVENANCE.json").read_bytes())
    for filename, expected in provenance["executed_code_sha256"].items():
        if hashlib.sha256((geometry / filename).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Native geometry code differs from its executed source: {filename}")
    seed = json.loads((geometry / "SEED-RESULT.json").read_bytes())
    if seed["native_wedges_sha256"] != provenance["native_wedges_sha256"]:
        raise ValueError("Native geometry timing uses different seed wedges")
    rows = [{k: int(v) for k, v in row.items()} for row in csv.DictReader((root / geometry_path).read_text().splitlines())]
    if len(rows) != 20 or {r["mode"] for r in rows} != set(range(4)):
        raise ValueError("Incomplete native geometry matrix")
    arms = {}
    for mode, label in enumerate(("generation_checksum", "eager_exact", "filtered_exact", "pure_binary64")):
        workers = [r for r in rows if r["mode"] == mode]
        if sorted(r["rep"] for r in workers) != list(range(5)) or any(r["n"] != 100_000_000 for r in workers):
            raise ValueError("Bad native geometry worker roster")
        if any(r["mismatches"] or r["fallback"] != (21744 if mode == 2 else 0) for r in workers):
            raise ValueError("Native geometry exact-reference checks changed")
        arms[mode] = {r["rep"]: r for r in workers}
        value = {"wall_s": {"median": median(r["ns"] for r in workers) / 1e9,
                            "min": min(r["ns"] for r in workers) / 1e9,
                            "max": max(r["ns"] for r in workers) / 1e9},
                 "fallbacks_per_run": 21744 if mode == 2 else 0, "wrong_signs_per_run": 0}
        yield (f"s68.o4.native.{label}", geometry_path, value, 100_000_000, "predicate calls per worker",
               "Five rotated workers on the original native wedges. AST and O5 pilot measurements finished before this series.")
    ratios = [arms[2][rep]["ns"] / arms[3][rep]["ns"] for rep in range(5)]
    value = {"median_within_repeat": median(ratios), "min": min(ratios), "max": max(ratios),
             "ratio_of_medians": median(r["ns"] for r in arms[2].values()) / median(r["ns"] for r in arms[3].values())}
    yield ("s68.o4.native.filtered_over_plain_float", geometry_path, value, 5, "worker pairs",
           "Filtered exact predicate versus ordinary binary64 on identical inputs, with fixed compiler flags and rotated arm order.")

    o5_path = f"{PACKET}/o5-data/COST-RAW.jsonl"
    o5 = packet / "o5-data"
    archived, rebuilt = (json.loads((o5 / name).read_bytes()) for name in ("LAYOUT-100M.json", "LAYOUT-NEW.json"))
    if any(archived[k] != rebuilt[k] for k in ("csv_sha256", "total", "buckets", "arrow")):
        raise ValueError("O5 regenerated input differs from the complete archived CSV content")
    def manifest(name):
        return {filename: digest for digest, filename in
                (line.split("  ", 1) for line in (o5 / name).read_text().splitlines())}
    old_files, new_files = manifest("ARCHIVED-INPUT.sha256"), manifest("REGENERATED-INPUT.sha256")
    binding = json.loads((o5 / "BINDING-RESULT.json").read_bytes())
    if len(new_files) != 100 or old_files.keys() != new_files.keys() or new_files != binding["regenerated_files_sha256"]:
        raise ValueError("O5 regenerated file seal is incomplete")
    if old_files == new_files or binding["archived_parquet_byte_hashes_match"]:
        raise ValueError("O5 byte-different Parquet reproduction must be labeled explicitly")
    provenance = json.loads((o5 / "MEASUREMENT-PROVENANCE.json").read_bytes())
    for filename, source in (("o5_cost.py", packet / "o5_cost.py"), ("archived-o5.py", o5 / "archived-o5.py")):
        if hashlib.sha256(source.read_bytes()).hexdigest() != provenance["executed_code_sha256"][filename]:
            raise ValueError(f"O5 code differs from its executed source: {filename}")
    if hashlib.sha256((o5 / "REGENERATED-INPUT.sha256").read_bytes()).hexdigest() != provenance["input_manifest_sha256"]:
        raise ValueError("O5 timing input manifest differs from its pre-execution seal")
    rows = [json.loads(line) for line in (root / o5_path).read_bytes().splitlines()]
    if len(rows) != 15 or {r["overlay_rows"] for r in rows} != {3, 1000, 100000}:
        raise ValueError("Incomplete sparse-overlay scaling matrix")
    archived_driver = hashlib.sha256((o5 / "archived-o5.py").read_bytes()).hexdigest()
    for size in (3, 1000, 100000):
        workers = [r for r in rows if r["overlay_rows"] == size]
        if any(r["archived_driver_sha256"] != archived_driver or r["duckdb"] != "1.4.3" for r in workers):
            raise ValueError("O5 timing uses a different archived implementation or engine version")
        if sorted(r["repeat"] for r in workers) != list(range(5)) or any(r["backing_rows"] != 100_000_000 for r in workers):
            raise ValueError("Bad O5 sparse timing worker roster")
        times = {}
        for stage in ("apply", "witness", "verify"):
            samples = [r[f"{stage}_wall_ns"] / 1e9 for r in workers]
            times[f"{stage}_s"] = {"median": median(samples), "min": min(samples), "max": max(samples)}
        times["receipt_rows"] = sorted({r["receipt_rows"] for r in workers})
        times["witness_over_apply"] = median(r["witness_wall_ns"] / r["apply_wall_ns"] for r in workers)
        times["peak_rss_kib"] = {"median": median(r["peak_rss_kib"] for r in workers),
                                  "max": max(r["peak_rss_kib"] for r in workers)}
        yield (f"s68.o5.overlay_{size}", o5_path, times, 100_000_000, "backing rows",
               "Five rotated fresh workers with KEEP, CLEAR, equal-value WRITE and changed-value WRITE. "
               "Full verification builds an independent oracle and scans all backing rows. "
               "Rebuilt CSV SHA256 and partition counts match the archive. Parquet bytes are sealed separately.")


def existing_numbers(root):
    def read(path):
        return json.loads((root / path).read_bytes())
    path = "evidence/remote-calc-recalculation/RESULT.json"
    calc = read(path)
    for key in ("no_formula", "frozen_manifest_active_scope", "formula_or_package_admission"):
        yield (f"s68.spreadsheet.exclusions.{key}", calc["statuses"]["total"][key], calc["source_paths"],
               "source workbook paths", path, "Frozen Calc admission exclusions before formula-cache comparison.")
    total = calc["counts"]["total"]
    yield ("s68.spreadsheet.missing_recalculated_cache", total["missing_or_untyped_recalculated"],
           total["physical_formulas"], "formula cells", path, "Residual missing/untyped value after Calc recalculation.")
    path = "evidence/pvldb-a10-spreadsheetbench-scorer/RESULT.json"
    scorer = read(path)
    value = {name: group["intersecting_workbooks_pass_to_fail"] for name, group in scorer["groups"].items()}
    if sum(value.values()) != scorer["grader_transitions"]["pass -> fail"]:
        raise ValueError("Spreadsheet pass-to-fail reasons do not reconcile")
    yield ("s68.spreadsheet.pass_to_fail_reasons", value, sum(value.values()), "targeted workbooks", path,
           "25 missing-cache cases and one TEXTAFTER case among the 26 original-to-recalculated grading changes.")
    path = "evidence/e7-archived-native-replay-extension-10/packages/tpcds-sf10-q39-exact-threshold/q39-result.json"
    q39 = read(path)
    yield ("s68.q39.exact_threshold_ties", q39["exact_equal_threshold_groups"], q39["tested_jan_feb_groups"],
           "January/February groups", path, "SF10 exact rational threshold census over all tested groups.")
    path = "evidence/e6-cross-scale-and-ratio-audit/RESULT.json"
    o5 = read(path)["endpoint_stages"]["O5"]
    yield ("s68.o5.archived_overlay_writes", o5["overlay_writes"], o5["endpoint"], "sparse overlay rows", path,
           "Archived Table 7 applies three overlays over a 100M-row immutable backing relation and records four intents.")
    path = "evidence/pvldb-a1-query-inventory/SAME-CARDINALITY-SUMMARY.json"
    control = read(path)
    value = control["shape_controls_rejected"] + control["equal_length_controls_rejected"]
    yield ("s68.ast.negative_controls_rejected", value, value, "authored candidate outputs", path,
           "201 shape controls plus 549 equal-cardinality membership, multiplicity and ordering controls.")


if __name__ == "__main__":
    print(json.dumps(metrics(Path(__file__).resolve().parents[2]), indent=2))
