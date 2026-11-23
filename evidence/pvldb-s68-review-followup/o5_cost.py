"""Scale the archived 100M-row sparse intent check to larger overlay sizes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
from time import perf_counter_ns

import duckdb
import pyarrow as pa


def load_archived(path):
    content = path.read_bytes()
    code, marker, _ = content.partition(b"\nif len(sys.argv)>1:")
    if not marker:
        raise ValueError("Could not isolate the archived timing functions")
    namespace = {"__file__": str(path), "__name__": "archived_o5"}
    exec(compile(code, str(path), "exec"), namespace)
    return namespace, hashlib.sha256(content).hexdigest()


def roster(db, inputs, count, original):
    if count == 3:
        return original
    complete, remaining = divmod(count, 3)
    layout = [0, 1, 2, 3] * complete + [1, 2][:remaining]
    raw = db.execute("""SELECT ordinal,v1 FROM read_parquet(?) WHERE v1 IS NOT NULL
                        ORDER BY ordinal LIMIT ?""", [str(inputs / "id1=id001/*.parquet"), len(layout)]).fetchall()
    if len(raw) != len(layout):
        raise ValueError("The pinned first partition does not contain enough non-null keys")
    return [("id001", ordinal, min(kind, 2), value + (kind == 3) if kind >= 2 else None)
            for (ordinal, value), kind in zip(raw, layout, strict=True)]


def run(path, archived, overlays, repeat):
    available = os.sched_getaffinity(0)
    cpu = max(available)
    os.sched_setaffinity(0, {cpu})
    implementation, digest = load_archived(archived)
    implementation["path"] = path
    db, original = implementation["setup"]()
    try:
        expected = roster(db, path, overlays, original)
        if overlays != 3:
            columns = {name: [row[i] for row in expected] for i, name in enumerate(("id1", "rid", "op", "val"))}
            db.register("prepared_operations", pa.table(columns))
            db.execute("DELETE FROM stage")
            db.execute("INSERT INTO stage SELECT id1,rid,op,val FROM prepared_operations")
            db.unregister("prepared_operations")
        if sum(op != 0 for _, _, op, _ in expected) != overlays:
            raise ValueError("The staged operation mix does not match its overlay scale")
        files = sorted(path.glob("id1=*/*.parquet"))
        if len(files) != 100:
            raise ValueError("The original 100 Hive partitions are required")
        t0 = perf_counter_ns()
        records = implementation["apply"](db, expected)
        t1 = perf_counter_ns()
        witness = implementation["witness"](db, expected)
        t2 = perf_counter_ns()
        verification = implementation["verify"](db, expected, files)
        t3 = perf_counter_ns()
        if records != (overlays, len(expected)) or not witness or verification != [100_000_000, 0, overlays, 0, True]:
            raise ValueError(f"Unexpected replay counts: {records}, {verification}")
        return {"repeat": repeat, "overlay_rows": overlays, "receipt_rows": len(expected), "backing_rows": verification[0],
                "apply_wall_ns": t1-t0, "witness_wall_ns": t2-t1, "verify_wall_ns": t3-t2,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, "pinned_cpu": cpu,
                "duckdb": duckdb.__version__, "archived_driver_sha256": digest}
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("archived", type=Path)
    parser.add_argument("overlays", type=int, choices=(3, 1000, 100000))
    parser.add_argument("repeat", type=int)
    args = parser.parse_args()
    if duckdb.__version__ != "1.4.3":
        parser.error("Expected archived DuckDB 1.4.3")
    print(json.dumps(run(args.inputs.resolve(), args.archived, args.overlays, args.repeat), sort_keys=True))
