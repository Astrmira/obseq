"""Bind public inputs for a fresh full-window timing run on Linux."""

import argparse
import json
from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[2]
PACKET = Path(__file__).resolve().parent
STOCK_SHA = "274ffe1c4f83baad2fc177bbb6773bbdab0db779faeb2970de8cc531292a5dc6"


def load_shards(acquisition, stores):
    manifest = json.loads(acquisition.read_bytes())
    if sorted(row["part"] for row in manifest) != list(range(100)):
        raise ValueError("Expected the complete 100-part publisher manifest")
    verify = runpy.run_path(str(ROOT / "fetch_clickbench.py"))["verify"]
    shards = []
    for row in sorted(manifest, key=lambda item: item["part"]):
        matches = [store / f"hits_{row['part']}.parquet" for store in stores]
        path = next((path for path in matches if path.is_file()), None)
        if path is None:
            raise FileNotFoundError(f"Missing publisher partition {row['part']}")
        verify(path, row)
        shards.append(path.resolve())
    return shards


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tpch", type=Path, required=True)
    parser.add_argument("--tpcds", type=Path, required=True)
    parser.add_argument("--clickbench-store", type=Path, action="append", required=True)
    parser.add_argument("--spill", type=Path, required=True)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    inventory = ROOT / "evidence/pvldb-a1-query-inventory"
    args.spill.mkdir(parents=True, exist_ok=True)
    config = {
        "upstream": str(Path(__file__).resolve()),
        "validator": str(inventory),
        "acquisition": str(ROOT / "evidence/pvldb-a7-typed-candidates/FULL-ACQUISITION.json"),
        "stores": [str(path.resolve()) for path in args.clickbench_store],
        "databases": {"tpch": str(args.tpch.resolve()), "tpcds": str(args.tpcds.resolve())},
        "queries": {"tpch": str(PACKET / "sql-tpch-143.json"),
                    "tpcds": str(PACKET / "sql-tpcds-143.json"), "clickbench": str(PACKET / "stock.sql")},
        "censuses": {"tpch": str(inventory / "TPCH-SF10-CUTOFFS.jsonl"),
                     "tpcds": str(inventory / "TPCDS-SF10-CUTOFFS.jsonl"),
                     "clickbench": str(PACKET / "CLICKBENCH-CUTOFFS.jsonl")},
        "spill": str(args.spill.resolve()),
    }
    freeze = runpy.run_path(str(PACKET / "ast_cost.py"))["freeze"]
    freeze(config, args.output)


if __name__ == "__main__":
    main()
