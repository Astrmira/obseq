"""Native peer-count census for literal top-level ORDER BY/LIMIT windows."""

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import runpy

import duckdb
import sqlglot
from sqlglot import exp


def integer(construct, default):
    if construct is None:
        return default
    expression = construct.args["expression"]
    if not isinstance(expression, exp.Literal) or not expression.is_int:
        raise ValueError("nonliteral limit or offset")
    return int(expression.this)


@dataclass(frozen=True)
class Window:
    relation: str
    values: tuple
    keys: tuple
    order: str
    offset: int
    size: int


def compile_window(query, projected_names=None):
    root = sqlglot.parse_one(query, read="duckdb")
    order, limit = root.args.get("order"), root.args.get("limit")
    if not order or not limit:
        return None
    if not isinstance(root, exp.Select):
        raise ValueError("census only rewrites SELECT queries")
    if root.args.get("limit").args.get("limit_options"):
        raise ValueError("nonstandard limit options")
    k, offset = integer(limit, None), integer(root.args.get("offset"), 0)
    if k <= 0 or offset < 0:
        raise ValueError("census requires a positive window and nonnegative offset")
    projections = list(root.expressions)
    if any(item.unalias().is_star for item in projections):
        if (len(projections) != 1 or not isinstance(projections[0], exp.Star) or any(projections[0].args.values())
                or not projected_names or len(set(projected_names)) != len(projected_names)):
            raise ValueError("wildcard projection needs unambiguous native output names")
        projections = [exp.column(name, quoted=True) for name in projected_names]
        root.set("expressions", projections)
    aliases = {item.alias.lower(): item.unalias() for item in projections if item.alias}
    distinct = root.args.get("distinct")
    if distinct and distinct.args.get("on"):
        raise ValueError("DISTINCT ON or wildcard projection needs a separate peer rule")
    value_columns = tuple(f"__pvl_projection_{position}" for position in range(1, len(projections) + 1))
    projected_keys = []
    rank_columns, ranked = [], []
    for index, ordered in enumerate(order.expressions, 1):
        key = ordered.this
        if isinstance(key, exp.Literal) and key.is_int:
            ordinal = int(key.this)
            if ordinal < 1 or ordinal > len(root.expressions):
                raise ValueError("invalid projection ordinal")
            key = root.expressions[ordinal - 1].unalias()
        elif isinstance(key, exp.Column) and not key.table:
            key = aliases.get(key.name.lower(), key)
        if isinstance(key, exp.Collate):
            raise ValueError("explicit collation needs a separate peer rule")
        name = f"__pvl_rank_key_{index}"
        rank_columns.append(name)
        item = ordered.copy()
        item.set("this", exp.column(name))
        ranked.append(item.sql(dialect="duckdb"))
        if distinct:
            matches = [position for position, item in enumerate(projections, 1)
                       if item.unalias().unnest() == key.unnest()]
            if len(matches) != 1:
                raise ValueError("DISTINCT rank key does not match one projected expression")
            projected_keys.append(f"{value_columns[matches[0]-1]} AS {name}")
        else:
            root.append("expressions", exp.alias_(key.copy(), name))
    for clause in ("order", "limit", "offset"):
        root.set(clause, None)
    relation = root.sql(dialect="duckdb")
    if distinct:
        columns = ", ".join(value_columns)
        relation = f"SELECT {columns}, {', '.join(projected_keys)} FROM ({relation}) AS projected({columns})"
    else:
        columns = ", ".join((*value_columns, *rank_columns))
        relation = f"SELECT * FROM ({relation}) AS projected({columns})"
    return Window(relation, value_columns, tuple(rank_columns), ", ".join(ranked), offset, k)


def compile_census(query, projected_names=None):
    window = compile_window(query, projected_names)
    if window is None:
        return None
    names = ", ".join(window.keys)
    lower, upper = window.offset + 1, window.offset + window.size
    return f"""
        WITH candidate AS ({window.relation}),
             peers AS (SELECT {names}, count(*) AS n FROM candidate GROUP BY {names}),
             ranked AS (
               SELECT n, sum(n) OVER (
                 ORDER BY {window.order} ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) AS end_rank FROM peers
             )
        SELECT coalesce(max(end_rank), 0) AS candidate_rows,
               max(n) FILTER (WHERE end_rank - n < {lower} AND end_rank >= {lower}) AS lower_peers,
               max(n) FILTER (WHERE end_rank - n < {upper} AND end_rank >= {upper}) AS upper_peers,
               coalesce(bool_or(end_rank - n < {window.offset} AND end_rank >= {lower}), false) AS lower_boundary_split,
               coalesce(bool_or(end_rank - n < {upper} AND end_rank > {upper}), false) AS upper_boundary_split
        FROM ranked
    """


