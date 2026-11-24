"""Run the original O2 and O3 workers on a user-supplied 100M H2O snapshot."""

import argparse
import json
import os
from pathlib import Path
import random
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("h2o_root", type=Path)
    parser.add_argument("cpu", type=int)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    os.sched_setaffinity(0, {args.cpu})
    os.environ["H2O_ROOT"] = str(args.h2o_root.resolve())
    hive = args.h2o_root / "native-100m-hive"
    output = Path.cwd()

    def worker(driver, *argv):
        return json.loads(subprocess.check_output(
            [sys.executable, "-IB", str(here / driver), *map(str, argv)], text=True))

    specs = [
        ("O2", "epoch.py", (), ("producer", "exact", "epoch"), 130139, ()),
        ("TOPK", "topk.py", (hive, "worker", "--n", 100_000_000),
         ("producer", "guard", "family"), 40069, (1000, 100000, 1000000, 10000000)),
        ("REP", "representative.py", (hive, "worker", "--size", 100_000_000),
         ("producer", "claimed", "family"), 80137, (1000, 100000, 1000000, 10000000)),
    ]
    for name, driver, prefix, arms, seed, preceding_scales in specs:
        print(f"Starting {name}", flush=True)
        if name != "O2":
            controls = worker(driver, hive, "validate", "--cpu", args.cpu)
            (output / f"{name}-CONTROLS.json").write_text(json.dumps(controls, indent=2) + "\n")
        rng = random.Random(seed)
        # Keep the original arm randomization at 100M without running the smaller scales.
        for _ in preceding_scales:
            for _ in range(5):
                ignored_order = list(arms)
                rng.shuffle(ignored_order)
        with (output / f"{name}-RAW.jsonl").open("x", encoding="utf-8") as stream:
            for rep in range(5):
                order = list(arms)
                rng.shuffle(order)
                for arm in order:
                    command = (*prefix, "--arm", arm, "--cpu", args.cpu) if prefix else (arm,)
                    print(json.dumps({"rep": rep, **worker(driver, *command)}, sort_keys=True),
                          file=stream, flush=True)
        if name == "O2":
            controls = worker(driver, "control")
            (output / f"{name}-CONTROLS.json").write_text(json.dumps(controls, indent=2) + "\n")
        print(f"Finished {name}", flush=True)


if __name__ == "__main__":
    main()
