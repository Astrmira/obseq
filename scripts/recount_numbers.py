"""Recount the paper's supplemental ledger entries from sealed public receipts."""

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
from functools import cache
import hashlib
import json
from pathlib import Path
import re
from statistics import median


ROOT = Path(__file__).resolve().parents[1]
MATRIX = "evidence/pvldb-native-baseline-matrix"


def comparison_counts(rows, verdicts):
    counts = defaultdict(Counter)
    for row in rows:
        for method, verdict in row[verdicts].items():
            label = "legal" if row["legal"] else "illegal"
            counts[method][f"{label}_applicable" if verdict is not None else f"{label}_na"] += 1
            if row["legal"] and verdict is False:
                counts[method]["false_reject"] += 1
            if not row["legal"] and verdict is True:
                counts[method]["false_accept"] += 1
    return {
        method: {**dict.fromkeys(("false_reject", "false_accept"), 0), **count}
        for method, count in sorted(counts.items())
    }


def recount(root=ROOT):
    rows = {}

    @cache
    def source(path):
        return (root / path).read_bytes()

    def read(path):
        return json.loads(source(path))

    def add(id_, path, value, denominator, unit, scope):
        if id_ in rows:
            raise ValueError(f"Duplicate paper metric: {id_}")
        rows[id_] = {
            "id": id_, "value": value, "denominator": denominator,
            "unit": unit, "scope": scope, "artifact_path": path,
            "source_sha256": hashlib.sha256(source(path)).hexdigest(),
            "replay": f"python -B scripts/recount_numbers.py {id_}",
        }

    path = "evidence/pvldb-a4-natural-roster/CONTRACT-CHECKS.json"
    arms = read(path)["observations"]
    counts = Counter((row["historical_legal"], row["contract_accepts"]) for row in arms)
    if set(counts) != {(True, True), (False, False)}:
        raise ValueError("C4 contract decisions disagree with the frozen labels")
    for metric, value, denominator in (
        ("arms_scored", len(arms), len(arms)),
        ("legal_arms_accepted", counts[True, True], sum(row["historical_legal"] for row in arms)),
        ("faulty_arms_rejected", counts[False, False], sum(not row["historical_legal"] for row in arms)),
    ):
        add(f"c4.contract_replay.{metric}", path, value, denominator, "archived arms",
            "Section 3 and Table 6. Case-specific contract decisions over archived native projections.")

    path = "evidence/PUBLIC-DOCKER-VALIDATION.json"
    native = read(path)["native_archive"]
    statuses = Counter(row["status"] for row in native["records"])
    receipt_only = sum(row["kind"] == "receipt_only" and row["status"] == "PASS"
                       for row in native["records"])
    if statuses != native["status_counts"] or len({row["id"] for row in native["records"]}) != 101:
        raise ValueError("Public CI receipt has inconsistent native archive counts")
    for metric, value in (
        ("completed", statuses["PASS"] + statuses["PASS_stable"]),
        ("native_reexecuted", statuses["PASS"] + statuses["PASS_stable"] - receipt_only),
        ("receipt_only", receipt_only), ("pass_exact", statuses["PASS"]),
        ("pass_stable", statuses["PASS_stable"]), ("missing_optional_inputs", statuses["NA_input_binding"]),
        ("failed", sum(count for status, count in statuses.items() if status.startswith("FAIL_"))),
    ):
        add(f"a8.native.public_docker.{metric}", path, value, len(native["records"]), "archive entries",
            "Section 3. GitHub Actions Linux/amd64, network disabled, empty external input map.")

    path = "evidence/e6-cross-scale-and-ratio-audit/RESULT.json"
    stages = read(path)["endpoint_stages"]
    topk = stages["O3-topk"]["by_scope"]["100000000"]
    guard, family = (topk[arm]["vmhwm_kib"] / 1024 for arm in ("guard", "family"))
    for arm, resident in (("guard", guard), ("family", family)):
        add(f"e6.o3.topk_{arm}_peak_rss", path, round(resident), topk[arm]["repeats"], "MiB",
            "Section 7. Median peak resident memory (VmHWM), converted from KiB and rounded to MiB.")
    add("e6.o3.topk_guard_memory_reduction", path, 100 * (family - guard) / family,
        family, "percent", "Section 7. Reduction relative to the explicit family's median MiB.")
    geom = stages["O4"]
    eager, filtered, baseline = (geom["arm"][name]["wall_seconds"]
                                 for name in ("eager_exact", "lazy_filtered", "generation_checksum"))
    add("e6.o4.eager_vs_generate", path, eager / baseline, baseline, "times",
        "Section 7 and Table 7. Eager exact median seconds divided by generation/checksum median seconds.")
    add("e6.o4.filtered_speedup_vs_eager", path, eager / filtered, filtered, "times",
        "Sections 1 and 7. Ratio of the unrounded eager and filtered exact wall-clock medians in seconds.")
    add("e6.o4.exact_fallbacks", path, geom["fallback"], geom["endpoint"], "predicate calls",
        "Section 7. Exact dyadic fallbacks at the largest scale.")
    add("e6.o4.geometry_seed_count", path, geom["original_unique_seeds"], geom["endpoint"], "real seeds",
        "Table 7. Unique seeds expanded into the generated dyadic workload.")

    for oracle in ("O1", "O2", "O4"):
        timings = {arm: data["wall_seconds"] for arm, data in stages[oracle]["arm"].items()}
        add(f"e6.table7.{oracle.lower()}.time", path, timings, 5, "seconds",
            "Table 7. Median wall time across five fresh workers per arm at 100 million rows or calls.")
    for oracle in ("O3-topk", "O3-group"):
        stage = stages[oracle]["by_scope"]["100000000"]
        timings = {arm: {key: data[key] for key in ("total_wall_seconds",
                    "median_within_trial_checker_over_producer_pct")}
                   for arm, data in stage.items()}
        add(f"e6.table7.{oracle.lower().replace('-', '_')}.time", path, timings, 5,
            "seconds and percent", "Table 7. Total duration and median within-worker incremental ratio.")
    add("e6.table7.o5.time", path, stages["O5"]["stages"], stages["O5"]["endpoint_processes"],
        "seconds, percent and KiB", "Section 7 and Table 7. Sparse apply, intent witness and full verification.")

    path = "evidence/pvldb-a5-epoch-writer/CONTRACT-INVENTORY.json"
    inventory = read(path)
    original = [row["statement_words"] for row in inventory["entries"] if row["cohort"] == "original"]
    add("a5.original.contract_words_min", path, min(original), len(original), "words",
        "Section 7. Minimum over the original held-out case declarations.")
    add("a5.original.contract_words_max", path, max(original), len(original), "words",
        "Section 7. Maximum over the original held-out case declarations.")
    for cohort in ("later", "development"):
        sizes = [row["fields"]["clauses"] for row in inventory["entries"] if row["cohort"] == cohort]
        for metric, value in (("min", min(sizes)), ("max", max(sizes)), ("median", median(sizes))):
            add(f"a5.{cohort}.contract_clauses_{metric}", path, value, len(sizes), "clauses",
                "Section 7. Distribution over the case roster using its recorded contract definitions.")
    add("a5.later.contract_panels", path, len(inventory["panel_definitions"]),
        inventory["counts"]["later"]["panel_definition"], "panels", "Section 7. Later held-out cases.")
    add("a1.static_only_queries", path, inventory["counts"]["benchmark"]["not_measured"],
        sum(inventory["counts"]["benchmark"].values()), "queries", "Section 7. Static inventory only.")

    path = "evidence/pvldb-a5-epoch-writer/DURABLE-RESULT.json"
    durable = read(path)
    add("a5.durable.write_times", path,
        {arm: row["median_of_pair_medians_ms"] for arm, row in durable["summary"].items()},
        len(durable["pairs"]), "milliseconds", "Section 7. Single-writer, one-commit-per-transaction medians.")
    add("a5.durable.wal_bytes", path,
        {arm: median(row["wal_bytes_after_commits"][arm] for row in durable["pairs"])
         for arm in ("tracked", "untracked")}, durable["timed_transactions_per_arm_per_pair"],
        "bytes", "Section 7. Median WAL size after the reported number of commits.")

    path = "evidence/pvldb-a1-query-inventory/INVENTORY.json"
    query_rows = read(path)
    suites = Counter(row["suite"] for row in query_rows)
    windows = Counter(row["suite"] for row in query_rows if row["top_limit"] and row["order_keys"])
    add("a1.table3.queries_by_suite", path, suites, len(query_rows), "queries",
        "Tables 2 and 3. All frozen SQL queries parsed by the static inventory.")
    add("a1.table3.ordered_windows_by_suite", path, {suite: windows[suite] for suite in suites},
        suites, "queries", "Table 3. Top-level ordered LIMIT windows by benchmark.")
    path = "evidence/pvldb-a1-query-inventory/SQL-AUDIT.tsv"
    reviewed = len(source(path).splitlines()) - 1
    add("a1.audit.frozen_queries", path, reviewed, len(query_rows), "queries",
        "Section 4.1. Frozen selected queries with recorded review labels.")
    path = "evidence/pvldb-a1-query-inventory/SQL-AUDIT.md"
    audit = source(path).decode("utf-8")
    resolved, unresolved = map(int, re.search(r"\| Total \| (\d+)/\d+ \| (\d+) \|", audit).groups())
    positive, negative = map(int, re.search(r"including (\d+) positive and (\d+) negative", audit).groups())
    add("a1.audit.cells", path, {"resolved": resolved, "unresolved": unresolved,
        "positive": positive, "negative": negative}, resolved + unresolved, "review cells",
        "Section 4.1. Five axes across the frozen review sample.")
    path = "evidence/pvldb-a1-query-inventory/SAME-CARDINALITY-SUMMARY.json"
    controls = read(path)
    for metric, label in (("native_outputs_accepted", "outputs"), ("shape_controls_rejected", "controls")):
        add(f"a1.{metric}", path, controls[metric], controls[metric], label,
            "Sections 1 and 4.1. Native SQL window replay over the suite/scale roster.")
    add("a1.equal_length_controls_by_kind", path,
        {kind: count["rejected"] for kind, count in controls["equal_length_by_kind"].items()},
        controls["equal_length_controls_rejected"], "controls", "Section 4.1. Equal-length negative controls.")

    path = f"{MATRIX}/BENCHMARK-E5-RESULT.json"
    cases = [row for row in read(path)["observations"] if row["cohort"] == "benchmark"]
    for suite, prefix in (("clickbench", "clickbench-"), ("tpc", "tpc")):
        selected = [row for row in cases if row["id"].startswith(prefix)]
        labels = {"legal": sum(row["legal"] for row in selected), "illegal": sum(not row["legal"] for row in selected)}
        add(f"c3.{suite}.table4.configured_tools", path, comparison_counts(selected, "e5"), labels,
            "comparison arms", "Table 4. Configured tool errors and applicable denominators by suite.")

    path = f"{MATRIX}/TPC-RESULT.json"
    tpc = {row["query"]: row for row in read(path)["queries"]}
    tpc_arms = [arm for query in tpc.values() for arm in query["observations"]]
    add("c3.tpc.table4.generic", path, comparison_counts(tpc_arms, "generic"), len(tpc_arms),
        "comparison arms", "Table 4. Generic TPC comparators with explicit applicability.")
    cwi_arms = [dict(row, cwi={"roundingdiff": row["stock_cwi"]}) for row in tpc["tpcds-39"]["observations"]]
    add("c3.tpc.table4.cwi", path, comparison_counts(cwi_arms, "cwi"), len(cwi_arms),
        "comparison arms", "Table 4. Pinned CWI comparator on the Q39 subset.")
    for key, fields in (
        ("tpch-11", ("biggest_group_cents", "results")),
        ("tpch-21", ("qualifying_suppliers", "boundary_count", "mandatory_before_boundary", "peers_at_boundary",
                     "taken_from_boundary", "memberships_admissible_if_dropping_secondary_sort",
                     "ordered_position_differences_with_reverse_secondary")),
        ("tpcds-86", ("tagged_output_rows_before_limit", "qualifying_join_facts",
                      "null_dimension_rendering_collisions", "groups_wrongly_inferred_by_nullability",
                      "stock_head_hierarchy_counts", "wrong_head_hierarchy_counts")),
    ):
        metadata = tpc[key]["metadata"]
        add(f"c3.{key.replace('-', '_')}.source_reference", path, {field: metadata[field] for field in fields},
            10, "query-specific measurements at SF10", "Section 4.2. Independent exact source rescan.")

    path = f"{MATRIX}/Q59-INDEPENDENT-RESULT.json"
    q59 = read(path)
    add("c3.q59.source_scan_and_cutoff", path, {field: q59[field] for field in (
        "sales_rows_scanned", "cutoff_peer_size", "cutoff_peer_output_rows", "required_rows",
        "position_differences_ascending_vs_descending")}, len(q59["decisions"]), "source rows and cutoff counts",
        "Sections 3 and 4.1. SF10 independent Decimal source rescan and typed window decisions.")
    path = "evidence/e7-archived-native-replay-extension-9/packages/tpch-sf10-bundled-vs-workload-q11/tpch-counts.json"
    add("c3.tpch_sf10.lineitem_rows", path, read(path)["tables"]["lineitem"], 10, "source rows",
        "Section 3. Source lineitem table at SF10, used by the Q21 rescan.")

    path = "evidence/pvldb-a7-typed-candidates/FULL-A2.json"
    ungrouped = read(path)["observations"]
    add("c3.clickbench.table4.q18_q25_generic", path, comparison_counts(ungrouped, "observers"),
        len(ungrouped), "comparison arms", "Table 4. Generic decisions on Q18 and Q25.")
    path = "evidence/pvldb-a2-clickbench-typed-windows/RESULT.json"
    grouped = [row for group in read(path)["queries"].values() for row in group["observations"]]
    add("c3.clickbench.table4.grouped_generic", path, comparison_counts(grouped, "observers"),
        len(grouped), "comparison arms", "Table 4. Generic decisions on Q31–Q33 and Q39–Q42.")
    add("c3.clickbench.table4.generic", path, comparison_counts([*ungrouped, *grouped], "observers"),
        len(ungrouped) + len(grouped), "comparison arms",
        "Table 4. Grouped-window receipt combined with FULL-A2.json for Q18 and Q25.")

    path = "evidence/pvldb-a7-typed-candidates/FULL-ANALYSIS.json"
    full = read(path)
    cutoffs = {row["query"]: row for row in full["queries"] if row["cutoff"]}
    q25, q32 = cutoffs[25], cutoffs[32]
    add("a7.full.cutoff_examples", path, {
        "q25_candidates": q25["cutoff"]["candidate_rows"], "q25_peers": q25["cutoff"]["upper_peers"],
        "q25_legal_bags": full["q25_projected_legal_bags"], "q32_candidates": q32["cutoff"]["candidate_rows"],
        "order_and_bag_difference_counts": {key: len(value) for key, value in full["thread_comparison"].items()},
        "offset_boundary_peer_counts": {str(q): [cutoffs[q]["cutoff"]["lower_peers"],
                                                cutoffs[q]["cutoff"]["upper_peers"]] for q in (39, 40, 41, 42)},
    }, len(full["queries"]), "counts", "Section 4.1. Cutoff and legal output census on full ClickBench.")

    path = "evidence/submission-e-series-native-evidence/e1/q39-retry-reference.json"
    q39 = read(path)
    add("c3.q39.sf1.drift", path, {"changed_rows": q39["variant_changed_rows"], "max_ulp": q39["max_ulp"]},
        q39["groups"], "rows and ULP", "Table 3. SF1 one/four-thread variation versus exact reference.")
    path = ("evidence/e7-archived-native-replay-extension-10/packages/"
            "tpcds-sf10-q39-exact-threshold/q39-result.json")
    q39 = read(path)
    add("c3.q39.sf10.drift", path, {"changed_rows": q39["binary64_row_changes"],
        "max_ulp": {threads: arm["max_ulp"] for threads, arm in q39["native"].items()}},
        q39["output_groups"], "rows and ULP", "Table 3. SF10 one/four-thread variation versus exact reference.")
    path = ("evidence/e7-unified-native-development-extension-8/packages/"
            "publisher-cutoff-observability/RESULT.json")
    q8 = read(path)["h2o_q8"]
    add("a1.h2o.q8_unique_groups", path, q8["cutoff_multiplicities"]["1"], q8["groups"],
        "groups", "Table 3. Groups with a unique top-two cutoff.")
    path = f"{MATRIX}/H2O-RESULT.json"
    h2o = read(path)
    add("c3.h2o.q3_checksum", path,
        {arm: row["stock_chk"] for arm, row in h2o["full_native_checks"].items()},
        h2o["source_rows"], "formatted column sums", "Section 4.2. Native H2O checksum and mutation control.")

    path = "evidence/submission-e-series-native-evidence/e23/result.json"
    c1 = read(path)["observations"]
    c1_rows = [dict(row, legal=row["expected_legal"], typed={"ObsEq": row["typed_oracle_pass"]},
                   mechanism="O4-date-serial" if row["case"].startswith("O4-date-serial-") else row["case"])
               for row in c1]
    add("c1.figure2.generic_by_mechanism", path,
        {method: {
            "legal_mechanisms_rejected": len({row["mechanism"] for row in c1_rows
                if row["legal"] and row["tests"][method] is False}),
            "fault_mechanisms_accepted": len({row["case"] for row in c1_rows
                if not row["legal"] and row["tests"][method] is True}),
         } for method in c1_rows[0]["tests"]},
        {"legal": len({row["mechanism"] for row in c1_rows if row["legal"]}),
         "fault": len({row["mechanism"] for row in c1_rows if not row["legal"]})},
        "mechanisms", "Figure 2 and Table 5. A mechanism contributes if any arm is misclassified.")
    add("c1.table5.generic_and_typed_by_arm", path,
        {**comparison_counts(c1_rows, "tests"), **comparison_counts(c1_rows, "typed")}, len(c1_rows),
        "arms", "Figure 2 and Table 5. Generic comparison and typed-oracle decision counts.")
    path = "evidence/e5-practical-denominator-crosswalk/RESULT.json"
    c1_tools = read(path)
    add("c1.table5.tool_native_masks", path,
        {method: row["native_own_mask"] for method, row in c1_tools["methods"].items()},
        c1_tools["original_rows"], "arms", "Figure 2 and Table 5. Per-tool applicable arms and errors.")
    path = f"{MATRIX}/HOLDOUT-MATRIX.json"
    c2 = read(path)
    add("c2.table6.cases_by_cohort", path, c2["cases"], sum(c2["cases"].values()),
        "authored cases", "Section 5.2 and Table 6. Independent original/later case rosters.")
    original = {group: methods for group, methods in c2["methods_by_group"].items() if group.startswith("original/")}
    mechanisms = defaultdict(Counter)
    for group, methods in original.items():
        for method, counts in methods.items():
            mechanisms[method]["legal_mechanisms_rejected"] += bool(group.startswith("original/O") and counts.get("false_reject"))
            mechanisms[method]["fault_mechanisms_accepted"] += bool(group.startswith("original/F") and counts.get("false_accept"))
    add("c2.table6.original_mechanisms", path, mechanisms,
        {"legal": sum(group.startswith("original/O") for group in original),
         "fault": sum(group.startswith("original/F") for group in original)},
        "mechanisms", "Table 6. Any erroneous observed arm marks its original held-out mechanism.")
    for panel in ("ordered-intervention-receipts", "keyed-aggregate-cancellation", "coherent-group-representatives"):
        key = f"later/heldout-{panel}"
        add(f"c2.table6.{panel.replace('-', '_')}", path, c2["methods_by_group"][key],
            c2["group_denominators"][key], "comparison arms", "Section 5.2. Later held-out panel decisions.")
    path = "evidence/pvldb-a4-natural-roster/FAMILY-MATRIX.json"
    c4 = read(path)
    add("c4.table6.methods_by_release_pair", path, c4["method_totals"], c4["release_pairs"],
        "release pairs", "Table 6. Natural release-pair decisions and per-method applicability.")
    path = "evidence/pvldb-a4-natural-roster/ROSTER.json"
    roster = read(path)
    add("c4.release_pair_sources", path, Counter(row["scope"] for row in roster), len(roster),
        "release pairs", "Section 3. Frozen bug-tracker and supplemental release-pair sources.")
    path = "evidence/pvldb-a4-natural-roster/OLD-PILOT.json"
    pilot = read(path)["rows"]
    add("c4.pandas.pilot_illegal_arms_accepted_by_shape", path, sum(not row["legal"] and
        row["observers"]["rowcount"] and row["observers"]["schema"] for row in pilot), len(pilot),
        "pilot observations", "Section 5.2. Old pandas outputs passing both shape checks.")

    path = "evidence/pvldb-a10-spreadsheetbench-scorer/RESULT.json"
    grade = read(path)
    add("c3.spreadsheetbench.grader_transitions", path, grade["grader_transitions"], grade["targeted_workbooks"],
        "workbooks", "Section 4.2. Official original-versus-recalculated grader transitions.")
    add("c3.spreadsheetbench.grading_range_coverage", path, grade["groups"], grade["targeted_workbooks"],
        "cells, tasks and workbooks", "Section 4.2. Affected gold formulas overlapping grading ranges.")
    path = "evidence/remote-calc-recalculation/RESULT.json"
    calc = read(path)
    add("a6.recalculated.workbooks", path, calc["statuses"]["total"]["recalculated"], calc["source_paths"],
        "workbooks", "Section 6.4. Recalculation admission within the frozen source sample.")
    add("a6.recalculated.formula_cells", path, calc["counts"]["total"], calc["statuses"]["total"]["recalculated"],
        "formula cells", "Section 6.4. Typed cache comparison counts over the admitted workbooks.")
    path = "evidence/tlc-complete-published-clock-transition-coverage/RESULT.json"
    tlc = read(path)
    add("e4.tlc.transition_census", path, tlc["transition_totals"], tlc["total_rows"],
        "months and pickup rows", "Section 6.1. All published transition months of yellow-taxi data.")
    path = "evidence/TLC-TRANSITION-MONTHS.json"
    missing_by_type = Counter()
    for month in read(path)["months"]:
        counts = month["counts"]
        if counts["transition"] == "nonexistent" and counts["affected"]:
            missing_by_type[counts["arrow_type"]] += counts["affected"]
    add("e4.tlc.nonexistent_by_storage_type", path, missing_by_type, sum(missing_by_type.values()),
        "pickup rows", "Section 6.1. Nonexistent local times split by source column type.")

    path = "evidence/HVFHV-UTC-HOURS.json"
    fold, ordinary = read(path)["cohorts"]
    policies = {name: Counter() for name in ("earliest", "latest", "mixed")}
    for row in fold["report"]:
        hour = row["utc_hour"][11:13]
        policies[row["policy"]][hour] += row["count"]
        choice = "latest" if row["provider"] == "HV0003" else "earliest"
        if row["policy"] == choice:
            policies["mixed"][hour] += row["count"]
    ordinary_bins = {name: Counter() for name in ("earliest", "latest")}
    for row in ordinary["report"]:
        ordinary_bins[row["policy"]][row["utc_hour"][11:13]] += row["count"]
    add("e8.hvfhv.utc_policy_counts", path, {
        "selected": fold["admitted"] + fold["excluded_no_duration_match"],
        "moved_pickups": fold["changed_pickup_bins"], "hour_bins": policies,
        "two_fold_hours_total": policies["earliest"]["05"] + policies["earliest"]["06"],
        "ordinary_control_agrees": ordinary_bins["earliest"] == ordinary_bins["latest"],
    }, fold["admitted"], "pickup counts", "Section 6.1 and the NYC ride-hail figure.")

    path = "evidence/pvldb-a7-typed-candidates/FULL-ID-CAST.json"
    ids = read(path)["columns"]
    add("a7.full.id_cast_counts", path, {column: row["exact_reference_and_native"] for column, row in ids.items()},
        ids["UserID"]["exact_reference_and_native"]["population"], "keys and pairs",
        "Section 6.2. Full ClickBench distinct keys and symmetric/asymmetric cast effects.")
    path = "evidence/pvldb-a2-clickbench-left-join/RESULT.json"
    join = read(path)
    add("a2.clickbench.left_rollup_rows", path, join["left_rows"], join["source_rows"], "rows",
        "Section 6.2. Exact and corrupted one-output-per-left-row products.")
    add("a2.clickbench.left_rollup_sample_rows", path,
        join["per_left_row_product"]["fixed_stride_sample"]["rows_per_arm"], join["left_rows"], "rows",
        "Section 6.2. Fixed-stride projection used by the comparator crosswalk.")
    for version in ("143", "201"):
        path = ("evidence/e7-unified-native-development-extension-8/packages/"
                f"clickbench-native-id-cast-boundaries/result-{version}.json")
        columns = read(path)["columns"]
        direct = columns["UserID"]["bigint_source"]
        wide = columns["UserID"]["widening_control"]
        add(f"a7.shard.id_cast_duckdb{version}", path, {
            "watch_id_keys_changed": columns["WatchID"]["bigint_source"]["keys_changed"],
            "user_id_widened_negative_differences": wide.get("negative_diff", 0),
            "user_id_additional_lost_pairs": wide["unilateral_lost_pairs"] - direct["unilateral_lost_pairs"],
        }, direct["population"], "keys and pairs", "Section 6.2. Native direct and widened casts on one shard.")
    path = "evidence/e7-archived-native-replay-extension-9/packages/sparse-float-join-discriminators/result.json"
    tweet = read(path)[0]
    add("e3.tweet_ids.float64_false_pairs", path, tweet["float_false_pairs"], tweet["all_domain_distinct"],
        "spurious self-join pairs", "Section 6.2. Published tweet IDs and symmetric float64 comparison.")
    path = "evidence/e4-direct-geos-version-order-matrix/RESULT.json"
    geos = read(path)
    scans = geos["scan_same_all"]
    add("e4.geometry.scanned_features", path, sum(n for key, n in scans.items() if key.endswith("|original")),
        3, "features", "Section 6.3. Polygonal feature scans across three GEOS releases.")
    add("e4.geometry.union_order_and_release", path, geos["comparisons"], sum(geos["admitted_same_all"].values()),
        "features", "Section 6.3. WKB and topology deltas for all order/release comparisons.")
    path = "evidence/NATURAL-EARTH-ADMIN1-VALIDITY.json"
    earth = read(path)["counts"]
    add("e4.geometry.natural_earth_admin1_invalid", path, earth["gdal_invalid"], earth["features"],
        "features", "Section 6.3. Independent Natural Earth province validity scan.")

    path = "evidence/e9-independent-annotation-and-adjudication/RESULT.json"
    issues = read(path)
    total = issues["adjudicated"]["reviewed_rows"]
    add("e9.sample.adjudicated_status", path, issues["adjudicated"]["status"], total,
        "issues", "Section 6.5. Adjudicated yes/no/unresolved counts.")
    add("e9.sample.adjudicated_classes", path, {**issues["adjudicated"]["yes_class"], "O3": 0},
        issues["adjudicated"]["status"]["yes"], "issues", "Section 6.5. Classes of evidenced wrong results.")
    for metric in ("wrong_result", "joint_wrong_result_and_class", "class_given_both_yes"):
        score = issues[metric]
        add(f"e9.sample.kappa.{metric}", path, float(Fraction(score["kappa"])), score["paired"],
            "Cohen's kappa", "Section 6.5. Two independent rater annotations before adjudication.")
    add("e9.sample.adjudicated_disagreements", path, issues["adjudication_needed"], total,
        "issues", "Section 6.5. Cases sent to a third rater.")
    path = "evidence/ISSUE-SAMPLE-COUNTS.txt"
    eligible, sampled = map(int, re.search(r"unique (\d+) sample (\d+)", source(path).decode("utf-8")).groups())
    add("e9.sample.eligible_population", path, {"eligible": eligible, "sampled": sampled}, eligible, "issues",
        "Table 2 and Section 6.5. Unique eligible issues and the deterministic sample size.")

    path = "evidence/TPCH-SF1-CROSS-ENGINE.json"
    tpch = read(path)["queries"]
    add("a1.tpch.sf1.postgres_comparison", path, {
        "exact": sum(row["same_typed_bag"] for row in tpch),
        "tolerance_only": sum(row["same_bag_with_float_tolerance"] and not row["same_typed_bag"] for row in tpch),
    }, len(tpch), "query output bags", "Table 3. DuckDB and PostgreSQL on the pinned SF1 tables.")

    path = "evidence/pvldb-a7-typed-candidates/PART0-CUTOFFS.jsonl"
    shard = [json.loads(line) for line in source(path).splitlines()]
    add("a7.partition0.split_cutoff", path, sum(row["lower_boundary_split"] or row["upper_boundary_split"]
        for row in shard), len(shard), "ORDER BY/LIMIT queries",
        "Eight-thread cutoff census on the one-million-row publisher shard hits_0.parquet.")
    rows["a7.partition0.split_cutoff"].update(status="superseded_for_population_estimates",
        full_cohort_source="a7.full.split_cutoff", superseded_by="a7.full.split_cutoff")
    path = "evidence/pvldb-a6-cache-transitions/TEXTAFTER-CLUSTER.json"
    add("a6.textafter_name_error", path, read(path)["counts"]["cells"],
        calc["counts"]["total"]["type_disagreement"], "cells",
        "Occurrences of unsupported TEXTAFTER in the dominant answer workbook, out of the original Calc cache type disagreements.")
    path = "evidence/tlc-complete-published-clock-transition-coverage/RESULT.json"
    ambiguous = tlc["transition_totals"]["ambiguous"]
    add("e4.tlc.transition_month_population", path, tlc["total_rows"], tlc["total_rows"], "source rows",
        "All 35 published clock-transition months in the pinned NYC TLC index.")
    add("e4.tlc.ambiguous_trips", path, ambiguous["affected"], ambiguous["in_month"], "in-month pickup rows",
        "Ambiguous local hours in the 17 published NYC TLC fall transition months.")
    path = "evidence/e5-practical-denominator-crosswalk/RESULT.json"
    add("e5.common.configurations", path, len(c1_tools["methods"]), c1_tools["number_configurations"],
        "tested configurations", "Shared E2/E3 cohort, with applicability recorded independently per method.")
    path = "evidence/e9-independent-annotation-and-adjudication/RESULT.json"
    add("e9.sample.wrong_result_yes", path, issues["adjudicated"]["status"]["yes"], total, "sampled public issues",
        "Adjudicated, deliberately query-selected frozen public issue sample. The coded unresolved cases remain in the denominator.")
    path = "evidence/e9-all-class-release-coverage/RESULT.json"
    release_pairs = read(path)["across_both_sources_strict"]["n"]
    add("e9.native_release_pairs", path, release_pairs, len(roster), "release-pair families",
        "15 from the frozen public issue sample and 14 purposefully found supplements.")
    path = "evidence/e6-cross-scale-and-ratio-audit/RESULT.json"
    ratios = {
        "e6.o1.backup_and_typed_digest": (
            stages["O1"]["arm"]["sqlite_backup_logical"]["percent_of_separate_native_read_median"],
            "SQLite backup and typed logical digest relative to native count/sum."),
        "e6.o2.trusted_epoch_check": (
            stages["O2"]["arm"]["epoch"]["percent_of_separate_native_producer_median"],
            "Dependency epoch check relative to the H2O Q1 native producer."),
        "e6.o4.lazy_filtered_vs_generate": (
            geom["arm"]["lazy_filtered"]["percent_of_separate_generation_checksum_median"],
            "Filtered exact predicates relative to the separate generation/checksum arm."),
        "e6.o5.witness_vs_sparse_apply": (
            stages["O5"]["stages"]["witness_over_apply_median_within_trial_pct"],
            "Intent witness relative to sparse apply in the same worker."),
    }
    for arm in ("guard", "family"):
        ratios[f"e6.o3.topk_{arm}_increment"] = (
            topk[arm]["median_within_trial_checker_over_producer_pct"],
            "Additional checker time versus producer in same worker.")
    for id_, (value, scope) in ratios.items():
        add(id_, path, value, 100, "percent of stated baseline", scope)

    return rows


def verify(root, ledger):
    published = {row["id"]: row for row in ledger}
    if len(published) != len(ledger):
        raise ValueError("Duplicate IDs in NUMBERS.json")
    for id_, row in recount(root).items():
        if published.get(id_) != row:
            raise ValueError(f"Recounted ledger entry differs: {id_}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="ledger IDs to recount (default: all supplemental IDs)")
    args = parser.parse_args()
    rows = recount()
    if unknown := set(args.ids) - rows.keys():
        parser.error("unrecognized IDs: " + ", ".join(sorted(unknown)))
    print(json.dumps([rows[id_] for id_ in args.ids or rows], indent=2))


if __name__ == "__main__":
    main()
