"""Map A6 formula differences to SpreadsheetBench V1's actual grading surface."""

import argparse
from collections import Counter, defaultdict
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path, PurePosixPath
import runpy
import tarfile

import openpyxl
from openpyxl.utils.cell import coordinate_from_string, column_index_from_string, range_boundaries


ARCHIVE_SHA = "9cf7228b54f1edcdd4b372eb736774adf29cb4f804c9920229bac6c154833399"


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_targets(workspace):
    _, *ledger = [json.loads(value) for value in (workspace/"RAW.jsonl").read_bytes().splitlines()]
    answers = [row for row in ledger if row["stratum"] == "answer" and row["status"] == "recalculated"]
    files, missing, numeric_errors = {}, {}, {}
    for row in answers:
        path = workspace / "private-discrepancies" / row["id"] / "A6.json"
        if not path.is_file():
            continue
        details = json.loads(path.read_bytes())
        files[row["id"]] = path.parent
        missing[row["id"]] = {(r["sheet"], r["cell"]) for r in details if r["original"][1] is None}
        numeric_errors[row["id"]] = {(r["sheet"], r["cell"]) for r in details
                                     if r["original"][0] == "n" and r["original"][1] is not None
                                     and r["export"] is not None and r["export"][0] == "e"}
    largest, cluster = max(numeric_errors.items(), key=lambda pair: len(pair[1]))
    if (sum(map(len, missing.values())), len(cluster)) != (2389, 42042):
        raise ValueError("population differs from the frozen A6 analysis")
    return {identity: (files[identity], cells, cluster if identity == largest else set())
            for identity, cells in missing.items() if cells or identity == largest}


def archive_scope(archive, identities):
    tasks, selected = None, {}
    with tarfile.open(archive, "r|gz") as source:
        for member in source:
            path = PurePosixPath(member.name)
            if path.name == "dataset.json":
                raw = source.extractfile(member).read()
                tasks = {str(row["id"]): row for row in json.loads(raw)}
            elif path.name.endswith("_answer.xlsx"):
                key = hashlib.sha256(("pvl-eab-e4-v1:" + member.name).encode()).hexdigest()
                if key in identities:
                    selected[key] = path.parent.name, int(path.name.split("_", 1)[0])
    if tasks is None or len(tasks) != 912 or selected.keys() != identities or any(task not in tasks for task, _ in selected.values()):
        raise ValueError("frozen task metadata or archived answer roster mismatch")
    return tasks, selected, hashlib.sha256(raw).hexdigest()


def grading_ranges(path, answer_position):
    with path.open("rb") as source:
        wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
        try:
            sheets = wb.sheetnames
        finally:
            wb.close()
    regions = defaultdict(list)
    for item in answer_position.split(","):
        sheet, interval = item.split("!") if "!" in item else (sheets[0], item)
        bounds = range_boundaries(interval.strip("'"))
        if any(v is None for v in bounds):
            raise ValueError("unbounded answer position")
        regions[sheet.strip("'")].append(bounds)
    return regions, bool(regions.keys() - set(sheets))


def inside(regions, cell):
    sheet, address = cell
    letters, row = coordinate_from_string(address)
    col = column_index_from_string(letters)
    return any(left <= col <= right and top <= row <= bottom
               for left, top, right, bottom in regions[sheet])


def grader(compare, original, other, meta):
    try:
        with redirect_stdout(StringIO()):
            passed, _ = compare(str(original), str(other), meta["instruction_type"], meta["answer_position"])
    except Exception as exc:
        return "exception:" + type(exc).__name__
    return "pass" if passed else "fail"


def main():
    p = argparse.ArgumentParser()
    for name in ("archive", "a6_workspace", "stock_evaluation"):
        p.add_argument(name, type=Path)
    p.add_argument("evaluator_sha256")
    a = p.parse_args()
    if sha(a.archive) != ARCHIVE_SHA or sha(a.stock_evaluation) != a.evaluator_sha256:
        raise ValueError("archive or scorer identity changed")
    targets = read_targets(a.a6_workspace)
    tasks, mapping, metadata_sha = archive_scope(a.archive, targets.keys())
    compare = runpy.run_path(str(a.stock_evaluation))["compare_workbooks"]
    observations, groups = [], {"missing_cache": Counter(), "textafter": Counter()}
    graded = Counter()
    task_union = defaultdict(set)
    for identity, (directory, missing, textafter) in sorted(targets.items()):
        task, slot = mapping[identity]
        meta = tasks[task]
        label = hashlib.sha256(("a10:task:" + task).encode()).hexdigest()
        original, exported = directory/"input.xlsx", directory/"output.xlsx"
        try:
            ranges, missing_sheet = grading_ranges(original, meta["answer_position"])
        except Exception as exc:
            raise ValueError(f"unresolved grading ranges for {identity}: {type(exc).__name__}") from None
        base, changed = grader(compare, original, original, meta), grader(compare, original, exported, meta)
        graded[base + " -> " + changed] += 1
        record = {"workbook": identity, "task": label, "slot": slot, "original_against_original": base,
                  "original_against_recalculated": changed, "missing_original_grading_sheet": missing_sheet,
                  "groups": {}}
        for reason, cells in (("missing_cache", missing), ("textafter", textafter)):
            if not cells:
                continue
            hit = sum(inside(ranges, cell) for cell in cells)
            counts = groups[reason]
            counts["cells"] += len(cells)
            counts["workbooks"] += 1
            counts["cells_in_answer_position"] += hit
            counts["workbooks_with_intersection"] += int(bool(hit))
            counts["intersecting_workbooks_pass_to_fail"] += int(bool(hit) and base == "pass" and changed == "fail")
            task_union[reason + "_all"].add(label)
            if hit:
                task_union[reason + "_intersect"].add(label)
            record["groups"][reason] = {"cells": len(cells), "in_answer_position": hit}
        observations.append(record)
    print(json.dumps({
        "archive_sha256": ARCHIVE_SHA, "metadata_sha256": metadata_sha,
        "evaluator_sha256": a.evaluator_sha256, "openpyxl": openpyxl.__version__,
        "targeted_workbooks": len(observations), "grader_transitions": graded,
        "groups": {name: dict(group, tasks=len(task_union[name+"_all"]),
                              tasks_with_intersection=len(task_union[name+"_intersect"])) for name, group in groups.items()},
        "observations": observations,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
