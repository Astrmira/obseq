"""Compile ordered SQL windows and validate typed projected candidates."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy

import duckdb
import pyarrow as pa
import sqlglot

from cutoffs import compile_window


def projected_equal(names, types, candidate, source):
    terms = []
    for name, dtype in zip(names, types, strict=True):
        left, right = f"{candidate}.{name}", f"{source}.{name}"
        if pa.types.is_string(dtype) or pa.types.is_large_string(dtype):
            left = f"(CAST({left} AS VARCHAR) COLLATE POSIX)"
            right = f"(CAST({right} AS VARCHAR) COLLATE POSIX)"
        terms.append(f"{left} IS NOT DISTINCT FROM {right}")
    return " AND ".join(terms)


def nested_strings(dtype):
    if pa.types.is_nested(dtype):
        return any(pa.types.is_string(dtype.field(i).type) or pa.types.is_large_string(dtype.field(i).type)
                   or nested_strings(dtype.field(i).type) for i in range(dtype.num_fields))
    return False


def check(db, window, candidates):
    """Evaluate peer interval occupancy and the multiplicity of requested projected rows."""
    keys = ", ".join(window.keys)
    values = ", ".join(window.values)
    wanted_keys = ", ".join(f"bands.{name}" for name in window.keys)
    names = (*window.keys, *window.values)
    types = next(iter(candidates.values())).schema.types
    if any(nested_strings(dtype) for dtype in types):
        raise ValueError("nested text projections lack a certified collation-independent identity")
    key_equal = " AND ".join(
        f"desired.{key} IS NOT DISTINCT FROM eligible.{key}" for key in window.keys)
    equal = key_equal + " AND " + projected_equal(window.values, types, "desired", "eligible")
    lower, upper = window.offset, window.offset + window.size
    tables = []
    for label, table in candidates.items():
        if table.num_columns != len(window.values):
            raise ValueError("typed candidate projection width differs from compiled window")
        tables.append(pa.Table.from_arrays(
            [pa.array([label] * table.num_rows, type=pa.string()),
             pa.array(range(table.num_rows), type=pa.int64()), *table.columns],
            names=["__pvl_arm", "__pvl_position", *window.values],
        ))
    db.register("__pvl_input", pa.concat_tables(tables))
    try:
        expected, invalid = db.execute(f"""
            WITH eligible AS MATERIALIZED ({window.relation}),
            peers AS (SELECT {keys}, count(*) AS n FROM eligible GROUP BY {keys}),
            ranked AS (
                SELECT {keys}, n, sum(n) OVER (
                    ORDER BY {window.order} ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS rank_end FROM peers
            ),
            bands AS (
                SELECT {keys}, greatest(rank_end - n, {lower}) - {lower} AS lo,
                       least(rank_end, {upper}) - {lower} AS hi
                FROM ranked WHERE rank_end > {lower} AND rank_end - n < {upper}
            ),
            desired AS (
                SELECT __pvl_arm, {wanted_keys}, {values}, count(*) AS wanted
                FROM __pvl_input JOIN bands
                    ON __pvl_position >= lo AND __pvl_position < hi
                GROUP BY ALL
            ),
            counted AS (
                SELECT desired.__pvl_arm, {", ".join(f"desired.{n}" for n in names)},
                       desired.wanted, count(eligible.present) AS available
                FROM desired LEFT JOIN (SELECT *, TRUE AS present FROM eligible) eligible
                    ON {equal} GROUP BY ALL
            )
            SELECT (SELECT coalesce(sum(hi-lo), 0) FROM bands),
                   (SELECT list(DISTINCT __pvl_arm) FROM counted WHERE available < wanted)
        """).fetchone()
    finally:
        db.unregister("__pvl_input")
    invalid = set(invalid or ())
    return {label: {
        "accepted": table.num_rows == expected and label not in invalid,
        "required_rows": expected,
        "observed_rows": table.num_rows,
        "ineligible_or_excess_peer_member": label in invalid,
    } for label, table in candidates.items()}


def call(db, query, candidates):
    """Public entry for one original SQL statement and already decoded Arrow arms."""
    canonical = db.execute(f"SELECT * FROM ({query.strip().rstrip(';')}) LIMIT 0").fetch_arrow_table()
    window = compile_window(query, canonical.column_names)
    if window is None:
        raise ValueError("query has no top-level ordered window")
    if any(arm.schema.types != canonical.schema.types for arm in candidates.values()):
        raise ValueError("typed candidate schema differs from native projection")
    return check(db, window, candidates)


def same_cardinality_controls(db, window, table):
    """Construct independently certified negative controls for a legal native arm."""
    if not table.num_rows:
        return {}, {"membership": "empty_window", "multiplicity": "empty_window", "order": "empty_window"}
    types = table.schema.types
    rows = list(zip(*(column.to_pylist() for column in table.columns)))
    first, last = rows[0], rows[-1]
    absent = list(first)
    for col, dtype in enumerate(types):
        if pa.types.is_string(dtype) or pa.types.is_large_string(dtype):
            absent[col] = "\uFDD0obseq-absent"
            break
        if pa.types.is_integer(dtype):
            absent[col] = (1 << (dtype.bit_width - (0 if pa.types.is_unsigned_integer(dtype) else 1))) - 1
            break
    else:
        absent[0] = None

    def as_table(values, names):
        return pa.Table.from_arrays(
            [pa.array(column, type=dtype) for column, dtype in zip(zip(*values), types, strict=True)],
            names=names,
        )

    probes = as_table([first, last, absent], window.values).add_column(
        0, "probe", pa.array(["first", "last", "absent"]))
    compare = projected_equal(window.values, types, "p", "e")
    db.register("__pvl_control_probes", probes)
    try:
        stats = db.execute(f"""
            WITH eligible AS MATERIALIZED ({window.relation}),
            matching AS (
                SELECT p.probe, dense_rank() OVER (ORDER BY {window.order}) AS rank
                FROM eligible e JOIN __pvl_control_probes p ON {compare}
            )
            SELECT probe, count(*), min(rank), max(rank) FROM matching GROUP BY probe
        """).fetchall()
    finally:
        db.unregister("__pvl_control_probes")
    hits = {name: (count, lower, upper) for name, count, lower, upper in stats}
    controls = {}
    reasons = {}
    if "absent" not in hits:
        controls["same_count_absent_member"] = as_table([absent, *rows[1:]], table.column_names)
    else:
        reasons["membership"] = "sentinel_present"
    if first != last and hits["first"][0] == rows.count(first):
        controls["same_count_excess_multiplicity"] = as_table([*rows[:-1], first], table.column_names)
    else:
        reasons["multiplicity"] = "excess_multiplicity_not_certified"
    if first != last and hits["first"][2] < hits["last"][1]:
        controls["same_count_wrong_order"] = as_table([last, *rows[1:-1], first], table.column_names)
    else:
        reasons["order"] = "strict_end_order_not_certified"
    return controls, reasons


def jsonl(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def capture(root, query, threads, manifest, digest, source):
    row = manifest[(query, threads)]
    data = (root / row["candidate"]).read_bytes()
    if row["sql_sha256"] != digest or row["acquisition_sha256"] != source or hashlib.sha256(data).hexdigest() != row["candidate_sha256"]:
        raise ValueError("frozen capture identity mismatch")
    return pa.ipc.open_file(data).read_all()


def control(table):
    if table.num_rows:
        return table.slice(1)
    return pa.Table.from_arrays([pa.nulls(1, type=f.type) for f in table.schema], schema=table.schema)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("suite", choices=("tpch", "tpcds", "clickbench"))
    p.add_argument("queries", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--database", type=Path)
    p.add_argument("--native", type=Path)
    p.add_argument("--acquisition", type=Path)
    p.add_argument("--upstream", type=Path)
    p.add_argument("--stores", nargs=2, type=Path)
    p.add_argument("--only", nargs="+", type=int)
    p.add_argument("--same-cardinality", action="store_true", help="score certified equal-length negatives")
    a = p.parse_args()
    if (duckdb.__version__, pa.__version__, sqlglot.__version__) != ("1.4.3", "22.0.0", "28.0.0"):
        raise ValueError("runtime version changed")
    dbpath = str(a.database) if a.database else ":memory:"
    temp = str(a.output.parent/"spills-a1")
    config = {"threads": "1" if a.database else "8", "memory_limit": "34GB", "temp_directory": temp}
    with duckdb.connect(dbpath, read_only=bool(a.database), config=config) as db:
        if a.suite == "clickbench":
            native = runpy.run_path(str(a.upstream))
            source = a.queries.read_bytes()
            if hashlib.sha256(source).hexdigest() != native["STOCK_SHA"]:
                raise ValueError("stock SQL identity mismatch")
            shards = native["load_shards"](a.acquisition, a.stores)
            paths = ", ".join(map(native["sql_string"], shards))
            db.execute(f"""CREATE VIEW hits AS SELECT * REPLACE (
                   DATE '1970-01-01' + CAST(EventDate AS INTEGER) AS EventDate,
                   make_timestamp(EventTime * 1000000) AS EventTime
                ) FROM read_parquet([{paths}], binary_as_string=true)""")
            manifest = {(r["query"], r["threads"]): r for r in jsonl(a.native/"manifest.jsonl")}
            acquisition = hashlib.sha256(a.acquisition.read_bytes()).hexdigest()
            queries = list(enumerate(source.decode().splitlines(), 1))
        else:
            fixture = json.loads(a.queries.read_bytes())
            queries = [(int(number), sql) for number, sql in fixture["queries"]]
        with a.output.open("x", encoding="utf-8") as out:
            for number, sql in queries:
                if a.only and number not in a.only:
                    continue
                digest = hashlib.sha256(sql.encode()).hexdigest()
                memo = {"suite": a.suite, "query": number, "sql_sha256": digest}
                try:
                    root = sqlglot.parse_one(sql, read="duckdb")
                    if not (root.args.get("order") and root.args.get("limit")):
                        continue
                    if a.suite == "clickbench":
                        inputs = {f"native_{t}": capture(a.native, number, t, manifest, digest, acquisition) for t in (1, 8)}
                    else:
                        inputs = {"native_1": db.execute(sql).fetch_arrow_table()}
                    inputs["shape_negative_control"] = control(inputs["native_1"])
                    if a.same_cardinality:
                        window = compile_window(sql, inputs["native_1"].column_names)
                        extras, skipped = same_cardinality_controls(db, window, inputs["native_1"])
                        inputs.update(extras)
                        memo["same_cardinality_unavailable"] = skipped
                    memo["observations"] = call(db, sql, inputs)
                except (duckdb.Error, ValueError, pa.ArrowException) as exc:
                    memo["error"] = type(exc).__name__
                    memo["diagnostic"] = str(exc).splitlines()[0][:200]
                print(json.dumps(memo, sort_keys=True), file=out, flush=True)
                print(f"{a.suite} Q{number} {'error' if 'error' in memo else 'scored'}", flush=True)


if __name__ == "__main__":
    main()
