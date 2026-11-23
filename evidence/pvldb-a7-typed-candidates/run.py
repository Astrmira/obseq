"""Run the pinned ClickBench workload once and retain private typed candidates."""

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import runpy

import duckdb
import pyarrow as pa


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def save_arrow(table, path):
    temp = path.with_suffix(".tmp")
    with temp.open("wb") as stream, pa.ipc.new_file(stream, table.schema) as writer:
        writer.write_table(table)
    os.replace(temp, path)
    return sha(path)


def collect(db, queries, capture_dir, ledger, source_sha):
    selected = {}
    fields = ["query", "threads", "status", "rows", "columns",
              "same_order_as_first_arm", "same_bag_as_first_arm"]
    writer = csv.DictWriter(ledger, fieldnames=fields)
    writer.writeheader()
    prior = {}
    success = {8: 0, 1: 0}
    manifest_path = capture_dir / "manifest.jsonl"
    with manifest_path.open("x", encoding="utf-8") as manifest:
        for threads in (8, 1):
            db.execute(f"SET threads={threads}")
            for number, query in enumerate(queries, 1):
                result = {"query": number, "threads": threads}
                try:
                    table = db.execute(query).fetch_arrow_table()
                except duckdb.Error as exc:
                    result["status"] = type(exc).__name__
                else:
                    name = f"q{number:02d}-t{threads}.arrow"
                    fingerprint = save_arrow(table, capture_dir / name)
                    rows = list(zip(*(column.to_pylist() for column in table.columns)))
                    if number in (18, 25):
                        selected[threads, number] = rows
                    if threads == 8:
                        prior[number] = rows
                    first = prior.pop(number, None) if threads == 1 else rows
                    result.update(
                        status="ok", rows=table.num_rows, columns=table.num_columns,
                        same_order_as_first_arm=rows == first if first is not None else "",
                        same_bag_as_first_arm=Counter(rows) == Counter(first) if first is not None else "",
                    )
                    success[threads] += 1
                    result["candidate"] = name
                    result["candidate_sha256"] = fingerprint
                evidence = dict(result, sql_sha256=hashlib.sha256(query.encode()).hexdigest(),
                                acquisition_sha256=source_sha, duckdb=duckdb.__version__,
                                pyarrow=pa.__version__)
                print(json.dumps(evidence, sort_keys=True), file=manifest, flush=True)
                writer.writerow({field: result.get(field) for field in fields})
                ledger.flush()
                print(f"threads={threads} q={number} status={result['status']}", flush=True)
    return selected, success


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("acquisition", type=Path)
    parser.add_argument("stock_sql", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("stores", type=Path, nargs=2)
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    original = runpy.run_path(str(args.upstream))
    stock = args.stock_sql.read_bytes()
    if hashlib.sha256(stock).hexdigest() != original["STOCK_SHA"]:
        raise ValueError("stock SQL fingerprint mismatch")
    if (duckdb.__version__, pa.__version__) != ("1.4.3", "22.0.0"):
        raise ValueError("native runtime version mismatch")
    queries = [line for line in stock.decode().splitlines() if line.strip()]
    if len(queries) != 43:
        raise ValueError("expected 43 stock queries")
    shards = original["load_shards"](args.acquisition, args.stores)
    paths = ", ".join(map(original["sql_string"], shards))
    args.output.mkdir(parents=True, exist_ok=True)
    private = args.output / "private-candidates"
    private.mkdir(mode=0o700)
    source_sha = sha(args.acquisition)
    with duckdb.connect(config={"memory_limit": "40GB", "temp_directory": str(args.output / "spill")}) as db:
        db.execute(f"CREATE VIEW raw AS SELECT * FROM read_parquet([{paths}],binary_as_string=true)")
        db.execute("""
            CREATE VIEW hits AS SELECT * REPLACE (
                DATE '1970-01-01' + CAST(EventDate AS INTEGER) AS EventDate,
                make_timestamp(EventTime * 1000000) AS EventTime
            ) FROM raw
        """)
        physical = db.execute("SELECT count(*), min(EventTime), max(EventTime), min(EventDate), max(EventDate) FROM raw").fetchone()
        logical = db.execute("""
            SELECT count(*), min(epoch(EventTime)), max(epoch(EventTime)),
                min(EventDate-DATE '1970-01-01'), max(EventDate-DATE '1970-01-01')
            FROM hits
        """).fetchone()
        if physical[0] != original["POPULATION"] or physical != logical:
            raise ValueError("physical/logical adapter mismatch")
        with (args.output / "queries.csv").open("x", newline="", encoding="utf-8") as ledger:
            observed, success = collect(db, queries, private, ledger, source_sha)
    family = original["independent_stock_families"](shards, observed)
    receipt = {
        "source_shards": len(shards), "source_rows": original["POPULATION"],
        "acquisition_sha256": source_sha, "stock_sql_sha256": original["STOCK_SHA"],
        "duckdb": duckdb.__version__, "pyarrow": pa.__version__,
        "successful_queries_by_threads": success, "two_independent_family_checks": family,
    }
    (args.output / "RESULT.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if any(count != 43 for count in success.values()) or not all(family["observed_membership"].values()):
        raise SystemExit("retained receipts include a failed query or family validation")


if __name__ == "__main__":
    main()
