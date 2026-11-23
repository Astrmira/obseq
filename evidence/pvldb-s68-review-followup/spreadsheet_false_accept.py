"""Run the pinned SpreadsheetBench grader on missing-cache counterexamples."""

import argparse
from collections import Counter
from contextlib import redirect_stdout
import csv
import hashlib
from io import StringIO
import json
from pathlib import Path, PurePosixPath
import posixpath
import runpy
import tarfile
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as xml
import zipfile

import openpyxl


BOOK = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
FORMULAS = {"positive": "=1000000000", "negative": "=-1000000000"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pick_tasks(receipt):
    by_task = {}
    for row in sorted(receipt["observations"], key=lambda row: row["workbook"]):
        if row["original_against_original"] == "pass" and row["groups"].get("missing_cache", {}).get("in_answer_position"):
            by_task.setdefault(row["task"], row["workbook"])
    if len(by_task) != 19:
        raise ValueError(f"Expected the 19 original qualifying tasks, found {len(by_task)}")
    return {workbook: task for task, workbook in by_task.items()}


def extract(archive, targets, work):
    metadata = None
    identities = {}
    with tarfile.open(archive, "r|gz") as source:
        for member in source:
            path = PurePosixPath(member.name)
            if path.name == "dataset.json":
                raw = source.extractfile(member).read()
                metadata = {str(task["id"]): task for task in json.loads(raw)}
                metadata_sha = hashlib.sha256(raw).hexdigest()
            elif path.name.endswith("_answer.xlsx"):
                key = hashlib.sha256(("pvl-eab-e4-v1:" + member.name).encode()).hexdigest()
                if key in targets:
                    task = hashlib.sha256(("a10:task:" + path.parent.name).encode()).hexdigest()
                    if task != targets[key] or key in identities:
                        raise ValueError("A10 task/workbook identity mismatch")
                    identities[key] = path.parent.name
                    (work / (key + ".xlsx")).write_bytes(source.extractfile(member).read())
    if metadata is None or identities.keys() != targets.keys():
        raise ValueError("Pinned workbook archive did not resolve the frozen roster")
    return {key: metadata[task] for key, task in identities.items()}, metadata_sha


def choose_cell(original, meta, a10):
    ranges, missing = a10["grading_ranges"](original, meta["answer_position"])
    if missing:
        raise ValueError("Missing grading sheet in a self-passing workbook")
    formula = openpyxl.load_workbook(original, data_only=False)
    cached = openpyxl.load_workbook(original, data_only=True)
    try:
        matches = set()
        for sheet, regions in ranges.items():
            for left, top, right, bottom in regions:
                for row in formula[sheet].iter_rows(min_row=top, max_row=bottom, min_col=left, max_col=right):
                    for cell in row:
                        if cell.data_type == "f" and cached[sheet][cell.coordinate].value is None:
                            matches.add((sheet, cell.row, cell.column, cell.coordinate))
        if not matches:
            raise ValueError("No missing-cache formula within the original grading ranges")
        sheet, _, _, cell = min(matches)
        return sheet, cell
    finally:
        formula.close()
        cached.close()


def sheet_member(archive, sheet):
    workbook = xml.fromstring(archive.read("xl/workbook.xml"))
    identity = next(item.attrib[f"{{{OFFICE_RELS}}}id"] for item in workbook.findall(f".//{{{BOOK}}}sheet")
                    if item.attrib["name"] == sheet)
    relationships = xml.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = next(item.attrib["Target"] for item in relationships.findall(f"{{{PACKAGE_RELS}}}Relationship")
                  if item.attrib["Id"] == identity)
    return target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))


def edit_one_cell(original, destination, sheet, address, formula, cached_value=None):
    """Preserve every other ZIP member and every other cell's cached value."""
    with zipfile.ZipFile(original) as source:
        member = sheet_member(source, sheet)
        tree = xml.fromstring(source.read(member))
        cell = next(cell for cell in tree.iter(f"{{{BOOK}}}c") if cell.attrib.get("r") == address)
        expr = cell.find(f"{{{BOOK}}}f")
        expr.attrib.clear()
        expr.text = formula[1:]
        val = cell.find(f"{{{BOOK}}}v")
        if val is None:
            val = xml.SubElement(cell, f"{{{BOOK}}}v")
        val.text = None if cached_value is None else str(cached_value)
        cell.attrib["t"] = "str" if isinstance(cached_value, str) else "n"
        with zipfile.ZipFile(destination, "w") as out:
            for item in source.infolist():
                out.writestr(item, xml.tostring(tree, encoding="utf-8") if item.filename == member else source.read(item))


