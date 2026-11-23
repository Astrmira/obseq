"""Export typed comparator inputs from the seven earlier native release pairs."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import runpy
import sys


def earlier(archive, arm, new_site):
    if arm in {"old", "new"}:
        sys.path.insert(0, str(new_site.resolve()))
        import numpy as np
        if arm == "old":
            sys.path.pop(0)
        import pandas as pd
        versions = {"old": "2.2.3", "new": "3.1.1"}
        if (pd.__version__, np.__version__) != (versions[arm], "2.5.5"):
            raise ValueError("old/new pandas replay environment differs")
        pilot = runpy.run_path(str(archive / "pilot.py"))
        captures = []

        def observer(reference, candidate, *_):
            captures.append((reference, candidate))
            return {}

        if arm == "old":
            with pd.option_context("mode.copy_on_write", True):
                rows = list(pilot["positional"](pd, arm, observer))
        else:
            rows = list(pilot["positional"](pd, arm, observer))
        rows.extend(pilot["timedelta"](pd, np, arm, observer))
        source = archive / ("OLD-PILOT.json" if arm == "old" else "NEW-PILOT.json")
        frozen = json.loads(source.read_bytes())["rows"]
        for row, expected, (left, right) in zip(rows, frozen, captures, strict=True):
            metadata = {k: v for k, v in row.items() if k != "observers"}
            if "input" in metadata:
                metadata["input"] = list(metadata["input"])
            if metadata != {k: v for k, v in expected.items() if k != "observers"}:
                raise ValueError("earlier pilot row differs from the frozen receipt")
            yield row["family"], arm, row["legal"], left, right
        return

    native = runpy.run_path(str(archive / "paired_pandas.py"))
    if (native["pd"].__version__, native["np"].__version__) != (arm, "2.3.5"):
        raise ValueError("paired pandas replay environment differs")
    frozen = json.loads((archive / f"PAIRED-PANDAS-{arm}.json").read_bytes())["observations"]
    for (family, case, left, right, _), expected in zip(native["outputs"](archive), frozen, strict=True):
        legal = left == right
        if (family, case, legal) != (expected["family"], expected["case"], expected["legal"]):
            raise ValueError("paired release row differs from the frozen receipt")
        yield family, arm, legal, left, right


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("arm", choices=("old", "new", "2.3.3", "3.0.0"))
    parser.add_argument("--new-site", type=Path)
    args = parser.parse_args()
    if args.arm in {"old", "new"} and args.new_site is None:
        parser.error("--new-site is required for the old and new pilot environments")
    counts = defaultdict(int)
    result = []
    for family, arm, legal, left, right in earlier(args.archive, args.arm, args.new_site):
        idx = counts[family]
        counts[family] += 1
        result.append(["natural", family, f"{arm}:{idx}", legal, left, right])
    print(json.dumps(result, allow_nan=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
