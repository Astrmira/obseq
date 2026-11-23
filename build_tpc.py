"""Generate a fresh TPC snapshot and stock SQL manifest with a signed extension."""

import argparse
import hashlib
import json
from pathlib import Path

import duckdb


EXTENSIONS = {
    "tpch": ("415c1b36d3e30f0d94b7eba826b03f3628787c5b8a1b1fb6336f002b478bf775", "dbgen", "lineitem"),
    "tpcds": ("0dc0c8fcdc401257a3dceeffc1675111beb6358913ab50ffd46bc24fb581ca02", "dsdgen", "store_sales"),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=EXTENSIONS)
    parser.add_argument("scale", type=int, choices=(1, 10))
    parser.add_argument("extension", type=Path)
    parser.add_argument("database", type=Path)
    parser.add_argument("queries", type=Path)
    args = parser.parse_args()
    if duckdb.__version__ != "1.4.3":
        raise ValueError("TPC snapshots use DuckDB 1.4.3")
    if args.database.exists() or args.queries.exists():
        raise ValueError("use new paths for database and query bundle")
    sha, generator, table = EXTENSIONS[args.suite]
    actual = hashlib.sha256(args.extension.read_bytes()).hexdigest()
    if actual != sha:
        raise ValueError("signed Linux x86-64 extension digest mismatch")
    literal = str(args.extension.resolve()).replace("'", "''")
    with duckdb.connect(str(args.database)) as connection:
        connection.execute(f"LOAD '{literal}'")
        connection.execute(f"CALL {generator}(sf={args.scale})")
        queries = connection.execute(f"SELECT query_nr, query FROM {args.suite}_queries() ORDER BY query_nr").fetchall()
        count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    with args.queries.open("x", encoding="utf-8") as file:
        json.dump({"queries": queries, "extension_sha256": sha}, file, indent=2)
        file.write("\n")
    print(json.dumps({"suite": args.suite, "scale": args.scale, "table": table, "rows": count,
                      "extension_sha256": sha}))


if __name__ == "__main__":
    main()
