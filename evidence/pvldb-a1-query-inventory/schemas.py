"""Bind the analyzed SQL catalog to the declared or native input-column types."""

import argparse
import hashlib
import json
from pathlib import Path

import duckdb
import sqlglot
from sqlglot import exp


def sql_string(arg):
    return "'" + str(arg).replace("'", "''") + "'"


def tpc_schema(family, extension, query_bundle):
    pinned = json.loads(query_bundle.read_bytes())["extension_sha256"]
    if hashlib.sha256(extension.read_bytes()).hexdigest() != pinned:
        raise ValueError(f"{family} extension mismatch")
    with duckdb.connect() as db:
        db.execute("LOAD " + sql_string(extension.resolve()))
        generator = "dbgen" if family == "tpch" else "dsdgen"
        db.execute(f"CALL {generator}(sf=0)")
        tables = db.execute("SHOW TABLES").fetchall()
        expected = 8 if family == "tpch" else 24
        if len(tables) != expected:
            raise ValueError(f"{family} schema-only generator table count mismatch")
        return {table: {r[0]: r[1] for r in db.execute(f'DESCRIBE "{table}"').fetchall()} for table, in tables}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", type=Path)
    parser.add_argument("job_schema", type=Path)
    parser.add_argument("clickbench_footer_file", type=Path)
    parser.add_argument("tpch_extension", type=Path)
    parser.add_argument("tpcds_extension", type=Path)
    args = parser.parse_args()
    if duckdb.__version__ != "1.4.3":
        raise ValueError("expected pinned native binding")
    schemas = {}
    for suite, extension in (("tpch", args.tpch_extension), ("tpcds", args.tpcds_extension)):
        schemas[suite] = tpc_schema(suite, extension, args.sources / f"sql-{suite}-143.json")
    schemas["job"] = {
        node.this.this.name: {column.name: column.args["kind"].sql() for column in node.this.expressions
                              if isinstance(column, exp.ColumnDef)}
        for node in sqlglot.parse(args.job_schema.read_text(), read="postgres")
        if isinstance(node, exp.Create) and isinstance(node.this, exp.Schema)
    }
    # DESCRIBE binds columns through the already authenticated footer without decoding sparse payloads.
    with duckdb.connect() as db:
        query = f"DESCRIBE SELECT * FROM read_parquet({sql_string(args.clickbench_footer_file)},binary_as_string=true)"
        clickbench = {r[0]: r[1] for r in db.execute(query).fetchall()}
    clickbench.update(EventTime="TIMESTAMP", EventDate="DATE")
    schemas["clickbench"] = {"hits": clickbench}
    schemas["ssb"] = {
        "d": {**dict.fromkeys(("day", "yr", "ym", "wk"), "BIGINT"), "ym_name": "VARCHAR"},
        "fact": dict.fromkeys(("ck", "pk", "sk", "day", "qty", "xp", "discount", "rev", "cost"), "BIGINT"),
        "p": {"pk": "BIGINT", **dict.fromkeys(("mfgr", "category", "brand"), "VARCHAR")},
        "s": {"sk": "BIGINT", **dict.fromkeys(("s_city", "s_nation", "s_region"), "VARCHAR")},
        "c": {"ck": "BIGINT", **dict.fromkeys(("c_city", "c_nation", "c_region"), "VARCHAR")},
    }
    schemas["h2o-groupby"] = {"x": {
        **dict.fromkeys(("id1", "id2", "id3"), "VARCHAR"),
        **dict.fromkeys(("id4", "id5", "id6", "v1", "v2"), "INTEGER"), "v3": "FLOAT",
    }}
    schemas["h2o-join"] = {}
    for table, keys in (
        ("x", ("id1", "id2", "id3", "id4", "id5", "id6")),
        ("small", ("id1", "id4")), ("medium", ("id1", "id2", "id4", "id5")),
        ("big", ("id1", "id2", "id3", "id4", "id5", "id6")),
    ):
        schemas["h2o-join"][table] = {
            **{k: "INT64" if k in ("id1", "id2", "id3") else "VARCHAR" for k in keys},
            ("v1" if table == "x" else "v2"): "DOUBLE",
        }
    print(json.dumps(schemas, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
