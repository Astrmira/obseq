"""Run common E5 configurations on an explicit set of frozen comparison pairs."""

import argparse
import json
from pathlib import Path


FRAME_METHODS = ("pandas_default", "pandas_check_like", "pandas_dtype_relaxed",
                 "polars_default", "polars_ignore_order", "datacompy_keyed")
TYPES = {int: "int", float: "float", str: "text", bool: "bool"}
BENCHMARK_KEYS = {
    "clickbench-18": (0, 1),
    "clickbench-25": None,
    "clickbench-31": (0, 1),
    "clickbench-32": (0, 1),
    "clickbench-33": (0, 1),
    "clickbench-39": (0,),
    "clickbench-40": (0, 1, 2, 3, 4),
    "clickbench-41": (0, 1),
    "clickbench-42": (0, 1),
    "tpcds-39": (0, 1),
    "tpcds-59": None,
    "tpcds-86": None,
    "tpch-11": (0,),
    "tpch-21": (0,),
}


def carrier(left, right):
    if len({len(row) for row in (*left, *right)}) != 1:
        return None
    kinds = []
    for column in zip(*left, *right):
        types = {type(value) for value in column if value is not None}
        if not types:
            kinds.append("text")
        elif len(types) != 1 or next(iter(types)) not in TYPES:
            return None
        elif types == {int} and any(value is not None and value >= 2**63 for value in column):
            if any(value is not None and not 0 <= value < 2**64 for value in column):
                return None
            kinds.append("uint")
        else:
            kinds.append(TYPES[next(iter(types))])
    return kinds


def frames(pairs):
    from tabular import VERSIONS, compare

    verdicts = []
    for _, _, _, _, left, right in pairs:
        kinds = carrier(left, right)
        verdicts.append(compare(left, right, kinds)["tool_verdicts"] if kinds is not None
                        else dict.fromkeys(FRAME_METHODS))
    return VERSIONS, verdicts


def fingerprint_and_shape(pairs):
    from file_and_shape import DVC, GX, fingerprints, shape

    verdicts = [{"dvc_fingerprint": dvc, "great_expectations_rowcount": gx}
                for dvc, gx in zip(fingerprints(pairs), shape(pairs), strict=True)]
    return {"dvc": DVC, "great_expectations": GX}, verdicts


def key_diagnostic(pairs):
    from tabular import PINNED, VERSIONS, compare_datacompy, frames

    if VERSIONS != PINNED:
        raise ValueError(f"unexpected E5 environment: {VERSIONS}")
    observations = []
    for cohort, number, arm, legal, left, right in pairs:
        if cohort != "benchmark":
            continue
        keys = BENCHMARK_KEYS[number]
        kinds = carrier(left, right)
        if kinds is None:
            positional, natural = (None, "unsupported_carrier"), (None, "unsupported_carrier")
        else:
            lhs, _ = frames(left, kinds)
            rhs, _ = frames(right, kinds)
            positional = compare_datacompy(lhs, rhs)
            natural = compare_datacompy(lhs, rhs, keys=keys) if keys else (
                None, "inapplicable_natural_key")
        observations.append({
            "cohort": cohort, "id": number, "arm": arm, "legal": legal,
            "key_columns": keys,
            "datacompy_positional": positional[0],
            "datacompy_natural_key": natural[0],
            "positional_error": positional[1],
            "natural_key_error": natural[1],
        })
    return {"versions": VERSIONS, "observations": observations}


def logic_tests(pairs, args):
    from slt import PORT, boot, decide
    import duckdb

    harness = boot(args.slt_root, args.old_adapter, args.upstream_seal)
    with duckdb.connect(config={"enable_external_access": False, "threads": 1}) as db:
        verdicts = [decide(db, harness, left, right)[0] for _, _, _, _, left, right in pairs]
    return {"duckdb": duckdb.__version__, "port": PORT}, verdicts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("frames", "extra", "slt", "keys"))
    parser.add_argument("pairs", type=Path)
    for flag in ("slt-root", "old-adapter", "upstream-seal"):
        parser.add_argument("--" + flag, type=Path)
    args = parser.parse_args()
    pairs = json.loads(args.pairs.read_bytes())
    if args.mode == "keys":
        print(json.dumps(key_diagnostic(pairs), indent=2, sort_keys=True))
        return
    if args.mode == "slt":
        versions, verdicts = logic_tests(pairs, args)
    else:
        versions, verdicts = (frames if args.mode == "frames" else fingerprint_and_shape)(pairs)
    observations = [{"cohort": cohort, "id": name, "arm": arm, "legal": legal, **decision}
                    for (cohort, name, arm, legal, _, _), decision in zip(pairs, verdicts, strict=True)]
    print(json.dumps({"versions": versions, "observations": observations}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
