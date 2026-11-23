"""Native paired controls for execution-bound and request-layer witnesses."""

import argparse
from collections import Counter
from contextlib import closing
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory


def snapshot(root, variant, faulty):
    requested, alternate = root / "requested.db", root / "alternate.db"
    for generation, path in enumerate((requested, alternate), 1):
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript("CREATE TABLE provenance(generation INTEGER); "
                             "CREATE TABLE values_by_key(k INTEGER PRIMARY KEY, v INTEGER);")
            db.execute("INSERT INTO provenance VALUES (?)", (generation,))
            db.executemany("INSERT INTO values_by_key VALUES (?,?)", [(1, variant), (2, generation)])
    with closing(sqlite3.connect(requested)) as db:
        captured = db.execute("SELECT generation FROM provenance").fetchone()[0]
    actual = alternate if faulty else requested
    with closing(sqlite3.connect(actual.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        bound = db.execute("SELECT generation FROM provenance").fetchone()[0]
        value = db.execute("SELECT v FROM values_by_key WHERE k=1").fetchone()[0]
        db.commit()
    return {"generation": 1, "value": variant}, {"generation": bound, "value": value}, {
        "generation": captured, "value": value}


def crash_after_write(dbpath, variant):
    import os

    with sqlite3.connect(dbpath) as db:
        db.execute("UPDATE source SET revision=2, value=?", (variant + 10,))
    with sqlite3.connect(dbpath) as db:
        db.execute("UPDATE derived SET epoch=2, value=?", (2 * (variant + 10),))
        os._exit(73)


def epoch(root, variant, operation):
    dbpath = root / "epoch.db"
    with closing(sqlite3.connect(dbpath)) as db, db:
        db.executescript("CREATE TABLE source(revision INTEGER, value INTEGER); "
                         "CREATE TABLE derived(epoch INTEGER, value INTEGER);")
        db.execute("INSERT INTO source VALUES (1,?)", (variant,))
        db.execute("INSERT INTO derived VALUES (1,?)", (2 * variant,))
    target = variant + 10
    exit_status = None
    if operation == "crash_after_write":
        worker = subprocess.run([sys.executable, "-B", __file__, "--crash-worker",
                                 str(dbpath), str(variant)], capture_output=True, text=True)
        exit_status = worker.returncode
        if exit_status != 73:
            raise RuntimeError(f"Crash injection did not reach the declared point: {worker.stderr}")
    else:
        with closing(sqlite3.connect(dbpath)) as writer:
            if operation == "rollback_after_epoch":
                writer.execute("UPDATE derived SET epoch=2, value=?", (2 * target,))
                writer.commit()
                writer.execute("UPDATE source SET revision=2, value=?", (target,))
                writer.rollback()
            else:
                with writer:
                    writer.execute("UPDATE source SET revision=2, value=?", (target,))
                    writer.execute("UPDATE derived SET epoch=2, value=?", (2 * target,))
    with closing(sqlite3.connect(dbpath)) as db:
        db.execute("BEGIN")
        revision, value = db.execute("SELECT revision,value FROM source").fetchone()
        derived_epoch, derived_value = db.execute("SELECT epoch,value FROM derived").fetchone()
        db.commit()
    expected = {"revision": 2, "source_value": target, "epoch": 2, "derived_value": 2 * target}
    actual = {"revision": revision, "source_value": value, "epoch": derived_epoch, "derived_value": derived_value}
    return expected, actual, expected.copy(), exit_status


def intent(root, variant, faulty):
    with closing(sqlite3.connect(root / "intent.db")) as db, db:
        db.executescript("""
            CREATE TABLE target(k INTEGER PRIMARY KEY, v INTEGER);
            CREATE TABLE effects(sequence INTEGER PRIMARY KEY, op TEXT, k INTEGER);
            CREATE TRIGGER observe_update AFTER UPDATE ON target BEGIN
                INSERT INTO effects (op,k) VALUES
                    (CASE WHEN NEW.v IS NULL THEN 'CLEAR' ELSE 'WRITE' END, NEW.k);
            END;
        """)
        db.execute("INSERT INTO target VALUES (?, NULL)", (variant,))
        db.commit()
        if faulty:
            db.execute("UPDATE target SET v=NULL WHERE k=?", (variant,))
        db.commit()
        value = db.execute("SELECT v FROM target WHERE k=?", (variant,)).fetchone()[0]
        actual = [list(row) for row in db.execute("SELECT op,k FROM effects ORDER BY sequence")]
    expected = {"value": None, "effects": []}
    return expected, {"value": value, "effects": actual}, {"value": value, "effects": []}


def trial(name, variant, faulty, operation, values, exit_status=None):
    expected, bound, log = values
    return {"family": name, "variant": variant, "execution": operation, "legal": not faulty,
            "reference": expected, "execution_bound_witness": bound, "request_layer_witness": log,
            "execution_bound_accept": bound == expected, "request_layer_accept": log == expected,
            "injected_process_exit": exit_status}


def run(plan_path):
    raw = plan_path.read_bytes()
    plan = json.loads(raw)
    observations = []
    for variant in plan["m2"]["variants"]:
        for family, function in (("O1", snapshot), ("O5", intent)):
            for faulty in (False, True):
                with TemporaryDirectory(prefix="obseq-binding-") as directory:
                    values = function(Path(directory), variant, faulty)
                operation = {"O1": "alternate_snapshot", "O5": "clear_logged_as_keep"}[family] if faulty else "control"
                observations.append(trial(family, variant, faulty, operation, values))
        for operation in ("atomic_control", "crash_after_write", "rollback_after_epoch"):
            with TemporaryDirectory(prefix="obseq-binding-") as directory:
                expected, actual, log, code = epoch(Path(directory), variant, operation)
            observations.append(trial("O2", variant, operation != "atomic_control", operation,
                                      (expected, actual, log), code))
    summary = {}
    for family in ("O1", "O2", "O5"):
        group = [row for row in observations if row["family"] == family]
        counts = {"legal": sum(r["legal"] for r in group), "faulty": sum(not r["legal"] for r in group)}
        for level in ("execution_bound", "request_layer"):
            errors = Counter("false_reject" if row["legal"] else "false_accept" for row in group
                             if row["legal"] != row[f"{level}_accept"])
            counts[level] = {key: errors[key] for key in ("false_reject", "false_accept")}
        summary[family] = counts
    return {"plan_sha256": hashlib.sha256(raw).hexdigest(), "sqlite": sqlite3.sqlite_version,
            "results": observations, "summary": summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=Path(__file__).with_name("PLAN.json"))
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--crash-worker", nargs=2, metavar=("DB", "VARIANT"))
    args = parser.parse_args()
    if args.crash_worker:
        crash_after_write(args.crash_worker[0], int(args.crash_worker[1]))
        raise RuntimeError("Crash worker returned normally")
    result = run(args.plan)
    if args.csv:
        fields = ("family", "variant", "execution", "legal", "execution_bound_accept",
                  "request_layer_accept", "injected_process_exit")
        with args.csv.open("x", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(result["results"])
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
