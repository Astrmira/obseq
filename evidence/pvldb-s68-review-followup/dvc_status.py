"""Exercise stock DVC stage invalidation with and without explicit dependencies."""

import argparse
from contextlib import closing
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory


MATERIALIZER = """
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
file, source, output = sys.argv[1:]
with closing(sqlite3.connect(file)) as db:
    if source == "udf":
        from definition import derive
        db.create_function("derive", 1, derive, deterministic=True)
        value, = db.execute("SELECT derive(k) FROM observed").fetchone()
    else:
        value, = db.execute("SELECT value FROM observed").fetchone()
Path(output).write_text(str(value), encoding="utf-8")
"""


def invoke(dvc, root, *args):
    proc = subprocess.run([str(dvc), *args], cwd=root, text=True, capture_output=True)
    if proc.returncode:
        raise RuntimeError(proc.stdout + proc.stderr)
    return proc.stdout


def configure(dvc, root, source, explicit):
    invoke(dvc, root, "init", "--no-scm")
    invoke(dvc, root, "config", "core.analytics", "false")
    (root / "materializer.py").write_text(MATERIALIZER, encoding="utf-8")
    for name in ("tracked", "omitted"):
        command = subprocess.list2cmdline(
            [sys.executable, "-B", "materializer.py", "source.db", source, f"{name}.txt"])
        flags = ["-d", explicit] if name == "tracked" else []
        invoke(dvc, root, "stage", "add", "-n", name, "-d", "materializer.py", "-d", "source.db",
               *flags, "-O", f"{name}.txt", command)
    invoke(dvc, root, "repro")


def status(dvc, root):
    return json.loads(invoke(dvc, root, "status", "--json"))


def output(root, name):
    return int((root / f"{name}.txt").read_text(encoding="utf-8"))


def wal_case(dvc, root, variant):
    path = root / "source.db"
    with closing(sqlite3.connect(path)) as db:
        if db.execute("PRAGMA journal_mode=wal").fetchone()[0] != "wal":
            raise ValueError("WAL mode was not enabled")
        db.execute("PRAGMA wal_autocheckpoint=0")
        db.executescript("CREATE TABLE observed(value INTEGER); CREATE TABLE log(k INTEGER);")
        db.execute("INSERT INTO observed VALUES (?)", (variant,))
        db.commit()
        db.execute("PRAGMA wal_checkpoint(truncate)")
        db.execute("INSERT INTO log VALUES (1)")
        db.commit()
        source_before = path.read_bytes()
        configure(dvc, root, "wal", "source.db-wal")
        initial = status(dvc, root)
        db.execute("UPDATE observed SET value=?", (variant + 100,))
        db.commit()
        if path.read_bytes() != source_before:
            raise ValueError("SQLite checkpoint would confound the DVC dependency contrast")
        shutil.copyfile(path, root / "stale.db")
        with closing(sqlite3.connect(root / "stale.db")) as stale:
            stale_value, = stale.execute("SELECT value FROM observed").fetchone()
        changed = status(dvc, root)
        outputs = {name: output(root, name) for name in ("tracked", "omitted")}
        invoke(dvc, root, "repro", "tracked")
        refreshed = status(dvc, root)
        current_output = output(root, "tracked")
    return {"before_change": initial, "after_change": changed, "after_tracked_repro": refreshed,
            "stale_snapshot_value": stale_value, "before_repro_outputs": outputs,
            "refreshed_output": current_output, "expected_output": variant + 100}


def udf_case(dvc, root, variant):
    path = root / "source.db"
    definition = root / "definition.py"
    definition.write_text("def derive(x):\n    return 2*x\n", encoding="utf-8")
    with closing(sqlite3.connect(path)) as db, db:
        db.create_function("derive", 1, lambda x: 2 * x, deterministic=True)
        db.execute("CREATE TABLE observed(k INTEGER, v INTEGER GENERATED ALWAYS AS(derive(k)) STORED)")
        db.execute("INSERT INTO observed(k) VALUES (?)", (variant + 3,))
    configure(dvc, root, "udf", "definition.py")
    initial = status(dvc, root)
    definition.write_text("def derive(x):\n    return 2*x+1\n", encoding="utf-8")
    with closing(sqlite3.connect(path)) as db:
        db.create_function("derive", 1, lambda x: 2 * x + 1, deterministic=True)
        stale, desired = db.execute("SELECT v,derive(k) FROM observed").fetchone()
    changed = status(dvc, root)
    outputs = {name: output(root, name) for name in ("tracked", "omitted")}
    invoke(dvc, root, "repro", "tracked")
    return {"before_change": initial, "after_change": changed, "after_tracked_repro": status(dvc, root),
            "stored_old_value": stale, "before_repro_outputs": outputs,
            "refreshed_output": output(root, "tracked"), "expected_output": desired}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dvc", type=Path)
    args = parser.parse_args()
    rows = []
    for family, case in (("F3", wal_case), ("F4", udf_case)):
        for variant in (1, 2, 3):
            with TemporaryDirectory(prefix="obseq-dvc-") as directory:
                row = case(args.dvc.resolve(), Path(directory), variant)
            if row["before_change"] or row["after_tracked_repro"] or row["refreshed_output"] != row["expected_output"]:
                raise ValueError(f"Unexpected DVC clean control or wrong refreshed output: {row}")
            rows.append({"family": family, "variant": variant, **row})
    print(json.dumps({"dvc": version("dvc"), "sqlite": sqlite3.sqlite_version,
                      "observations": rows,
                      "summary": {"cases": len(rows),
                                  "tracked_changed": sum("tracked" in row["after_change"] for row in rows),
                                  "omitted_changed": sum("omitted" in row["after_change"] for row in rows)}},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
