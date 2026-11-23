"""Same-witness Python and dbt assertions on the C1 and C2 replay cohorts."""

import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import sqlite3
import subprocess
from tempfile import TemporaryDirectory

import duckdb

from binding_faults import intent


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def snapshot(root, variant, legal):
    live, stale = root / "live.db", root / "stale.db"
    with closing(sqlite3.connect(live)) as db, db:
        if db.execute("PRAGMA journal_mode=wal").fetchone()[0] != "wal":
            raise ValueError("Failed to enable WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
        db.execute("CREATE TABLE vals(k INTEGER, v INTEGER)")
        db.execute("INSERT INTO vals VALUES (1,?)", (variant,))
        db.commit()
        db.execute("PRAGMA wal_checkpoint(truncate)")
        original = hashlib.sha256(live.read_bytes()).hexdigest()
        db.execute("UPDATE vals SET v=?", (variant + 100,))
        db.commit()
        shutil.copyfile(live, stale)
        if hashlib.sha256(stale.read_bytes()).hexdigest() != original or not (root / "live.db-wal").stat().st_size:
            raise ValueError("C1 F3 must reproduce the native WAL mechanism")
        with closing(sqlite3.connect(live if legal else stale)) as query:
            payload = query.execute("SELECT k,v FROM vals ORDER BY k").fetchall()
    return {"logical_digest": digest([(1, variant + 100)])}, {"logical_digest": digest(payload)}


def freshness(root, variant, legal):
    path = root / "stored.db"
    old = lambda x: 2 * x
    new = lambda x: 2 * x + 1
    with closing(sqlite3.connect(path)) as db, db:
        db.create_function("derive", 1, old, deterministic=True)
        db.execute("CREATE TABLE g(x INTEGER, y INTEGER GENERATED ALWAYS AS(derive(x)) STORED, epoch INTEGER)")
        db.execute("INSERT INTO g(x,epoch) VALUES (?, 1)", (variant + 3,))
    with closing(sqlite3.connect(path)) as db, db:
        db.create_function("derive", 1, new, deterministic=True)
        if legal:
            db.execute("UPDATE g SET x=x, epoch=2")
        epoch, y = db.execute("SELECT epoch,y FROM g").fetchone()
    return {"epoch": 2, "value": 2 * (variant + 3) + 1}, {"epoch": epoch, "value": y}


def c1_roster(home):
    rows = []
    native = read(home / "submission-e-series-native-evidence/e23/result.json")
    selectors = {row["case"]: [] for row in native["observations"] if row["case"] in ("F3", "F4", "F5")}
    for row in native["observations"]:
        if row["case"] in selectors:
            selectors[row["case"]].append(row)
    for category, prior in selectors.items():
        if len(prior) != 3 or any(row["expected_legal"] for row in prior):
            raise ValueError("C1 scope differs from the archived F3–F5 roster")
        for old_row in prior:
            variant = old_row["arm"]
            for legal in (False, True):
                with TemporaryDirectory(prefix="obseq-same-witness-") as directory:
                    root = Path(directory)
                    if category == "F5":
                        expected, actual, _ = intent(root, variant, not legal)
                    else:
                        expected, actual = {"F3": snapshot, "F4": freshness}[category](root, variant, legal)
                rows.append({"id": f"C1-{category}-{variant}-{'legal' if legal else 'fault'}",
                             "cohort": "C1", "mechanism": category, "legal": legal,
                             "reference": expected, "witness": actual, "obseq_accepts": actual == expected})
    return rows


def c2_roster(home):
    source = home / "heldout-ordered-intervention-receipts"
    fixture = read(source / "CASES.json")
    data = {row["id"]: row["legal"] for row in read(source / "SEALED_LABELS.json")}
    check = runpy.run_path(str(source / "check.py"))
    rows = []
    for case in fixture:
        expected_state, expected_events = check["expected"](case)
        state, events = check["native"](case, "SQLite")
        if (state, events) != check["native"](case, "DuckDB"):
            raise ValueError(f"Native committed witnesses disagree on {case['id']}")
        expected = {"state": expected_state, "events": expected_events, "committed": True}
        actual = {"state": state, "events": events, "committed": case["outcome"] == "commit"}
        label = data[case["id"]]
        rows.append({"id": f"C2-{case['id']}", "cohort": "C2", "mechanism": "ordered-intervention",
                     "legal": label, "reference": expected, "witness": actual,
                     "obseq_accepts": check["observe"](case, (state, events))["typed"]})
    if len(rows) != 24 or sum(row["legal"] for row in rows) != 12:
        raise ValueError("Expected 12 frozen legal and 12 frozen illegal C2 executions")
    return rows


def want_accept(row):
    try:
        assert row["witness"] == row["reference"]
    except AssertionError:
        return False
    return True


def dbt_cases(root, executable, rows):
    project = root / "dbt_project.yml"
    project.write_text('name: obseq_equal_information\nversion: "1.0.0"\nconfig-version: 2\n'
                       'profile: obseq_equal_information\ntest-paths: [tests]\nmodel-paths: [models]\n',
                       encoding="utf-8")
    (root / "profiles.yml").write_text("obseq_equal_information:\n  target: native\n  outputs:\n"
        "    native:\n      type: duckdb\n      path: witness.duckdb\n      threads: 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "models").mkdir()
    (root / "tests" / "same_witness.sql").write_text(
        "SELECT id FROM main.witness WHERE observed IS DISTINCT FROM expected\n", encoding="utf-8")
    freshness_ids = {}
    yaml = ["version: 2", "sources:", "  - name: witness_inputs", "    schema: main", "    tables:"]
    with duckdb.connect(str(root / "witness.duckdb")) as db:
        db.execute("CREATE TABLE witness(id VARCHAR, expected VARCHAR, observed VARCHAR)")
        db.executemany("INSERT INTO witness VALUES (?,?,?)", [
            (row["id"], canonical(row["reference"]), canonical(row["witness"])) for row in rows])
        for index, row in enumerate(rows):
            if row["mechanism"] not in ("F4", "ordered-intervention"):
                continue
            table = f"load_{index}"
            freshness_ids[f"source.obseq_equal_information.witness_inputs.{table}"] = row["id"]
            db.execute(f"CREATE TABLE {table} AS SELECT current_timestamp AS loaded_at")
            yaml.extend([f"      - name: {table}", "        config:", "          loaded_at_field: loaded_at",
                         "          freshness:", "            error_after: {count: 1, period: hour}"])
    (root / "models" / "sources.yml").write_text("\n".join(yaml) + "\n", encoding="utf-8")
    common = [str(executable), "--no-use-colors", "--no-send-anonymous-usage-stats"]
    profile = ["--profiles-dir", str(root)]
    test = subprocess.run([*common, "test", *profile, "--store-failures"], cwd=root, text=True, capture_output=True)
    receipt = root / "target" / "run_results.json"
    if not receipt.is_file():
        raise RuntimeError(test.stdout + test.stderr)
    parsed = read(receipt)["results"]
    if len(parsed) != 1 or parsed[0]["status"] not in ("pass", "fail") or test.returncode not in (0, 1):
        raise RuntimeError(test.stdout + test.stderr)
    with duckdb.connect(str(root / "witness.duckdb"), read_only=True) as db:
        failed = {key for key, in db.execute("SELECT id FROM main_dbt_test__audit.same_witness").fetchall()}
    if len(failed) != parsed[0]["failures"]:
        raise ValueError("dbt audited rows do not match its failure count")
    freshness = subprocess.run([*common, "source", "freshness", *profile], cwd=root, text=True, capture_output=True)
    receipt = root / "target" / "sources.json"
    if not receipt.is_file():
        raise RuntimeError(freshness.stdout + freshness.stderr)
    sources = read(receipt)["results"]
    flags = {freshness_ids[row["unique_id"]]: row["status"] for row in sources}
    if len(flags) != len(freshness_ids) or set(flags.values()) - {"pass", "warn", "error"}:
        raise RuntimeError(freshness.stdout + freshness.stderr)
    for row in rows:
        row["dbt_singular_accepts"] = row["id"] not in failed
        row["dbt_stock_source_freshness"] = flags.get(row["id"])
    return {"dbt_test_exit": test.returncode, "freshness_exit": freshness.returncode,
            "freshness_sources": len(sources)}


def run(home, dbt):
    rows = c1_roster(home) + c2_roster(home)
    for row in rows:
        row["python_assert_accepts"] = want_accept(row)
    with TemporaryDirectory(prefix="obseq-dbt-witness-") as directory:
        info = dbt_cases(Path(directory), dbt, rows)
    summary = {}
    for cohort in ("C1", "C2"):
        group = [row for row in rows if row["cohort"] == cohort]
        summary[cohort] = {}
        for arm in ("obseq_accepts", "python_assert_accepts", "dbt_singular_accepts", "dbt_stock_source_freshness"):
            counts = Counter()
            for row in group:
                decision = row[arm]
                if decision is None:
                    counts["not_applicable"] += 1
                    continue
                accepted = decision == "pass" if isinstance(decision, str) else decision
                label = "true_" if row["legal"] == accepted else "false_"
                counts[label + ("accept" if accepted else "reject")] += 1
            summary[cohort][arm] = dict(counts)
    from importlib.metadata import version
    return {"versions": {name: version(name) for name in ("dbt-core", "dbt-duckdb", "duckdb")},
            "sqlite": sqlite3.sqlite_version, "dbt": info, "summary": summary, "observations": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("dbt", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.evidence.resolve(), args.dbt.resolve()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
