"""Run common comparators across the six independently sealed later E7 panels."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import runpy

from tabular import VERSIONS, compare


GROUP = "heldout-group-role-and-fold-joint"
JSON = "heldout-json-presence-and-path-shape"
ORIENTATION = "heldout-binary64-orientation"
REPRESENTATIVE = "heldout-coherent-group-representatives"


def read(panel, name):
    seals = {}
    for line in (panel / "SHA256SUMS").read_text().splitlines():
        digest, entry = line.split(maxsplit=1)
        seals[entry.lstrip("*").removeprefix("./")] = digest
    data = (panel / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != seals[name]:
        raise ValueError(f"changed frozen inputs: {panel.name}/{name}")
    return json.loads(data)


def token(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sort_rows(rows):
    return sorted(rows, key=token)


def orient(panel):
    labels = {r["id"]: r["sign"] for r in read(panel, "SEALED_LABELS.json")}
    for r in read(panel, "PREDICTIONS.json")["predictions"]:
        reference = [[labels[r["id"]]]]
        for arm in ("stock_geos", "plain_float", "decimal_contract"):
            candidate = [[r[arm]]]
            label = "alternate_decimal_diagnostic" if arm == "decimal_contract" else arm
            yield r["id"], label, reference, candidate, ("int",), (), candidate == reference


def json_path(panel):
    labels = {r["id"]: r for r in read(panel, "SEALED_LABELS.json")}
    for row in read(panel, "PREDICTIONS.json")["predictions"]:
        truth = labels[row["id"]]
        reference = [[truth["status"], truth.get("failure_step"), token(truth.get("value"))]]
        for engine in ("duckdb", "postgres", "sqlite"):
            arm = row[engine]
            candidate = [[arm["status"], arm.get("step"), token(arm.get("value"))]]
            yield row["id"], engine, reference, candidate, ("text", "int", "text"), (), reference == candidate


def groups_and_folds(panel):
    labels = read(panel, "labels.json")
    cases = {r["id"]: r for r in read(panel, "inputs.json")}
    for row in read(panel, "PREDICTIONS.json"):
        identity = row["id"]
        case = cases[identity]
        truth = labels[identity]
        if row["family"] == "group":
            family = {token(sort_rows(b)) for b in truth["role_bags"]}
            reference = json.loads(min(family))
            for arm, values in (("native_projected_member", row["full"]), ("nullness_shortcut", row["rendered_null_mask_full"])):
                serialized = [token(sort_rows(b)) for b in values]
                candidate = json.loads(max(serialized)) if serialized else []
                legal = token(candidate) in family
                yield identity, arm, reference, candidate, ("text", "text", "int", "int"), (), legal
        else:
            family = truth["matching_observation"]
            reference = [min(family)] if family else []
            truncated = [r for r in row["earliest_only"] if r[2] == case["observed_duration"]]
            for arm, values in (("native_duration_member", row["observed_matches"]), ("earliest_only", truncated)):
                candidate = [max(values)] if values else []
                legal = candidate == [] if not family else bool(candidate and candidate[0] in family)
                yield identity, arm, reference, candidate, ("int", "int", "int"), (), legal


def previously_scored(panels, representative, value_driver):
    panel = panels/REPRESENTATIVE
    inputs = read(panel, "CASES.json")
    labels = {r["id"]: r["accepted"] for r in read(panel, "SEALED_LABELS.json")}
    kinds = ("text", "int", "int", "int", "int")
    function = representative["default_output"]
    fields = representative["VISIBLE"]
    for row in inputs:
        reference = function(row["source"])
        candidate = [[r[name] for name in fields] for r in row["candidate"]]
        yield REPRESENTATIVE, (row["id"], "frozen_candidate", reference, candidate, kinds, (0,), labels[row["id"]])
    for name in value_driver["PINS"]:
        panel = panels/name
        source = read(panel, "CASES.json")
        rows, types = value_driver["materialize"](panel, source)
        labels = {r["id"]: r["legal"] for r in read(panel, "SEALED_LABELS.json")}
        kinds = tuple({"object": "text", "Int64": "int"}[kind] for kind in types)
        for identity, reference, candidate in rows:
            yield name, (identity, "frozen_candidate", reference, candidate, kinds, (0,), labels[identity])


def projected_cases(panels, representative_script, value_script):
    representative = runpy.run_path(str(representative_script))
    value_driver = runpy.run_path(str(value_script))
    yield from previously_scored(panels, representative, value_driver)
    for panel, router in ((ORIENTATION, orient), (JSON, json_path), (GROUP, groups_and_folds)):
        yield from ((panel, row) for row in router(panels/panel))


def main():
    p = argparse.ArgumentParser()
    for name in ("panels", "representative", "value_driver", "a2_runner", "e2_source"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    e2 = runpy.run_path(str(a.a2_runner))["observer"](a.e2_source)
    cases = list(projected_cases(a.panels, a.representative, a.value_driver))
    existing = {(panel, row[0]) for panel, row in cases}
    if len(existing) != 138:
        raise ValueError("missing independent cases")
    observations = []
    counters = defaultdict(Counter)
    for panel, (identity, arm, reference, candidate, kinds, key, legal) in cases:
        trial = compare(reference, candidate, kinds, keys=key)
        ordinary = e2(reference, candidate, None, None, None)
        if arm != "alternate_decimal_diagnostic":
            for name, decision in (ordinary | trial["tool_verdicts"]).items():
                tag = ("NA" if decision is None else ("true_" if decision == legal else "false_")
                       + ("accept" if decision else "reject"))
                counters[name][tag] += 1
        observations.append({"panel": panel, "id": identity, "arm": arm, "legal": legal,
                             "generic": ordinary, **trial})
    print(json.dumps({"cases": len(existing), "observations": observations, "versions": VERSIONS,
                      "comparison_cell_summary_excluding_alternate_decimal": counters}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
