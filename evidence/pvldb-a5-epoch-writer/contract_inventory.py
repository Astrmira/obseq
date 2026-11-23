"""Count recorded contract sources and sizes without guessing missing annotations."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import subprocess


def read(path):
    return json.loads(path.read_bytes())


PANEL_CLAUSES = {
    "heldout-binary64-orientation": ("binary64 coordinates", "exact orientation sign", "ordered point triple"),
    "heldout-coherent-group-representatives": ("group identity", "rank score", "joint representative fields"),
    "heldout-group-role-and-fold-joint": ("explicit grouping role", "civil-time fold", "coupled projection"),
    "heldout-json-presence-and-path-shape": ("path", "presence", "container shape", "typed value"),
    "heldout-keyed-aggregate-cancellation": ("row key", "nullable value", "exact keyed bag"),
    "heldout-ordered-intervention-receipts": ("initial state", "ordered intent", "effect identity", "post-state"),
}


def replay_length(root, archive, case):
    entry = case.get("entry", "check.py")
    fingerprint = case["blobs"][entry]
    path = archive / "packages" / case["case_id"] / entry
    if path.is_file():
        data = path.read_bytes()
    else:
        data = subprocess.check_output(["git", "cat-file", "blob", fingerprint["git_blob"]], cwd=root)
    if hashlib.sha256(data).hexdigest() != fingerprint["sha256"]:
        raise ValueError(f"development replay digest changed: {case['case_id']}")
    return sum(bool(line.strip()) for line in data.splitlines())


def inventory(root):
    a1 = root / "pvldb-a1-query-inventory"
    certified = {row["sql_sha256"] for file in a1.glob("VERIFY-*.jsonl")
                 for line in file.read_bytes().splitlines() if "observations" in (row := json.loads(line))}
    rows = []
    for query in read(a1 / "INVENTORY.json"):
        native = query["sql_sha256"] in certified
        facts = [name for name in ("nested_limits", "explicit_representative", "float_inputs",
                                  "unresolved_reduction_inputs", "ranking_windows") if query[name]]
        rows.append({"cohort": "benchmark", "id": f'{query["suite"]}/{query["query"]}',
                     "source": "query_snapshot_derived" if native else "not_measured",
                     "contract": "O3 ordered projected window" if native else "unclassified",
                     "fields": {"order_keys": query["order_keys"], "offset_clause": int(query["top_offset"])}
                               if native else None, "other_static_indicators": facts})

    blind = root / "e7-original-native-one-command/bundle/e7-scored/BLIND.json"
    for case in read(blind):
        rows.append({"cohort": "original", "id": case["case_id"], "source": "per_case_statement",
                     "contract": case["subtype"], "fields": {"statements": 1},
                     "statement_words": len(case["contract"].split())})

    later = root / "pvldb-native-baseline-matrix/LATER-RESULT.json"
    for panel, identity in sorted({(row["panel"], row["id"]) for row in read(later)["observations"]}):
        rows.append({"cohort": "later", "id": identity, "source": "panel_definition",
                     "contract": panel, "fields": {"clauses": len(PANEL_CLAUSES[panel])}})

    dedup = set()
    with (root / "pvldb-a5-epoch-writer/DEVELOPMENT-CONTRACTS.tsv").open(encoding="utf-8", newline="") as file:
        annotations = {row["id"]: row for row in csv.DictReader(file, delimiter="\t")}
    packages = [*root.glob("e7-unified-native-development*/MANIFEST.json"),
                *root.glob("e7-archived-native-replay-extension-*/MANIFEST.json")]
    for file in sorted(packages):
        for case in read(file)["cases"]:
            identity = case["case_id"]
            if identity in dedup or case["kind"] != "native_authored_development":
                continue
            dedup.add(identity)
            annotation = annotations[identity]
            clauses = annotation["clauses"].split(", ")
            rows.append({"cohort": "development", "id": identity, "source": annotation["source"],
                         "contract": annotation["family"], "fields": {"clauses": len(clauses)},
                         "contract_clauses": clauses,
                         "replay_code_nonblank_lines": replay_length(root, file.parent, case),
                         "archive_manifest": file.relative_to(root).as_posix()})
    if set(annotations) != dedup:
        raise ValueError("development annotations do not match the frozen archive")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    rows = inventory(args.evidence)
    counts = defaultdict(Counter)
    contract_sources = defaultdict(Counter)
    for row in rows:
        counts[row["cohort"]][row["source"]] += 1
        if row["cohort"] == "development":
            contract_sources[row["contract"]][row["source"]] += 1
    print(json.dumps({"counts": counts, "development_contract_sources": contract_sources,
                      "panel_definitions": PANEL_CLAUSES, "entries": rows}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
