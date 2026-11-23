"""Replay the previously selected physical left-occurrence projection."""

import argparse
import hashlib
import json
from pathlib import Path

import duckdb


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("rollups", type=Path)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_bytes())
    sample = receipt["per_left_row_product"]["fixed_stride_sample"]
    with duckdb.connect() as db:
        rows = []
        for arm in ("exact", "right_float64"):
            file = args.rollups / f"{arm}.parquet"
            source = receipt["native_arms"][arm]
            with file.open("rb") as handle:
                if hashlib.file_digest(handle, "sha256").hexdigest() != source["rollup_sha256"]:
                    raise ValueError("private rollup has changed since its native receipt")
            values = db.execute("""SELECT shard, source_row, userid, matched_pairs
                FROM read_parquet(?) WHERE source_row % ? = 0 ORDER BY shard, source_row""",
                                [str(file), sample["stride"]]).fetchall()
            if len(values) != sample["rows_per_arm"]:
                raise ValueError("sample size differs from the pinned physical projection")
            rows.append(values)
    if [row[:3] for row in rows[0]] != [row[:3] for row in rows[1]] or rows[0] == rows[1]:
        raise ValueError("sample failed to retain corresponding left occurrences and a match-count fault")
    print(json.dumps([["benchmark_sample", "clickbench-userid-join", "M6_right_float64", False, *rows]],
                     allow_nan=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
