"""Measure the E2 common observers on two original E9 native bug families."""

import argparse
from collections import Counter
import itertools
import json
from pathlib import Path
import runpy
import sys


def compare(observer, reference, output):
    # These native observations have no archived serialized carrier or SQLite stage.
    return observer(reference, output, None, None, None)


def positional(pd, version, observer):
    original = {"east": [1, 2, 3], "west": [10, 20, 30], "spare": [300, 400, 500]}
    swapped = {**original, "east": original["west"], "west": original["east"]}
    for shallow, mode in itertools.product((False, True), ("positional_frame", "positional_array", "labelled_frame")):
        frame = pd.DataFrame(original)
        previous = frame.copy(deep=not shallow)
        rhs = frame[["east", "west"]]
        if mode == "labelled_frame":
            frame.loc[:, ["west", "east"]] = rhs
            expected = original
        else:
            frame.iloc[:, [1, 0]] = rhs if mode == "positional_frame" else rhs.to_numpy(copy=True)
            expected = swapped
        if previous.to_dict("list") != original or list(frame.columns) != list(original):
            raise ValueError("positional replay changed an out-of-contract field")
        native = list(map(list, zip(*(frame[column].tolist() for column in original))))
        reference = list(map(list, zip(*expected.values())))
        legal = native == reference
        if legal != (version == "new" or mode == "labelled_frame"):
            raise ValueError("positional replay drifted from the original receipt")
        yield {"family": "pandas-reversed-positional-write", "mode": mode, "shallow": shallow,
               "legal": legal, "observers": compare(observer, reference, native)}


def timedelta(pd, np, version, observer):
    for magnitude, residual in itertools.product((2**20, 2**55, 2**61), (-7, -1, 0, 1, 7)):
        inputs = (magnitude + residual, -magnitude, 0)
        for order in sorted(set(itertools.permutations(inputs))):
            series = pd.Series(pd.to_timedelta(np.array(order, dtype=np.int64), unit="ns"))
            if tuple(int(x.value) for x in series) != order:
                raise ValueError("native input lost integer nanoseconds")
            expected = sum(order)
            outputs = {"series": series.sum(), "frame": series.to_frame("delta").sum().iloc[0],
                       "group": series.groupby([0] * len(series)).sum().iloc[0]}
            for mode, value in outputs.items():
                native = int(value.value)
                legal = native == expected
                if (version == "new" or mode == "group" or magnitude < 2**53 or residual == 0) and not legal:
                    raise ValueError("timedelta replay drifted from the original receipt")
                yield {
                    "family": "pandas-timedelta-cancellation", "mode": mode, "input": order,
                    "legal": legal, "observers": compare(observer, [[expected]], [[native]]),
                }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("new_site", type=Path)
    parser.add_argument("arm", choices=("old", "new"))
    parser.add_argument("a2_observer_module", type=Path)
    parser.add_argument("e2_frozen_source", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.new_site.resolve()))
    import numpy as np
    if args.arm == "old":
        sys.path.pop(0)
    import pandas as pd
    if pd.__version__ != {"old": "2.2.3", "new": "3.1.1"}[args.arm] or np.__version__ != "2.5.5":
        raise ValueError("natural-replay pinned runtime mismatch")
    observer = runpy.run_path(str(args.a2_observer_module))["observer"](args.e2_frozen_source)
    if args.arm == "old":
        with pd.option_context("mode.copy_on_write", True):
            rows = list(positional(pd, args.arm, observer))
    else:
        rows = list(positional(pd, args.arm, observer))
    rows.extend(timedelta(pd, np, args.arm, observer))
    failures = Counter((row["family"], row["mode"]) for row in rows if not row["legal"])
    if args.arm == "old" and failures != {
        ("pandas-reversed-positional-write", "positional_frame"): 2,
        ("pandas-reversed-positional-write", "positional_array"): 2,
        ("pandas-timedelta-cancellation", "series"): 48,
        ("pandas-timedelta-cancellation", "frame"): 48,
    }:
        raise ValueError("native fault counts differ from the original replay")
    print(json.dumps({"arm": args.arm, "numpy": np.__version__, "pandas": pd.__version__,
                      "rows": rows}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
