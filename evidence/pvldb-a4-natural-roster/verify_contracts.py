"""Execute C4's case-specific contracts on sealed native output projections."""

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
from fractions import Fraction
from functools import cache
import hashlib
import json
import math
from pathlib import Path


FAMILIES = {
    "O1": {"prepared-snapshot-count", "pandas-groupby-snapshot"},
    "O2": {"polars-cache-lineage", "pandas-index-uniqueness-cache"},
    "O3": {"group-null-reassignment", "pivot-null-buckets", "null-sort-topn",
           "nested-sibling-null-explode", "pandas-annual-boundaries", "pandas-asof-string-boundary",
           "rolling-variance-cancellation", "pandas-timedelta-cancellation",
           "pandas-historical-rolling-moments", "polars-categorical-series-topk",
           "polars-grouped-coupled-representative"},
    "O4": {"uint64-mixed-input", "nested-timezone", "melt-timezone", "group-collation-type",
           "insert-decimal-export", "precision-ring-measure", "nullable-cumulative-group-type",
           "categorical-membership-logical-equality", "styler-index-representation",
           "valid-segment-intersection", "copy-summary-bound"},
    "O5": {"upsert-state-and-receipt", "pandas-reversed-positional-write",
           "pandas-idempotent-partial-key-write"},
}
ORACLE = {name: oracle for oracle, names in FAMILIES.items() for name in names}


def exact(expected, candidate):
    if type(expected) is not type(candidate):
        return False
    if isinstance(expected, list):
        return len(expected) == len(candidate) and all(exact(x, y) for x, y in zip(expected, candidate))
    return expected == candidate


def snapshot(family, arm, candidate, read):
    """Bind the read to the fixture's committed or captured logical version."""
    if family == "prepared-snapshot-count":
        rows = read("e9-native-f3-prepared-snapshot/RESULT.json")
        state = next(row for row in rows if row["duckdb"] == arm)
        if state["fresh_after"] != state["parameterized_after"]:
            raise ValueError("the two post-write controls disagree")
        expected = [[sensor, count] for sensor, count in zip((10, 20), state["fresh_after"], strict=True)]
    else:
        _, index = arm.split(":")
        grouping_keys = (11 if int(index) == 2 else 2, 5, 2, 7)
        sums = Counter()
        for group, value in zip(grouping_keys, (13, 17, 23, 29)):
            sums[group] += value
        expected = [[group, total] for group, total in sorted(sums.items())]
    return exact(expected, candidate)


def freshness(family, arm, candidate, read):
    """Compare cached state with the fixture's independently recomputed state."""
    if family == "pandas-index-uniqueness-cache":
        _, index = arm.split(":")
        offset = (0, 10, -20)[int(index)]
        child = [value + offset for value in (1, 1, 2, 3, 4)[2:]]
        expected = [[len(child) == len(set(child))]]
    else:
        archived = read("e9-supplemental-f4-polars-cached-lineage/RESULT.json")[arm]
        expected = [[case, *row] for case, data in enumerate(archived)
                    for row in data["engines"]["in-memory"]["controls"]["cache_disabled"]]
    return exact(expected, candidate)


def allowed_result(family, arm, expected, candidate, read):
    if family == "pandas-timedelta-cancellation":
        release, index = arm.split(":")
        file = "OLD-PILOT.json" if release == "old" else "NEW-PILOT.json"
        rows = read(f"pvldb-a4-natural-roster/{file}")["rows"]
        values = [row["input"] for row in rows if row["family"] == family][int(index)]
        return exact([[sum(values)]], candidate)
    if family == "polars-categorical-series-topk":
        _, order = arm.split("/", 1)
        categories = dict(h="9", l="1", m1="5", m2="5")
        reference = Counter(sorted((categories[id_] for id_ in order.split(",")), reverse=True)[:2])
        return Counter(value for value, in candidate) == reference
    if family == "polars-grouped-coupled-representative":
        release, mode, index = arm.split("/")
        cases = read(f"e9-supplemental-o3-polars-group-representative/{release}.json")
        groups = defaultdict(list)
        for group, id_, units, score in cases["reports"][mode]["cases"][int(index)]["input"]:
            groups[group].append((id_, units, score))
        if [group for group, *_ in candidate] != sorted(groups):
            return False
        for group, id_, units in candidate:
            members = groups[group]
            payloads = [(i, u) for i, u, _ in members]
            if mode != "plain_ties":
                payloads.reverse()
            min_score = min(score for _, _, score in members)
            legal = {payload for payload, (_, _, score) in zip(payloads, members) if score == min_score}
            if (id_, units) not in legal:
                return False
        return True
    if family == "pandas-historical-rolling-moments":
        source = read("e9-supplemental-f7-pandas-rolling-future-window/RESULT.json")["oracle"]
        window = [math.sqrt(Fraction(source["positive_skew_squared"])),
                  float(Fraction(source["excess_sample_kurtosis"]))]
        return len(candidate) == 1 and len(candidate[0]) == len(window) and all(
            math.isclose(actual, target, rel_tol=0, abs_tol=source["tol"])
            for actual, target in zip(candidate[0], window)
        )
    return exact(expected, candidate)


