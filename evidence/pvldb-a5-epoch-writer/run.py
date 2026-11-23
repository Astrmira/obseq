"""Measure atomic epoch maintenance for E6's scoped TPC-H price-overlay writer."""

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
from statistics import median
from time import perf_counter_ns

import duckdb


UPSERT = """
    INSERT INTO edits
    SELECT 1, l.rowid, coalesce(e.amount, l.l_extendedprice) + ?
    FROM lineitem l LEFT JOIN edits e ON e.rid = l.rowid AND e.lineage = 1
    WHERE l.rowid = ?
    ON CONFLICT(lineage, rid) DO UPDATE SET amount = excluded.amount
"""
REGION = """
    FROM lineitem l
    JOIN supplier s ON l.l_suppkey = s.s_suppkey
    JOIN nation n ON s.s_nationkey = n.n_nationkey
"""
ADVANCE = f"""
    UPDATE epoch SET tok = tok + 1
    WHERE ? != 0 AND EXISTS(SELECT 1 {REGION} WHERE l.rowid = ? AND n.n_regionkey = 0)
"""
DELTA = Decimal("0.01")


def write(db, rid, delta, tracked, rollback=False):
    db.execute("BEGIN")
    try:
        db.execute(UPSERT, [delta, rid])
        if tracked:
            db.execute(ADVANCE, [delta, rid])
    except Exception:
        db.execute("ROLLBACK")
        raise
    db.execute("ROLLBACK" if rollback else "COMMIT")


def measure(db, workload, tracked, *, durable=False):
    table = "TABLE" if durable else "TEMP TABLE"
    db.execute("DROP TABLE IF EXISTS edits; DROP TABLE IF EXISTS epoch")
    db.execute(f"""CREATE {table} edits(lineage INT, rid BIGINT, amount DECIMAL(15,2),
                                       PRIMARY KEY(lineage,rid))""")
    if tracked:
        db.execute(f"CREATE {table} epoch(id INT PRIMARY KEY, tok BIGINT); INSERT INTO epoch VALUES(0,0)")
    rid = next(rid for kind, rid in workload if kind == "scoped_change")
    write(db, rid, DELTA, tracked, rollback=True)
    if db.execute("SELECT count(*) FROM edits").fetchone() != (0,):
        raise ValueError("overlay survived rollback")
    if tracked and db.execute("SELECT tok FROM epoch").fetchone() != (0,):
        raise ValueError("epoch survived rollback")
    if durable:
        db.execute("CHECKPOINT")
    ticks = {kind: [] for kind in ("scoped_change", "outside_change", "scoped_zero")}
    for kind, rid in workload:
        before = perf_counter_ns()
        write(db, rid, Decimal(0) if kind == "scoped_zero" else DELTA, tracked)
        ticks[kind].append(perf_counter_ns() - before)
    if tracked and db.execute("SELECT tok FROM epoch").fetchone() != (32,):
        raise ValueError("wrong epoch change count")
    rows = db.execute("""
        SELECT e.rid, e.amount - l.l_extendedprice
        FROM edits e JOIN lineitem l ON e.rid=l.rowid ORDER BY e.rid
    """).fetchall()
    reference = sorted((rid, Decimal(0) if kind == "scoped_zero" else DELTA) for kind, rid in workload)
    if rows != reference:
        raise ValueError("native overlay differs from exact update intent")
    return ticks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("queries", type=Path)
    parser.add_argument("extension", type=Path)
    parser.add_argument("--durable-db", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.queries.read_bytes())
    extension = args.extension.resolve()
    if duckdb.__version__ != "1.4.3" or hashlib.sha256(extension.read_bytes()).hexdigest() != manifest["extension_sha256"]:
        raise ValueError("pinned engine or signed TPC-H extension mismatch")
    randomizer = random.Random(20261122)
    trials = []
    database = str(args.durable_db.resolve()) if args.durable_db else ":memory:"
    wal = Path(database + ".wal")
    if args.durable_db and (Path(database).exists() or wal.exists()):
        raise ValueError("durability replay needs a new database path")
    with duckdb.connect(database, config={"threads": "1", "memory_limit": "2GB"}) as db:
        db.execute("LOAD '" + str(extension).replace("'", "''") + "'")
        db.execute("CALL dbgen(sf=1)")
        population, = db.execute("SELECT count(*) FROM lineitem").fetchone()
        if population != 6_001_215:
            raise ValueError("native SF1 population mismatch")
        scoped = db.execute(f"SELECT l.rowid {REGION} WHERE n.n_regionkey=0 ORDER BY l.rowid LIMIT 64").fetchall()
        outside = db.execute(f"SELECT l.rowid {REGION} WHERE n.n_regionkey<>0 ORDER BY l.rowid LIMIT 32").fetchall()
        workload = [("scoped_change", rid) for rid, in scoped[:32]]
        workload += [("scoped_zero", rid) for rid, in scoped[32:]]
        workload += [("outside_change", rid) for rid, in outside]
        if len({rid for _, rid in workload}) != 96:
            raise ValueError("paired workload has an incomplete or duplicate key cohort")
        for repeat in range(5):
            randomizer.shuffle(workload)
            arms = ["untracked", "tracked"]
            randomizer.shuffle(arms)
            ticks, wal_bytes = {}, {}
            for arm in arms:
                ticks[arm] = measure(db, workload, arm == "tracked", durable=bool(args.durable_db))
                if args.durable_db:
                    wal_bytes[arm] = wal.stat().st_size
            trial = {"repeat": repeat + 1, "order": arms, "transaction_ns": ticks}
            if wal_bytes:
                trial["wal_bytes_after_commits"] = wal_bytes
            trials.append(trial)
    if args.durable_db:
        with duckdb.connect(database, read_only=True) as persisted:
            if persisted.execute("SELECT count(*) FROM edits").fetchone() != (96,):
                raise ValueError("reopened overlay does not contain the final committed arm")
            if arms[-1] == "tracked" and persisted.execute("SELECT tok FROM epoch").fetchone() != (32,):
                raise ValueError("reopened epoch differs from the last committed arm")
    groups = ("scoped_change", "outside_change", "scoped_zero")
    by_class = {}
    for group in groups:
        median_ms = {arm: [median(trial["transaction_ns"][arm][group]) / 1e6 for trial in trials]
                     for arm in ("untracked", "tracked")}
        by_class[group] = {
            "median_of_pair_medians_ms": {arm: median(times) for arm, times in median_ms.items()},
            "median_of_within_pair_ratios": median(b / a for a, b in zip(
                median_ms["untracked"], median_ms["tracked"])),
        }
    result = {
        "engine": duckdb.__version__, "scale": 1, "lineitem_rows": population,
        "extension_sha256": manifest["extension_sha256"],
        "timed_transactions_per_arm_per_pair": len(workload), "pairs": trials,
        "summary": by_class,
    }
    if args.durable_db:
        result["storage"] = {"durable_tables": True, "commit_per_write": True,
                             "reopen_verified": True, "database_bytes_after_close": Path(database).stat().st_size}
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