def check_cell(path, sheet, address, formula, cache):
    for data_only, expected in ((False, formula), (True, cache)):
        wb = openpyxl.load_workbook(path, read_only=True, data_only=data_only)
        try:
            if wb[sheet][address].value != expected:
                raise ValueError("Written formula or cached value differs from the intervention")
        finally:
            wb.close()


def grade(compare, gold, other, meta):
    with redirect_stdout(StringIO()):
        accepted, _ = compare(str(gold), str(other), meta["instruction_type"], meta["answer_position"])
    return accepted


def run(archive, grader_path, a10_path):
    receipt_path = a10_path.with_name("RESULT.json")
    receipt = json.loads(receipt_path.read_bytes())
    if digest(archive) != receipt["archive_sha256"] or digest(grader_path) != receipt["evaluator_sha256"]:
        raise ValueError("Pinned archive or grader digest differs")
    a10 = runpy.run_path(str(a10_path))
    compare = runpy.run_path(str(grader_path))["compare_workbooks"]
    targets = pick_tasks(receipt)
    observations = []
    with TemporaryDirectory(prefix="obseq-xlsx-") as scratch:
        work = Path(scratch)
        tasks, metadata_sha = extract(archive, targets, work)
        if metadata_sha != receipt["metadata_sha256"]:
            raise ValueError("Pinned task metadata differs")
        for workbook, meta in sorted(tasks.items()):
            gold = work / (workbook + ".xlsx")
            sheet, cell = choose_cell(gold, meta, a10)
            base = grade(compare, gold, gold, meta)
            if not base:
                raise ValueError("Original workbook failed its self-comparison")
            row = {"task": targets[workbook], "workbook": workbook,
                   "cell_sha256": hashlib.sha256(f"{workbook}/{sheet}/{cell}".encode()).hexdigest(),
                   "gold_self_comparison": base, "comparisons": {}}
            for key, formula in FORMULAS.items():
                standard = work / f"standard-{key}.xlsx"
                isolated = work / f"isolated-{key}.xlsx"
                wb = openpyxl.load_workbook(gold, data_only=False)
                try:
                    wb[sheet][cell] = formula
                    wb.save(standard)
                finally:
                    wb.close()
                check_cell(standard, sheet, cell, formula, None)
                edit_one_cell(gold, isolated, sheet, cell, formula)
                check_cell(isolated, sheet, cell, formula, None)
                row["comparisons"][key] = {"openpyxl_save": grade(compare, gold, standard, meta),
                                           "isolated_cell": grade(compare, gold, isolated, meta)}
            control = work / "populated-cache.xlsx"
            marker = "OBSEQ-CACHE-PRESENT"
            control_formula = f'="{marker}"'
            edit_one_cell(gold, control, sheet, cell, control_formula, marker)
            check_cell(control, sheet, cell, control_formula, marker)
            row["populated_cache_control_accepts"] = grade(compare, gold, control, meta)
            observations.append(row)
    summary = {}
    for mode in ("openpyxl_save", "isolated_cell"):
        support = Counter(sum(results[mode] for results in row["comparisons"].values()) for row in observations)
        summary[mode] = {"both_variants_accepted": support[2], "one_variant_accepted": support[1],
                         "no_variant_accepted": support[0], "task_count": len(observations)}
    summary["populated_cache_controls_accepted"] = sum(row["populated_cache_control_accepts"] for row in observations)
    return {"a10_receipt_sha256": digest(receipt_path), "archive_sha256": receipt["archive_sha256"],
            "evaluator_sha256": receipt["evaluator_sha256"], "metadata_sha256": metadata_sha,
            "openpyxl": openpyxl.__version__, "summary": summary, "observations": observations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("grader", type=Path)
    parser.add_argument("a10", type=Path)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    result = run(args.archive, args.grader, args.a10)
    if args.csv:
        with args.csv.open("x", encoding="utf-8", newline="") as out:
            writer = csv.writer(out, lineterminator="\n")
            writer.writerow(("task", "workbook", "arm", "mode", "accepted"))
            for row in result["observations"]:
                for arm, modes in row["comparisons"].items():
                    for mode, accepted in modes.items():
                        writer.writerow((row["task"], row["workbook"], arm, mode, accepted))
                writer.writerow((row["task"], row["workbook"], "populated_cache_control",
                                 "isolated_cell", row["populated_cache_control_accepts"]))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
