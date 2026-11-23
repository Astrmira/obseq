"""Bind all 29 strict natural-fault families to their native replay packets."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path


EARLIER = "e9-release-replay-crosswalk-15-roster/REPLAYS.tsv"
LATEST = "e9-all-class-release-coverage/REPLAYS.tsv"
EARLIER_PACKETS = {
    "group-null-reassignment": "e9-native-ordinary-correctness-release-controls",
    "pivot-null-buckets": "e9-native-ordinary-correctness-release-controls",
    "uint64-mixed-input": "e9-native-historical-f1-f8-controls",
    "nested-timezone": "e9-native-historical-f1-f8-controls",
    "melt-timezone": "e9-native-historical-f1-f8-controls",
    "group-collation-type": "e9-native-historical-f9-duckdb-cli",
    "insert-decimal-export": "e9-native-historical-o4-decimal-export",
    "upsert-state-and-receipt": "e9-native-historical-f5-upsert-effects",
    "copy-summary-bound": "e9-native-f6-parquet-claimed-stats",
    "precision-ring-measure": "e9-native-f10-geos-precision-measure",
    "null-sort-topn": "e9-native-f2-roster-topn-null",
    "prepared-snapshot-count": "e9-native-f3-prepared-snapshot",
    "rolling-variance-cancellation": "e9-native-f7-pandas-rolling-std",
    "nullable-cumulative-group-type": "e9-native-f9-nullable-cumulative-type",
    "categorical-membership-logical-equality": "e9-native-o4-categorical-logical-equality",
    "nested-sibling-null-explode": "e9-native-f2-polars-unnest-sibling-null",
    "styler-index-representation": "e9-native-f1-styler-index-representation",
    "valid-segment-intersection": "e9-native-f10-valid-segment-intersection",
}


def rows(path):
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def readme(root, packet):
    path = root / packet / "README.md"
    return {"packet": packet, "readme_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def build(root):
    original, supplement = rows(root / EARLIER), rows(root / LATEST)
    classifications = json.loads((root / EARLIER).with_name("RESULT.json").read_bytes())["observations"]
    if set(EARLIER_PACKETS) != {row["family"] for row in original}:
        raise ValueError("earlier roster does not match pinned packet mapping")
    results = []
    for row in original:
        anchor = classifications[row["family"]]
        if any(anchor[key] != value for key, value in row.items()):
            raise ValueError("earlier case differs from the audited record")
        scope = "frozen_300" if anchor["scope"] == "frozen_roster" else "supplemental"
        results.append({
            "family": row["family"], "category": row["category"], "scope": scope,
            "old": row["initial"], "new": row["later"], "artifact_commit": row["artifact_commit"],
            "issues": anchor["issues"], "frozen_roster_ids": anchor["roster_ids"],
            **readme(root, EARLIER_PACKETS[row["family"]]),
        })
    for family, category, issue, packet in (
        ("pandas-reversed-positional-write", "F5", 65446, "e9-supplemental-f5-positional-write"),
        ("pandas-timedelta-cancellation", "F7", 66551, "e9-supplemental-f7-timedelta-cancellation"),
    ):
        results.append({
            "family": family, "category": category, "scope": "supplemental", "old": "2.2.3", "new": "3.1.1",
            "issues": [f"https://github.com/pandas-dev/pandas/issues/{issue}"], **readme(root, packet),
        })
    for row in supplement:
        if row["scope"] != "supplemental":
            continue
        results.append({
            "family": row["family"], "category": row["category"], "scope": "supplemental",
            "old": row["old"], "new": row["new"], "artifact_commit": row["commit"],
            "issues": row["source"].split(";"), **readme(root, row["slug"]),
        })
    if len({row["family"] for row in results}) != 29:
        raise ValueError("expected 29 distinct strict replay families")
    published = json.loads((root / "e9-all-class-release-coverage" / "RESULT.json").read_bytes())
    if Counter(r["category"] for r in results) != published["across_both_sources_strict"]["categories"]:
        raise ValueError("strict class counts differ from released reconciliation")
    if Counter(r["scope"] for r in results) != {"frozen_300": 15, "supplemental": 14}:
        raise ValueError("incorrect frozen/supplemental split")
    if Counter(r["category"] for r in results if r["scope"] == "frozen_300") != published["frozen_unchanged"]["categories"]:
        raise ValueError("in-roster families differ from released class counts")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.evidence_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
