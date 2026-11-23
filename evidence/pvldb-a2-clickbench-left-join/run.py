"""Measure whole-result and per-left-row observations of a native UserID join."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
from time import perf_counter

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


KEYS = ("shard", "source_row")
FIELDS = (*KEYS, "userid", "matched_pairs")
SAMPLE_STRIDE = 16_384
RIGHT = {"exact": "userid::HUGEINT", "right_float64": "(userid::DOUBLE)::HUGEINT"}


def read_json(path):
    return json.loads(path.read_bytes())


def elapsed(action):
    before = perf_counter()
    value = action()
    return value, perf_counter() - before


def native_arms(db, out, string):
    results = {}
    for arm, expression in RIGHT.items():
        def direct():
            return db.execute(f"""
                SELECT count(*), count(r.k), count(*) FILTER (WHERE r.k IS NULL)
                FROM left_input l LEFT JOIN (
                    SELECT {expression} AS k FROM source WHERE source_row % 2 = 1
                ) r ON l.userid::HUGEINT = r.k
            """).fetchone()

        (total, matched, unmatched), join_seconds = elapsed(direct)
        if total != matched + unmatched:
            raise ValueError("raw native left-join counts do not partition the result")
        db.execute(f"""CREATE OR REPLACE TEMP TABLE right_counts AS
                       SELECT {expression} AS k, count(*) AS n
                       FROM source WHERE source_row % 2 = 1 GROUP BY k""")
        path = out / f"{arm}.parquet"
        db.execute(f"""
            COPY (
                SELECT l.shard, l.source_row, l.userid, coalesce(r.n, 0) AS matched_pairs
                FROM left_input l LEFT JOIN right_counts r ON l.userid::HUGEINT = r.k
            ) TO {string(path)} (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        db.execute(f"CREATE VIEW {arm} AS SELECT * FROM read_parquet({string(path)})")
        rows, pairs, zero = db.execute(f"""
            SELECT count(*), sum(matched_pairs), count(*) FILTER (WHERE matched_pairs = 0) FROM {arm}
        """).fetchone()
        if (pairs, zero, pairs + zero) != (matched, unmatched, total):
            raise ValueError("group-count left-join representation differs from the physical native join")
        with path.open("rb") as stream:
            artifact_sha = hashlib.file_digest(stream, "sha256").hexdigest()
        results[arm] = {"raw_rows": total, "native_matched_pairs": matched, "raw_unmatched_rows": unmatched,
                        "native_join_wall_seconds": join_seconds, "rollup_rows": rows,
                        "rollup_bytes": path.stat().st_size, "rollup_sha256": artifact_sha}
        print(f"[{arm}] finished physical left join and row-level product", flush=True)
    return results


def native_relations(db, count):
    sums = [db.execute(f"SELECT {', '.join('sum('+col+')' for col in FIELDS)} FROM {arm}").fetchone() for arm in RIGHT]
    rows, mismatch, rtol5, rtol9 = db.execute("""
        SELECT count(*), count(*) FILTER (
                   WHERE e.userid IS DISTINCT FROM c.userid OR e.matched_pairs IS DISTINCT FROM c.matched_pairs),
               bool_and(e.userid = c.userid AND abs(e.matched_pairs - c.matched_pairs) <=
                        1e-5 * greatest(abs(e.matched_pairs), abs(c.matched_pairs))),
               bool_and(e.userid = c.userid AND abs(e.matched_pairs - c.matched_pairs) <=
                        1e-9 * greatest(abs(e.matched_pairs), abs(c.matched_pairs)))
        FROM exact e JOIN right_float64 c USING (shard, source_row)
    """).fetchone()
    if rows != count:
        raise ValueError("left row identities are missing or nonunique")
    fields = [db.execute(f"DESCRIBE {name}").fetchall() for name in RIGHT]
    return {"rowcount": True, "schema": fields[0] == fields[1], "sum": sums[0] == sums[1],
            "ordered_by_left_identity": mismatch == 0, "rtol1e-5": rtol5, "rtol1e-9": rtol9}, mismatch


def native_tools(db, out, observe):
    full = [pq.read_table(out / f"{arm}.parquet").to_pandas() for arm in RIGHT]
    # Sort by the declared physical left identity, not by values that may be corrupted.
    full = [df.sort_values(list(KEYS), kind="stable", ignore_index=True) for df in full]
    decisions = {}
    for label, options in (("pandas_default", {}), ("pandas_dtype_relaxed", {"check_dtype": False}),
                           ("pandas_check_like", {"check_like": True})):
        try:
            pd.testing.assert_frame_equal(*full, **options)
        except AssertionError:
            decisions[label] = False
        else:
            decisions[label] = True
    del full
    sample = [db.execute(f"""SELECT * FROM {arm}
                             WHERE source_row % {SAMPLE_STRIDE} = 0 ORDER BY shard, source_row""").fetchall()
              for arm in RIGHT]
    return decisions, {"rows_per_arm": len(sample[0]), "stride": SAMPLE_STRIDE,
                       "e2_observers": observe(*(list(map(list, table)) for table in sample), None, None, None)}


def main():
    parser = argparse.ArgumentParser()
    for name in ("acquisition", "prior_id_cast", "upstream", "observer", "e2", "out"):
        parser.add_argument(name, type=Path)
    parser.add_argument("stores", nargs=2, type=Path)
    args = parser.parse_args()
    if (duckdb.__version__, pa.__version__, pd.__version__) != ("1.4.3", "22.0.0", "2.2.3"):
        raise ValueError("unexpected experimental runtime")
    upstream = runpy.run_path(str(args.upstream))
    shards = upstream["load_shards"](args.acquisition, args.stores)
    prior = read_json(args.prior_id_cast)["columns"]["UserID"]["exact_reference_and_native"]
    observe = runpy.run_path(str(args.observer))["observer"](args.e2)
    string = upstream["sql_string"]
    args.out.mkdir(mode=0o700, exist_ok=True)
    out = args.out / "private-rollup"
    out.mkdir(mode=0o700)
    with duckdb.connect(config={"threads": "8", "memory_limit": "32GB",
                                "temp_directory": str(args.out / "spill")}) as db:
        paths = ", ".join(map(string, shards))
        db.execute(f"""
            CREATE TEMP TABLE source AS
            SELECT regexp_extract(filename, 'hits_([0-9]+)[.]parquet$', 1)::USMALLINT AS shard,
                   file_row_number AS source_row, UserID AS userid
            FROM read_parquet([{paths}], filename=true, file_row_number=true)
        """)
        population, admitted = db.execute("SELECT count(*), count(userid) FROM source").fetchone()
        if not population == admitted == upstream["POPULATION"]:
            raise ValueError("source population differs from frozen nonnull IDs")
        db.execute("CREATE TEMP VIEW left_input AS SELECT * FROM source WHERE source_row % 2 = 0")
        left_count, = db.execute("SELECT count(*) FROM left_input").fetchone()
        results = native_arms(db, out, string)
        exact_pairs = results["exact"]["native_matched_pairs"]
        lost = exact_pairs - results["right_float64"]["native_matched_pairs"]
        if (exact_pairs, lost) != (prior["source_exact_nonnull_pairs"], prior["unilateral_lost_pairs"]):
            raise ValueError("physical left join diverges from the independent exact frequency reference")
        if any(detail["rollup_rows"] != left_count for detail in results.values()):
            raise ValueError("business output does not retain every left occurrence")
        ordinary, differing_rows = native_relations(db, left_count)
        tools, sample = native_tools(db, out, observe)
    result = {
        "source_rows": population, "left_rows": left_count, "right_rows": population - left_count,
        "acquisition_sha256": hashlib.sha256(args.acquisition.read_bytes()).hexdigest(),
        "e2_sha256": hashlib.sha256(args.e2.read_bytes()).hexdigest(), "runtime": {
            "duckdb": duckdb.__version__, "pyarrow": pa.__version__, "pandas": pd.__version__,
        },
        "native_arms": results, "lost_exact_pairs": lost,
        "raw_shape_observers": {
            "rowcount": len({arm["raw_rows"] for arm in results.values()}) == 1,
            "schema": True,
        },
        "per_left_row_product": {"columns": FIELDS, "differing_rows": differing_rows,
                                 "whole_output_ordinary_observers": ordinary, "whole_output_tool_observers": tools,
                                 "fixed_stride_sample": sample},
    }
    (args.out / "RESULT.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
