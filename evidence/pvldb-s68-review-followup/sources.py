"""Join C4 releases to their frozen E9 annotations and render the source table."""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import runpy


def read(path):
    return json.loads(path.read_bytes())


def labels(root):
    root = root / "e9-independent-annotation-and-adjudication"
    freeze = runpy.run_path(str(root / "check.py"))["freeze"]
    with (root / "ROSTER.csv").open(encoding="utf-8", newline="") as stream:
        issues = {row["id"]: row for row in csv.DictReader(stream)}
    def ratings(name):
        return {row["id"]: row for row in map(json.loads, (root / name).read_bytes().splitlines())}
    a, b, tie = (ratings(name) for name in ("RATER-A.jsonl", "RATER-B.jsonl", "ADJUDICATED.jsonl"))
    finalized = {}
    for id_, issue in issues.items():
        left, right = freeze(a[id_]), freeze(b[id_])
        choice = a[id_] if left == right else tie[id_]
        status, category = freeze(choice)
        finalized[id_] = {**issue, "status": status, "category": category,
                          "fix_a": a[id_]["fix_status"], "fix_b": b[id_]["fix_status"]}
    if Counter(row["status"] for row in finalized.values()) != read(root / "RESULT.json")["adjudicated"]["status"]:
        raise ValueError("The joined E9 label distribution differs from its frozen receipt")
    return finalized


def render(root, upstream, positives=None):
    inputs = root / "pvldb-a4-natural-roster"
    origins = read(inputs / "ROSTER.json")
    contracts = read(inputs / "CONTRACT-CHECKS.json")
    matrix = read(inputs / "FAMILY-MATRIX.json")
    current = labels(root) if positives is None else {row["id"]: dict(row, status="yes") for row in positives}
    per_family = defaultdict(list)
    for record in contracts["observations"]:
        per_family[record["family"]].append(record)
    rows = []
    for item in sorted(origins, key=lambda item: item["family"]):
        family = item["family"]
        observations = per_family[family]
        versions = [item["old"], item["new"]]
        issues = item["issues"]
        fix_refs = {ref["url"]: ref for issue in issues for field in ("closing_merged_prs", "evidence_linked_merged_prs")
                    for ref in upstream.get(issue, {}).get(field, [])}
        keys = item.get("frozen_roster_ids", [])
        matched = [current[k] for k in keys if k in current]
        decision = matrix["families"][family]["ordered"]
        rows.append({"mechanism": family, "category": item["category"], "versions": versions,
                     "issues": issues, "upstream_fix_links": [fix_refs[url] for url in sorted(fix_refs)],
                     "oracle": sorted({o["oracle"] for o in observations}),
                     "visible_to_ordered_equality": bool(decision["detected"]),
                     "e9_links": [{"id": row["id"], "status": row["status"], "url": row["url"],
                                   "matches_issue": row["url"] in issues} for row in matched],
                     "e9_unresolved_ids": [k for k in keys if k not in current],
                     "archived_contract_arms": len(observations)})
        dispositions = {issue: upstream[issue]["disposition"] for issue in issues
                        if "disposition" in upstream.get(issue, {})}
        if dispositions:
            rows[-1]["upstream_disposition"] = dispositions
    linked = [row for row in rows if row["e9_links"]]
    positive = {match["id"] for row in linked for match in row["e9_links"]
                if match["status"] == "yes" and match["matches_issue"]}
    scope = {"release_pairs": len(rows), "linked_families": len(linked), "linked_distinct_positive_issues": len(positive),
             "release_pairs_with_fix_link": sum(bool(row["upstream_fix_links"]) for row in rows),
             "e9_positive_count": sum(row["status"] == "yes" for row in current.values())}
    return {"summary": scope, "rows": rows}


def markdown(data):
    def links(urls):
        return ", ".join(f"[#{url.rsplit('/', 1)[1]}]({url})" for url in urls) or "—"

    lines = [
        "# C4 release-pair sources", "",
        "The issue-to-release mapping comes from the frozen C4 roster. The merged PRs were linked by the issue or by the replay evidence. "
        "A dash indicates that the repair commit is unresolved. "
        "Visibility means that ordered equality detected at least one faulty arm. "
        "An E9 link is counted as positive only when its frozen annotation and issue URL agree.",
        "", "| Mechanism | Issue | Upstream fix PR | Tested versions | Class | Ordered equality detects fault | ObsEq | E9 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in data["rows"]:
        match = ", ".join(f"{item['id']} ({item['status']})" for item in row["e9_links"]) or "—"
        fixes = links([ref["url"] for ref in row["upstream_fix_links"]])
        lines.append(f"| {row['mechanism']} | {links(row['issues'])} | {fixes} | "
                     f"{row['versions'][0]} → {row['versions'][1]} | {row['category']} | "
                     f"{'yes' if row['visible_to_ordered_equality'] else 'no'} | {', '.join(row['oracle'])} | {match} |")
    for row in data["rows"]:
        for issue, info in row.get("upstream_disposition", {}).items():
            lines.extend([
                "",
                f"For {links([issue])}, maintainers added the [`{info['label']}` label]"
                f"({info['label_event']}) on {info['labeled_at'][:10]} and "
                f"[closed the issue as {info['closed_as']}]({info['close_event']}) on {info['closed_at'][:10]}. "
                f"The repair commit is {info['repair_commit'] or 'unresolved'}. "
                f"An earlier candidate was {links([info['earlier_candidate']])}. "
                f"{info['earlier_candidate_outcome']} The table gives the tested versions.",
            ])
    return "\n".join(lines) + "\n"


def review_queue(evidence, path, positives=None):
    columns = ("id", "issue_url", "fix_or_maintainer_confirmation", "reproduction_evidence",
               "human_wrong_result", "human_category", "human_reviewer", "reviewed_at")
    positive = ([row for row in labels(evidence).values() if row["status"] == "yes"]
                if positives is None else positives)
    with path.open("x", encoding="utf-8", newline="") as stream:
        out = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n", delimiter="\t")
        out.writeheader()
        out.writerows({"id": row["id"], "issue_url": row["url"]} for row in positive)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--review-queue", type=Path)
    parser.add_argument("--e9-positives", type=Path, help="Use the published positive slice for offline rendering")
    args = parser.parse_args()
    positives = read(args.e9_positives)["positive_rows"] if args.e9_positives else None
    data = render(args.evidence, read(args.upstream), positives)
    if args.markdown:
        args.markdown.write_text(markdown(data), encoding="utf-8", newline="\n")
    if args.review_queue:
        review_queue(args.evidence, args.review_queue, positives)
    print(json.dumps(data, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
