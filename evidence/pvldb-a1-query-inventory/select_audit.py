"""Freeze a 30-query mechanism-stratified queue for independent human review."""

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys


def signatures(row):
    tests = {
        "ordered_limit": row["top_limit"] and row["order_keys"],
        "ordered_without_limit": not row["top_limit"] and row["order_keys"],
        "unordered_limit": row["top_limit"] and not row["order_keys"],
        "unresolved_order_dependency": row["order_dependency"] == "dependency_unresolved",
        "nested_limit": row["nested_limits"] > 0,
        "ranking_window": row["ranking_windows"] > 0,
        "representative": row["explicit_representative"],
        "grouped_top_n": row["grouped_top_n_aggregates"] > 0,
        "floating_reduction": row["float_inputs"] > 0,
        "unresolved_reduction": row["unresolved_reduction_inputs"] > 0,
        "native_statistical_binding": row["exact_before_native_statistical_binding"] > 0,
    }
    return {key for key, applies in tests.items() if applies} or {"no_static_trigger"}


def audit_keys(rows):
    suites = defaultdict(list)
    for row in rows:
        suites[row["suite"]].append(row)
    if set(suites) != {"tpch", "tpcds", "ssb", "job", "clickbench", "h2o"} or len(rows) != 305:
        raise ValueError("unexpected source cohort")
    for suite, members in sorted(suites.items()):
        unreviewed = {(r["query"], r["sql_sha256"]): signatures(r) for r in members}
        if len(unreviewed) != len(members):
            raise ValueError(f"duplicate input in {suite}")
        covered = set()
        for _ in range(5):
            def priority(key):
                tie = hashlib.sha256(("pvldb-a1-audit-20261123:" + suite + ":" + key[0]).encode()).hexdigest()
                return -len(unreviewed[key] - covered), tie

            key = min(unreviewed, key=priority)
            covered.update(unreviewed.pop(key))
            yield suite, *key


def main():
    p = argparse.ArgumentParser()
    p.add_argument("inventory", type=Path)
    a = p.parse_args()
    source = json.loads(a.inventory.read_bytes())
    writer = csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")
    writer.writerow(("suite", "query", "sql_sha256", "reviewer", "mechanism_labels", "basis", "unresolved_reason"))
    writer.writerows((*key, "", "", "", "") for key in audit_keys(source))


if __name__ == "__main__":
    main()
