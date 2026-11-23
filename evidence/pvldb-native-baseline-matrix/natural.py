"""Apply the common comparator matrix to selected archived E9 native release pairs."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import runpy

from tabular import VERSIONS, compare


def cases(read):
    ordinary = read("e9-native-ordinary-correctness-release-controls", "RESULT.json")
    for row in ordinary["pandas"]:
        yield ("group-null-reassignment", row["version"], row["expected"], row["native"],
               ("text", "int", "int"), (0, 1), row["exact"])
    for row in ordinary["polars"]:
        native = [[r["ward"], r["null"]] for r in row["native_records"]]
        yield ("pivot-null-buckets", row["version"], row["expected_null_bucket"], native,
               ("text", "int"), (0,), row["exact_null_bucket"])

    for version in ("1.5.5", "2.0.1"):
        content = read("e9-native-f2-roster-topn-null", version + ".raw")
        partitions = {}
        for mode, group, rank in csv.reader(content.splitlines()):
            partitions.setdefault(mode, []).append([int(group), int(rank)])
        reference = [[3, 1], [3, 2]]
        if partitions["noopt"] != reference or partitions["nonnull"] != reference:
            raise ValueError("unexpected ROW_NUMBER negative or positive control")
        yield ("null-sort-topn", version, reference, partitions.get("target", []),
               ("int", "int"), (0, 1), version == "2.0.1")

    for row in read("e9-native-f3-prepared-snapshot", "RESULT.json"):
        reference = row["fresh_after"]
        if reference != row["parameterized_after"] or reference != [2, 3]:
            raise ValueError("unexpected exact prepared snapshot control")
        def count_rows(counts):
            return [[sensor, count] for sensor, count in zip((10, 20), counts, strict=True)]
        yield ("prepared-snapshot-count", row["duckdb"], count_rows(reference),
               count_rows(row["prepare_after"]), ("int", "int"), (0,), row["duckdb"] == "2.0.1")

    history = read("e9-native-historical-f1-f8-controls", "RESULT.json")
    for cohort in history:
        if cohort["case"] not in {"pl-int", "pl-tz", "pd-tz"}:
            continue
        for arm in cohort["arms"]:
            row = arm["result"]
            if cohort["case"] == "pl-int":
                native = row["observed"]
                yield ("uint64-mixed-input", row["version"], list(map(list, enumerate(row["expected"]))),
                       [list(item) for item in zip(native["rank"], native["values"], strict=True)],
                       ("int", "uint"), (0,), row["passes"])
            elif cohort["case"] == "pl-tz":
                native = row["observed"]
                yield ("nested-timezone", row["version"], [[row["expected"], "Europe/Amsterdam"]],
                       [[native["epoch_microseconds"], native["time_zone"]]],
                       ("int", "text"), (), row["passes"])
            else:
                yield ("melt-timezone", row["version"], row["expected"], row["observed"]["typed"],
                       ("int", "text", "text"), (0, 1), row["passes"])

    for version in ("0.20.3", "0.20.4"):
        row = read("e9-native-o4-categorical-logical-equality", version + ".json")
        buckets = sorted(row["membership"]["True"].items())
        yield ("categorical-membership-logical-equality", version,
               [[key, True, False] for key, _ in buckets],
               [[key, *r["positive"], *r["negative"]] for key, r in buckets],
               ("text", "bool", "bool"), (0,), version == "0.20.4")


def main(case_factory=cases):
    parser = argparse.ArgumentParser()
    for name in ("archive", "a2_runner", "e2_source"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    e2 = runpy.run_path(str(args.a2_runner))["observer"](args.e2_source)
    hashes = {}
    def read(packet, filename):
        file = args.archive / packet / filename
        raw = file.read_bytes()
        hashes[f"{packet}/{filename}"] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw) if file.suffix == ".json" else raw.decode()
    observations = []
    for family, version, reference, candidate, kinds, keys, legal in case_factory(read):
        if not legal and reference == candidate:
            raise ValueError(f"projection dropped the source fault for {family} at {version}")
        observations.append({"family": family, "version": version, "legal": legal,
                             "reference": reference, "candidate": candidate,
                             "generic": e2(reference, candidate, None, None, None),
                             **compare(reference, candidate, kinds, keys=keys)})
    print(json.dumps({"families": len({x["family"] for x in observations}),
                      "versions": VERSIONS, "source_sha256": hashes,
                      "observations": observations}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