def representation(family, arm, expected, candidate, read):
    if family == "insert-decimal-export":
        return [Decimal(value) for value, in expected] == [Decimal(value) for value, in candidate]
    if family == "precision-ring-measure":
        measures = read("e9-native-f10-geos-precision-measure/RESULT.json")
        raw = next(row for row in measures if row["version"].split("-")[0] == arm)
        return raw["nan_m_count"] == 0 and exact(expected, candidate)
    if family == "valid-segment-intersection":
        raw = read(f"e9-native-f10-valid-segment-intersection/{arm}.raw")
        return raw["prepared"] == 1 and candidate == [[raw["prepared"]]]
    return exact(expected, candidate)


def effect(family, arm, candidate):
    """Check fixture-specific intended and preserved projected fields."""
    if family == "pandas-reversed-positional-write":
        _, index = arm.split(":")
        east, west, spare = (1, 2, 3), (10, 20, 30), (300, 400, 500)
        source_order = (east, west) if int(index) % 3 == 2 else (west, east)
        expected = [list(row) for row in zip(*source_order, spare)]
    elif family == "pandas-idempotent-partial-key-write":
        values = [0, 1, 2]
        expected = [[None], *[[(a + b) / 2] for a, b in zip(values, values[1:])]]
    else:
        expected = [["keep", "kept"], ["clear", None], ["returning_id", "1"],
                    ["stored_id", "1"], ["stored_value", "30"]]
    return exact(expected, candidate)


def predict(family, arm, reference, candidate, read):
    oracle = ORACLE[family]
    if oracle == "O1":
        return snapshot(family, arm, candidate, read)
    if oracle == "O2":
        return freshness(family, arm, candidate, read)
    if oracle == "O3":
        return allowed_result(family, arm, reference, candidate, read)
    if oracle == "O4":
        return representation(family, arm, reference, candidate, read)
    return effect(family, arm, candidate)


def audit(root):
    a4 = "pvldb-a4-natural-roster"
    matrix = "pvldb-native-baseline-matrix"
    hashes = {}

    @cache
    def read(name):
        raw = (root / name).read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        if name.endswith(".jsonl"):
            return [json.loads(line) for line in raw.splitlines()]
        return json.loads(raw)

    inputs = {}
    for family, arm, reference, candidate in read(f"{a4}/TYPED-LEGACY-ARMS.jsonl"):
        if (family, arm) in inputs:
            raise ValueError(f"duplicate native case: {family}/{arm}")
        inputs[family, arm] = reference, candidate
    for file in ("NATURAL-RESULT", "NATURAL-EXTENDED-RESULT"):
        for row in read(f"{matrix}/{file}.json")["observations"]:
            key = row["family"], row["version"]
            if key in inputs:
                raise ValueError(f"duplicate native case: {key}")
            inputs[key] = row["reference"], row["candidate"]
    predictions = {key: predict(*key, *cells, read) for key, cells in sorted(inputs.items())}

    # Load the old reference labels only after producing the predictions.
    truth = {}
    for item in read(f"{a4}/E5-LEGACY.json")["observations"]:
        truth[item["id"], item["arm"]] = item["legal"]
    for file in ("NATURAL-RESULT", "NATURAL-EXTENDED-RESULT"):
        for row in read(f"{matrix}/{file}.json")["observations"]:
            truth[row["family"], row["version"]] = row["legal"]
    roster = {row["family"] for row in read(f"{a4}/ROSTER.json")}
    if predictions.keys() != truth.keys() or {family for family, _ in predictions} != roster:
        raise ValueError("contract results and historical labels cover different arms")
    outcomes = defaultdict(Counter)
    observations = []
    for (family, arm), decision in predictions.items():
        legal = truth[family, arm]
        outcome = ("true_" if decision == legal else "false_") + ("accept" if decision else "reject")
        outcomes[family][outcome] += 1
        observations.append({"family": family, "arm": arm, "oracle": ORACLE[family],
                             "historical_legal": legal, "contract_accepts": decision})
    return {
        "scope": "case-specific contract checks over archived native projections",
        "release_pairs": len(roster),
        "pairs_with_illegal_arms": sum(bool(r["true_reject"] + r["false_accept"]) for r in outcomes.values()),
        "pairs_with_legal_arms": sum(bool(r["true_accept"] + r["false_reject"]) for r in outcomes.values()),
        "pairs_with_missed_faults": sum(r["true_reject"] == 0 and r["false_accept"] > 0 for r in outcomes.values()),
        "pairs_with_legal_rejects": sum(r["false_reject"] > 0 for r in outcomes.values()),
        "family_counts": dict(outcomes),
        "source_sha256": hashes,
        "observations": observations,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.evidence), sort_keys=True, indent=2))