def census(db, queries, stream):
    for index, query in queries:
        source_sha = hashlib.sha256(query.encode()).hexdigest()
        record = {"query": index, "sql_sha256": source_sha}
        try:
            root = sqlglot.parse_one(query, read="duckdb")
            if not (root.args.get("order") and root.args.get("limit")):
                continue
            names = [column[0] for column in db.execute(
                f"SELECT * FROM ({query.strip().rstrip(';')}) LIMIT 0"
            ).description]
            sql = compile_census(query, names)
        except duckdb.Error as exc:
            record.update(status="native_error", reason=type(exc).__name__)
        except ValueError as exc:
            record.update(status="unresolved", reason=str(exc))
        else:
            if sql is None:
                continue
            try:
                executed = db.execute(sql)
                row = dict(zip((item[0] for item in executed.description), executed.fetchone()))
            except duckdb.Error as exc:
                record.update(status="native_error", reason=type(exc).__name__)
            else:
                record.update(status="verified", **row)
        print(json.dumps(record, sort_keys=True), file=stream, flush=True)
        print(f"cutoff query={index} status={record['status']}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=("tpch", "tpcds", "clickbench"))
    parser.add_argument("queries", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--extension", type=Path)
    parser.add_argument("--scale", type=int, choices=(1, 10), default=1)
    parser.add_argument("--acquisition", type=Path)
    parser.add_argument("--stores", nargs=2, type=Path)
    parser.add_argument("--upstream", type=Path)
    args = parser.parse_args()
    if (duckdb.__version__, sqlglot.__version__) != ("1.4.3", "28.0.0"):
        raise ValueError("native or compiler version mismatch")
    with duckdb.connect(config={"threads": "8", "memory_limit": "40GB", "temp_directory": str(args.output.parent / "spill")}) as db:
        if args.suite in ("tpch", "tpcds"):
            fixture = json.loads(args.queries.read_bytes())
            if hashlib.sha256(args.extension.read_bytes()).hexdigest() != fixture["extension_sha256"]:
                raise ValueError("TPC-H generator identity mismatch")
            db.execute("LOAD '" + str(args.extension.resolve()).replace("'", "''") + "'")
            generator, table, sf1_rows = {
                "tpch": ("dbgen", "lineitem", 6_001_215),
                "tpcds": ("dsdgen", "store_sales", 2_880_404),
            }[args.suite]
            db.execute(f"CALL {generator}(sf={args.scale})")
            rows, = db.execute(f"SELECT count(*) FROM {table}").fetchone()
            if args.scale == 1 and rows != sf1_rows:
                raise ValueError(f"{args.suite} SF1 row count mismatch")
            print(json.dumps({"suite": args.suite, "scale": args.scale, "witness_table": table,
                              "witness_rows": rows, "extension_sha256": fixture["extension_sha256"]},
                             sort_keys=True), flush=True)
            queries = fixture["queries"]
        else:
            native = runpy.run_path(str(args.upstream))
            source = args.queries.read_bytes()
            if hashlib.sha256(source).hexdigest() != native["STOCK_SHA"]:
                raise ValueError("stock SQL identity mismatch")
            shards = native["load_shards"](args.acquisition, args.stores)
            paths = ", ".join(map(native["sql_string"], shards))
            db.execute(f"""
                CREATE VIEW hits AS
                SELECT * REPLACE (DATE '1970-01-01' + CAST(EventDate AS INTEGER) AS EventDate,
                   make_timestamp(EventTime * 1000000) AS EventTime)
                FROM read_parquet([{paths}],binary_as_string=true)
            """)
            if db.execute("SELECT count(*) FROM hits").fetchone() != (native["POPULATION"],):
                raise ValueError("ClickBench input row count mismatch")
            queries = list(enumerate(source.decode().splitlines(), 1))
        with args.output.open("x") as stream:
            census(db, queries, stream)


if __name__ == "__main__":
    main()
