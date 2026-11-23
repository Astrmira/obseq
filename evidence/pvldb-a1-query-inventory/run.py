"""Audit the frozen 305-query SQL catalog before producing candidate labels."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import runpy

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.annotate_types import annotate_types
from sqlglot.optimizer.qualify import qualify


EXPECTED = {"tpch": 22, "tpcds": 99, "ssb": 13, "job": 113, "clickbench": 43, "h2o": 15}
CLICKBENCH = "274ffe1c4f83baad2fc177bbb6773bbdab0db779faeb2970de8cc531292a5dc6"
H2O = {
    "groupby": "d23ede9d21ca8933f2aea169639a5ffc8cea2b05ad24b2325a02df495d6ade5f",
    "join": "ac6b9d4ebe184bc699899a26564ac70871b1c719bf1338232a86b36232c4a66f",
}
REDUCTIONS = {"SUM", "AVG", "STDDEV", "STDDEV_POP", "STDDEV_SAMP", "VARIANCE", "VAR_POP", "VAR_SAMP"}
REPRESENTATIVES = {"ANY_VALUE", "ARG_MAX", "ARG_MIN", "MAX_BY", "MIN_BY", "FIRST", "LAST"}
VARIANCE_FUNCTIONS = REDUCTIONS - {"SUM", "AVG"}
FLOATS = {"DOUBLE", "FLOAT", "REAL"}
EXACT = {"TINYINT", "SMALLINT", "INT", "BIGINT", "INT128", "UINT128", "UTINYINT",
         "USMALLINT", "UINT", "UBIGINT", "DECIMAL", "BIGDECIMAL"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def catalog(source, job, clickbench, h2o):
    bundle = {}
    for family in ("tpch", "tpcds"):
        path = source / f"sql-{family}-143.json"
        rows = json.loads(path.read_bytes())["queries"]
        bundle[family] = [(str(key), sql, "duckdb") for key, sql in rows]
    queries = runpy.run_path(str(source / "ssb-queries.py"))["Q"]
    bundle["ssb"] = [(key, sql, "duckdb") for key, sql in queries.items() if "_" not in key]
    bundle["job"] = [(p.stem, p.read_text(encoding="utf-8"), "postgres") for p in sorted(job.glob("*.sql"))
                     if re.fullmatch(r"\d+[a-z]", p.stem)]
    stock = clickbench.read_bytes()
    if digest(stock) != CLICKBENCH:
        raise ValueError("ClickBench source fingerprint changed")
    bundle["clickbench"] = [(str(i), sql, "duckdb") for i, sql in enumerate(
        (line for line in stock.decode().splitlines() if line.strip()), 1)]
    h2o_group = []
    for mode, fingerprint in H2O.items():
        raw = (h2o / "duckdb" / f"{mode}-duckdb.py").read_bytes()
        if digest(raw) != fingerprint:
            raise ValueError(f"H2O {mode} source fingerprint changed")
        native = re.findall(r'CREATE %s TABLE ans AS (SELECT [^"]+)" % table_type', raw.decode())
        if len(native) % 2 or native[::2] != native[1::2]:
            raise ValueError("H2O cold/warm bindings differ")
        h2o_group.extend((f"{mode}-{i}", sql, "duckdb") for i, sql in enumerate(native[::2], 1))
    bundle["h2o"] = h2o_group
    if {suite: len(rows) for suite, rows in bundle.items()} != EXPECTED:
        raise ValueError("incomplete or expanded source catalog")
    return bundle


def canonical(node):
    return node.sql(normalize=True)


def rank_scope(select):
    order = select.args.get("order")
    if not order:
        return "no_order_key", 0
    if not isinstance(select, exp.Select):
        return "unresolved_set_projection", len(order.expressions)
    projections = [node.unalias() for node in select.expressions]
    aliases = {node.alias.lower(): node.unalias() for node in select.expressions if node.alias}
    keys = []
    for ordered in order.expressions:
        key = ordered.this
        if isinstance(key, exp.Literal) and key.is_int and 1 <= int(key.this) <= len(projections):
            key = projections[int(key.this) - 1]
        elif isinstance(key, exp.Column) and not key.table:
            key = aliases.get(key.name.lower(), key)
        keys.append(canonical(key))
    group = select.args.get("group")
    if group and group.expressions and not any(group.args.get(tag) for tag in ("grouping_sets", "cube", "rollup")):
        if all(canonical(aliases.get(col.name.lower(), col) if isinstance(col, exp.Column) and not col.table else col)
               in keys for col in group.expressions):
            return "covers_group_keys", len(keys)
    if projections and all(canonical(node) in keys for node in projections):
        return "covers_projected_expressions", len(keys)
    return "dependency_unresolved", len(keys)


def reduce_types(tree, schema, dialect):
    if schema:
        try:
            tree = qualify(tree.copy(), dialect=dialect, schema=schema, validate_qualify_columns=False)
        except sqlglot.errors.SqlglotError:
            tree = tree.copy()
    annotated = annotate_types(tree, schema=schema or None, dialect=dialect)
    counts = Counter()
    for aggregate in annotated.find_all(exp.AggFunc):
        if aggregate.sql_name() not in REDUCTIONS:
            continue
        operand = aggregate.this
        kind = operand.type.this.name if operand is not None and operand.type is not None else "UNKNOWN"
        counts["float" if kind in FLOATS else "exact" if kind in EXACT else "unresolved"] += 1
        if dialect == "duckdb" and aggregate.sql_name() in VARIANCE_FUNCTIONS and kind in EXACT:
            counts["exact_before_native_statistical_binding"] += 1
    return dict(counts)


def analyze(suite, key, sql, dialect, schema):
    result = {"suite": suite, "query": key, "dialect": dialect, "sql_sha256": digest(sql.encode())}
    try:
        root = sqlglot.parse_one(sql, read=dialect)
    except sqlglot.errors.ParseError:
        return {**result, "status": "parse_error"}
    scope, keys = rank_scope(root)
    limit = root.args.get("limit")
    offset = root.args.get("offset")
    nested = sum(1 for node in root.find_all(exp.Query) if node is not root and node.args.get("limit"))
    windows = sum(1 for win in root.find_all(exp.Window) if isinstance(win.this, (exp.RowNumber, exp.Rank, exp.DenseRank)))
    representative = any(node.sql_name() in REPRESENTATIVES for node in root.find_all(exp.AggFunc))
    representative |= any(node.args.get("on") is not None for node in root.find_all(exp.Distinct))
    grouped_top_n = sum(1 for node in root.find_all(exp.AggFunc)
                        if node.sql_name() in ("MIN", "MAX") and node.expressions)
    reductions = reduce_types(root.copy(), schema, dialect)
    return dict(
        result, status="parsed", top_limit=bool(limit), top_offset=bool(offset),
        order_keys=keys, order_dependency=scope, nested_limits=nested, ranking_windows=windows,
        explicit_representative=representative, grouped_top_n_aggregates=grouped_top_n,
        float_inputs=reductions.get("float", 0),
        exact_inputs=reductions.get("exact", 0), unresolved_reduction_inputs=reductions.get("unresolved", 0),
        exact_before_native_statistical_binding=reductions.get("exact_before_native_statistical_binding", 0),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", type=Path)
    parser.add_argument("job", type=Path)
    parser.add_argument("clickbench", type=Path)
    parser.add_argument("h2o", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--schemas", type=Path)
    args = parser.parse_args()
    if sqlglot.__version__ != "28.0.0":
        raise ValueError("SQL parser version changed")
    schemas = json.loads(args.schemas.read_bytes()) if args.schemas else {}
    rows = []
    for suite, workload in catalog(args.sources, args.job, args.clickbench, args.h2o).items():
        for key, sql, dialect in workload:
            schema_name = f"h2o-{key.split('-')[0]}" if suite == "h2o" else suite
            rows.append(analyze(suite, key, sql, dialect, schemas.get(schema_name)))
    args.output.mkdir(parents=True, exist_ok=True)
    result_path = args.output / "INVENTORY.json"
    result_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    with (args.output / "INVENTORY.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"queries": len(rows), "parsed": sum(row["status"] == "parsed" for row in rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
