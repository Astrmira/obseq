"""Measure the pinned general verifier and a diagnostic split on the same inputs."""

import argparse
from collections import defaultdict
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform
import resource
import runpy
from statistics import median, quantiles
import subprocess
import sys
from time import perf_counter_ns


def read(path):
    return json.loads(Path(path).read_bytes())


def hash_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def query_list(config):
    rows = {}
    for suite, source in config["queries"].items():
        rows[suite] = (dict(enumerate(Path(source).read_text(encoding="utf-8").splitlines(), 1))
                       if suite == "clickbench" else {int(key): sql for key, sql in read(source)["queries"]})
    return rows


def bind(db, suite, config):
    if suite != "clickbench":
        return
    shards = ", ".join("'" + path.replace("'", "''") + "'" for path in config["shards"])
    db.execute(f"""CREATE VIEW hits AS SELECT * REPLACE (
        DATE '1970-01-01' + CAST(EventDate AS INTEGER) AS EventDate,
        make_timestamp(EventTime * 1000000) AS EventTime
    ) FROM read_parquet([{shards}], binary_as_string=true)""")


def measure(config, suite, number, rep):
    sys.path.insert(0, config["validator"])
    import duckdb
    import pyarrow as pa
    import sqlglot
    from cutoffs import compile_window
    from verify_windows import call, check

    versions = [duckdb.__version__, pa.__version__, sqlglot.__version__]
    if versions != ["1.4.3", "22.0.0", "28.0.0"]:
        raise ValueError(f"Wrong engine/compiler runtime: {versions}")
    query = query_list(config)[suite][number]
    path = config["databases"].get(suite)
    threads = 8 if suite == "clickbench" else 1
    settings = {"threads": threads, "memory_limit": "34GB", "temp_directory": config["spill"]}
    with duckdb.connect(path or ":memory:", read_only=bool(path), config=settings) as db:
        bind(db, suite, config)
        start = perf_counter_ns()
        candidate = db.execute(query).fetch_arrow_table()
        producer = perf_counter_ns() - start
        arms = {"native": candidate}
        start = perf_counter_ns()
        end_to_end = call(db, query, arms)
        verifier = perf_counter_ns() - start
        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        start = perf_counter_ns()
        schema = db.execute(f"SELECT * FROM ({query.strip().rstrip(';')}) LIMIT 0").fetch_arrow_table()
        window = compile_window(query, schema.column_names)
        if schema.schema.types != candidate.schema.types or window is None:
            raise ValueError("The phase diagnostic does not bind the same output schema")
        compile_ns = perf_counter_ns() - start
        start = perf_counter_ns()
        db.execute(f"CREATE TEMP TABLE __timed_eligible AS {window.relation}")
        candidate_ns = perf_counter_ns() - start
        staged = replace(window, relation="SELECT * FROM __timed_eligible")
        start = perf_counter_ns()
        staged_result = check(db, staged, arms)
        check_ns = perf_counter_ns() - start
        rows = db.execute("SELECT count(*) FROM __timed_eligible").fetchone()[0]
        if staged_result != end_to_end or not end_to_end["native"]["accepted"]:
            raise ValueError(f"Verifier result or staged phase changed: {end_to_end}, {staged_result}")
    return {"suite": suite, "query": number, "repeat": rep, "status": "ok", "threads": threads,
            "runtime_versions": versions, "producer_ns": producer, "validator_ns": verifier,
            "compile_ns": compile_ns, "candidate_ns": candidate_ns, "staged_check_ns": check_ns,
            "e2e_worker_peak_rss_kib": peak_rss,
            "staged_worker_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "candidate_rows": rows, "output_rows": candidate.num_rows}


def freeze(config, path):
    upstream = runpy.run_path(config["upstream"])
    if hash_file(config["queries"]["clickbench"]) != upstream["STOCK_SHA"]:
        raise ValueError("Publisher SQL digest differs")
    shards = upstream["load_shards"](Path(config["acquisition"]), list(map(Path, config["stores"])))
    config["shards"] = [str(p) for p in shards]
    census = {}
    roster = query_list(config)
    for suite, receipt in config["censuses"].items():
        records = [json.loads(line) for line in Path(receipt).read_bytes().splitlines()]
        for row in records:
            query_sha = hashlib.sha256(roster[suite][row["query"]].encode()).hexdigest()
            if row["status"] != "verified" or row["sql_sha256"] != query_sha:
                raise ValueError(f"Census mismatch for {suite} Q{row['query']}")
        census[suite] = records
    plan = read(Path(__file__).with_name("PLAN.json"))
    if {suite: len(rows) for suite, rows in census.items()} != plan["m6"]["expected_windows"]:
        raise ValueError("The frozen full-scale window roster is incomplete")
    config["windows"] = census
    inputs = {"plan": Path(__file__).with_name("PLAN.json"), "harness": Path(__file__),
              "validator": Path(config["validator"]) / "verify_windows.py",
              "compiler": Path(config["validator"]) / "cutoffs.py", "acquisition": config["acquisition"]}
    for category in ("queries", "censuses", "databases"):
        inputs.update({f"{category}/{suite}": p for suite, p in config[category].items()})
    config["input_sha256"] = {name: hash_file(p) for name, p in inputs.items()}
    config["environment"] = {command: subprocess.check_output(command.split(), text=True) for command in (
        "lscpu", "free -b", "df -Th .", "uname -srv")}
    config["environment"]["python"] = platform.python_version()
    config["repeats"] = plan["m6"]["repeats"]
    with path.open("x", encoding="utf-8") as out:
        json.dump(config, out, indent=2, sort_keys=True)
        out.write("\n")


def run(path, output):
    config = read(path)
    existing = ([json.loads(line) for line in output.read_bytes().splitlines()] if output.exists() else [])
    completed = {(row["suite"], row["query"], row["repeat"]) for row in existing}
    config_sha = hash_file(path)
    if len(existing) != len(completed) or any(row["config_sha256"] != config_sha for row in existing):
        raise ValueError("Saved timing data come from a different frozen plan or contain duplicate workers")
    with output.open("a", encoding="utf-8") as out:
        for rep in range(config["repeats"]):
            for suite, rows in config["windows"].items():
                for window in rows:
                    number = window["query"]
                    if (suite, number, rep) in completed:
                        continue
                    proc = subprocess.run([sys.executable, "-B", __file__, "worker", str(path),
                                           suite, str(number), str(rep)], capture_output=True, text=True)
                    if proc.returncode:
                        row = {"suite": suite, "query": number, "repeat": rep, "status": "failed",
                               "exit_code": proc.returncode, "diagnostic": proc.stderr}
                    else:
                        row = json.loads(proc.stdout)
                        if row["candidate_rows"] != window["candidate_rows"]:
                            row.update(status="census_mismatch", expected_candidate_rows=window["candidate_rows"])
                    row["config_sha256"] = config_sha
                    print(json.dumps(row, sort_keys=True), file=out, flush=True)
                    print(suite, number, rep, row["status"], flush=True)


def summarize(path, raw):
    config = read(path)
    rows = [json.loads(line) for line in raw.read_bytes().splitlines()]
    seen, groups = set(), defaultdict(list)
    failures = []
    metrics = ["producer_ns", "validator_ns", "compile_ns", "candidate_ns", "staged_check_ns",
               "e2e_worker_peak_rss_kib", "staged_worker_peak_rss_kib"]
    config_sha = hash_file(path)
    for row in rows:
        key = (row["suite"], row["query"], row["repeat"])
        if key in seen or row["config_sha256"] != config_sha:
            raise ValueError(f"Duplicate worker or wrong config: {key}")
        seen.add(key)
        if row["status"] != "ok":
            failures.append(row)
            continue
        for stage in ("validator", "compile", "candidate", "staged_check"):
            row[f"{stage}_over_producer"] = row[f"{stage}_ns"] / row["producer_ns"]
        groups[key[:2]].append(row)
    metrics += [f"{stage}_over_producer" for stage in ("validator", "compile", "candidate", "staged_check")]
    queries = []
    for suite, windows in config["windows"].items():
        for window in windows:
            group = groups[suite, window["query"]]
            if len(group) == config["repeats"]:
                queries.append({"suite": suite, **window,
                                **{name: median(row[name] for row in group) for name in metrics}})
    distribution = {}
    for name in metrics:
        values = [query[name] for query in queries]
        if len(values) > 1:
            distribution[name] = {"median": median(values), "p90": quantiles(values, n=10, method="inclusive")[8],
                                  "max": max(values)}
    return {"workers": len(rows), "expected_workers": sum(map(len, config["windows"].values())) * config["repeats"],
            "complete_windows": len(queries), "failures": failures, "distribution": distribution,
            "slowest_validator": sorted(queries, key=lambda q: q["validator_ns"], reverse=True)[:3],
            "largest_candidate": max(queries, key=lambda q: q["candidate_rows"], default=None),
            "largest_boundary_peer_group": max(queries, key=lambda q: max(q["lower_peers"] or 0,
                                                                         q["upper_peers"] or 0), default=None),
            "per_query": queries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    for mode in ("freeze", "run", "summarize"):
        sub = modes.add_parser(mode)
        sub.add_argument("config", type=Path)
        sub.add_argument("output", type=Path)
    worker = modes.add_parser("worker")
    worker.add_argument("config", type=Path)
    worker.add_argument("suite")
    worker.add_argument("number", type=int)
    worker.add_argument("repeat", type=int)
    args = parser.parse_args()
    if args.mode == "freeze":
        freeze(read(args.config), args.output)
    elif args.mode == "run":
        run(args.config, args.output)
    elif args.mode == "worker":
        print(json.dumps(measure(read(args.config), args.suite, args.number, args.repeat)))
    else:
        print(json.dumps(summarize(args.config, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
