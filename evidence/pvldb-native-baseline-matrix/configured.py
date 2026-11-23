"""Replay the two configured dbt tests and two configured Deequ constraints."""

import argparse
from collections import Counter, defaultdict
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile


DBT = {"dbt-core": "1.10.15", "dbt-duckdb": "1.9.6", "duckdb": "2.0.1"}
SPARK = "4.0.1"


def encode(row):
    return json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode().hex()


def export(args):
    from file_and_shape import entries

    rows = list(entries(args.matrix, args.panels, args.representative, args.value_driver))
    print(json.dumps(rows, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def dbt_configured(pairs):
    import duckdb

    if DBT != {key: version(key) for key in DBT} or duckdb.__version__ != DBT["duckdb"]:
        raise ValueError("unexpected configured dbt environment")
    with TemporaryDirectory(prefix="e5-dbt-") as temp:
        root = Path(temp)
        db = root / "test.db"
        (root / "models").mkdir()
        (root / "tests").mkdir()
        with duckdb.connect(str(db)) as con:
            for name, position in (("got", 5), ("expected", 4)):
                con.execute(f"CREATE TABLE {name}(id INTEGER, k VARCHAR)")
                rows = [(i, f"{i}:{encode(row)}") for i, pair in enumerate(pairs) for row in pair[position]]
                con.executemany(f"INSERT INTO {name} VALUES (?, ?)", rows)

        def document(name, value):
            (root / name).write_text(json.dumps(value), encoding="utf-8")

        document("profiles.yml", {"audit": {"target": "local", "outputs": {
            "local": {"type": "duckdb", "path": str(db), "threads": 1}}}})
        document("dbt_project.yml", {"name": "audit", "version": "1.0.0", "profile": "audit",
                                     "test-paths": ["tests"], "data_tests": {"+store_failures": True}})
        relationships = {"relationships": {"arguments": {"to": "source('frozen', 'expected')", "field": "k"}}}
        document("models/sources.yml", {"version": 2, "sources": [{"name": "frozen", "schema": "main", "tables": [
            {"name": "got", "columns": [{"name": "k", "data_tests": [relationships]}]}, {"name": "expected"},
        ]}]})
        (root / "tests/fixed_bag.sql").write_text("""
            WITH actual AS (SELECT id, k, count(*) n FROM {{ source('frozen', 'got') }} GROUP BY id, k),
                 gold AS (SELECT id, k, count(*) n FROM {{ source('frozen', 'expected') }} GROUP BY id, k)
            SELECT coalesce(actual.id, gold.id) id, k FROM actual FULL JOIN gold USING (id, k)
            WHERE actual.n IS DISTINCT FROM gold.n
        """, encoding="utf-8")
        env = os.environ | {"DBT_SEND_ANONYMOUS_USAGE_STATS": "false", "DBT_PROJECT_DIR": temp,
                            "DBT_PROFILES_DIR": temp, "OPENBLAS_NUM_THREADS": "1"}
        cmd = [sys.executable, "-B", "-c", "from dbt.cli.main import cli; cli()", "test", "--no-partial-parse"]
        child = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)
        output = root / "target/run_results.json"
        if not output.exists():
            raise RuntimeError(child.stdout + child.stderr)
        results = json.loads(output.read_bytes())["results"]
        if child.returncode not in (0, 1) or len(results) != 2 or any(x["status"] not in ("pass", "fail") for x in results):
            raise RuntimeError(child.stdout + child.stderr)
        failed = {}
        with duckdb.connect(str(db), read_only=True) as con:
            for result in results:
                fixed = ".fixed_bag" in result["unique_id"]
                name = "typed_fixed_golden" if fixed else "stock_relationships"
                field = "id" if fixed else "CAST(split_part(from_field, ':', 1) AS INTEGER)"
                failed[name] = {row[0] for row in con.execute(
                    f"SELECT DISTINCT {field} FROM {result['relation_name']}").fetchall()}
        return {"versions": DBT, "native_cases_executed": len(pairs)}, [
            {name: i not in failures for name, failures in failed.items()} for i in range(len(pairs))]


def deequ_configured(pairs, spark, jar, scala):
    java = shutil.which("java")
    if java is None:
        raise ValueError("Spark execution requires Java")
    unique = {}
    ids = []
    for _, _, _, _, left, right in pairs:
        key = tuple(map(encode, left)), tuple(map(encode, right))
        ids.append(unique.setdefault(key, len(unique)))

    with TemporaryDirectory(prefix="e5-deequ-") as temp:
        root = Path(temp)
        classes = root / "classes"
        classes.mkdir()
        source = root / "input.jsonl"
        with source.open("w", encoding="utf-8") as file:
            for (gold, candidate), index in unique.items():
                file.write(json.dumps({"id": index, "gold": gold, "candidate": candidate}) + "\n")
        env = os.environ | {"SPARK_LOCAL_IP": "127.0.0.1", "SPARK_LOCAL_HOSTNAME": "localhost",
                            "SPARK_LOCAL_DIRS": str(root), "SPARK_HOME": str(spark)}
        classpath = os.pathsep.join((str(spark / "jars/*"), str(jar)))
        subprocess.run([java, "-Dscala.usejavacp=true", "-cp", classpath,
                        "scala.tools.nsc.Main", "-d", str(classes), str(scala)], env=env, check=True)
        program = root / "control.jar"
        with ZipFile(program, "w") as file:
            for binary in sorted(classes.rglob("*.class")):
                file.write(binary, binary.relative_to(classes))
        cmd = [str(spark / "bin/spark-submit"), "--master", "local[2]", "--driver-memory", "1g",
               "--conf", "spark.ui.enabled=false", "--conf", "spark.sql.shuffle.partitions=2",
               "--conf", "spark.driver.host=127.0.0.1", "--conf", "spark.driver.bindAddress=127.0.0.1",
               "--jars", str(jar), "--class", "DeequControl", str(program), str(source)]
        child = subprocess.run(cmd, cwd=root, env=env, text=True, capture_output=True)
        if child.returncode:
            raise RuntimeError(child.stderr[-7000:])
        decisions = {}
        spark_version = None
        for line in child.stdout.splitlines():
            if line.startswith("EAB_DECISION\t"):
                _, index, size, golden = line.split("\t")
                decisions[int(index)] = {"stock_size": size == "true", "typed_fixed_golden": golden == "true"}
            elif line.startswith("EAB_SPARK\t"):
                spark_version = line.split("\t")[1]
        if spark_version != SPARK or set(decisions) != set(ids):
            raise ValueError("missing native Deequ or Spark receipts")
        return {"versions": {"deequ": "2.0.15-spark-4.0", "spark": SPARK},
                "native_cases_executed": len(unique)}, [decisions[index] for index in ids]


def score(pairs, metadata, decisions):
    summaries = defaultdict(lambda: defaultdict(Counter))
    observations = []
    for (cohort, identity, arm, legal, reference, candidate), verdicts in zip(pairs, decisions, strict=True):
        left = Counter(map(encode, reference))
        right = Counter(map(encode, candidate))
        checks = {"stock_relationships": right.keys() <= left.keys(),
                  "typed_fixed_golden": right == left, "stock_size": len(reference) == len(candidate)}
        for name, accepted in verdicts.items():
            if accepted != checks[name]:
                raise ValueError(f"native output disagrees with authored policy for {identity}/{arm}/{name}")
            key = ("true_" if accepted == legal else "false_") + ("accept" if accepted else "reject")
            summaries[cohort][name][key] += 1
        observations.append({"cohort": cohort, "id": identity, "arm": arm, "legal": legal, **verdicts})
    print(json.dumps({**metadata, "summaries": summaries, "observations": observations}, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_subparsers(dest="mode", required=True)
    exporter = modes.add_parser("export")
    for name in ("matrix", "panels", "representative", "value_driver"):
        exporter.add_argument(name, type=Path)
    modes.add_parser("dbt").add_argument("pairs", type=Path)
    deequ = modes.add_parser("deequ")
    for name in ("pairs", "spark", "jar", "scala"):
        deequ.add_argument(name, type=Path)
    args = parser.parse_args()
    if args.mode == "export":
        export(args)
        return
    pairs = json.loads(args.pairs.read_bytes())
    if args.mode == "dbt":
        metadata, decisions = dbt_configured(pairs)
    else:
        metadata, decisions = deequ_configured(pairs, args.spark.resolve(), args.jar.resolve(), args.scala.resolve())
    score(pairs, metadata, decisions)


if __name__ == "__main__":
    main()
