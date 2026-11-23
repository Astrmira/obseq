"""Run native DVC and Great Expectations as two additional E5 configurations."""

import argparse
from collections import Counter, defaultdict
import hashlib
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import pandas as pd

from later import projected_cases


GX = "1.25.0"
DVC = "3.66.1"


def entries(matrix, panels, representative, value_driver):
    def read(name):
        return json.loads((matrix / f"{name}-RESULT.json").read_bytes())["observations"]
    for row in read("ORIGINAL"):
        yield "original", row["id"], "frozen_candidate", row["legal"], row["reference_rows"], row["candidate_rows"]
    for panel, (identity, arm, reference, candidate, _kinds, _keys, legal) in projected_cases(panels, representative, value_driver):
        if arm != "alternate_decimal_diagnostic":
            yield "later", f"{panel}/{identity}", arm, legal, reference, candidate
    for packet in ("NATURAL", "NATURAL-EXTENDED"):
        for row in read(packet):
            yield "natural", row["family"], row["version"], row["legal"], row["reference"], row["candidate"]


def fingerprints(pairs):
    import yaml

    with TemporaryDirectory(prefix="e5-dvc-pairs-") as tmp:
        directory = Path(tmp)
        config = directory / "config"
        config.mkdir()
        env = os.environ | {"DVC_NO_ANALYTICS": "1", "XDG_CONFIG_HOME": str(config),
                            "XDG_CACHE_HOME": str(config)}
        def dvc(*args):
            return subprocess.check_output([sys.executable, "-B", "-m", "dvc", *args], cwd=directory, env=env)
        if dvc("--version").decode().strip() != DVC:
            raise ValueError("unexpected DVC version")
        dvc("init", "--no-scm")
        dvc("config", "cache.type", "copy")
        paths = {}
        for index, (_, _, _, _, left, right) in enumerate(pairs):
            for arm, rows in (("gold", left), ("candidate", right)):
                filename = f"{index:04d}-{arm}.json"
                payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
                (directory / filename).write_bytes(payload)
                paths[filename] = (len(payload), hashlib.md5(payload).hexdigest())
        dvc("add", *paths)
        observed = {}
        for filename, expected in paths.items():
            pointer = yaml.safe_load((directory / f"{filename}.dvc").read_bytes())["outs"][0]
            if pointer["path"] != filename or pointer["hash"] != "md5" or (pointer["size"], pointer["md5"]) != expected:
                raise ValueError(f"unexpected DVC file pointer for {filename}")
            observed[filename] = pointer["md5"]
        return [observed[f"{i:04d}-gold.json"] == observed[f"{i:04d}-candidate.json"] for i in range(len(pairs))]


def shape(pairs):
    os.environ["GX_ANALYTICS_ENABLED"] = "false"
    import great_expectations as gx

    if version("great-expectations") != GX:
        raise ValueError("unexpected Great Expectations version")
    logging.disable(logging.WARNING)
    context = gx.get_context(mode="ephemeral")
    definition = context.data_sources.add_pandas("pd").add_dataframe_asset("output").add_batch_definition_whole_dataframe("case")
    decisions = []
    for _, _, _, _, left, right in pairs:
        count = gx.expectations.ExpectTableRowCountToEqual(value=len(left))
        batch = definition.get_batch(batch_parameters={"dataframe": pd.DataFrame(right)})
        verdict = batch.validate(count)
        if verdict.exception_info.get("raised_exception"):
            raise ValueError(verdict.exception_info)
        decisions.append(bool(verdict.success))
    return decisions


def main():
    p = argparse.ArgumentParser()
    for name in ("matrix", "panels", "representative", "value_driver"):
        p.add_argument(name, type=Path)
    args = p.parse_args()
    pairs = list(entries(args.matrix, args.panels, args.representative, args.value_driver))
    dvc, gx = fingerprints(pairs), shape(pairs)
    summaries = defaultdict(lambda: defaultdict(Counter))
    observations = []
    for (cohort, identity, arm, legal, _, _), exact_file, count in zip(pairs, dvc, gx, strict=True):
        decisions = {"dvc_fingerprint": exact_file, "great_expectations_rowcount": count}
        for method, value in decisions.items():
            outcome = ("true_" if value == legal else "false_") + ("accept" if value else "reject")
            summaries[cohort][method][outcome] += 1
        observations.append({"cohort": cohort, "id": identity, "arm": arm, "legal": legal, **decisions})
    print(json.dumps({"versions": {"dvc": DVC, "great_expectations": GX}, "summaries": summaries,
                      "observations": observations}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
