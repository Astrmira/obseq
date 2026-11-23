"""Run frozen native producers, keeping unavailable inputs distinct from failures."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from string import Formatter
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from compare_receipts import compare

PASS = {"PASS", "PASS_stable", "NA_input_binding"}


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def roles(case):
    params = case.get("args", [])
    return list(dict.fromkeys([
        *(key for value in params if not value.startswith("=")
          for _, key, _, _ in Formatter().parse(value) if key and key != "SCRATCH"),
        *case.get("python_path", []),
        *(item["role"] for item in case.get("verified_input_files", [])),
        *(arm["site"] for arm in case.get("arms", [])),
        *case.get("package_input_links", {}).values(),
        *case.get("scratch_input_links", {}).values(),
        *case.get("input_environment", {}).values(),
    ]))


def projected(blob, mode):
    result = json.loads(blob)
    if mode == "orientation-semantic":
        del result["worker_peak_kib"]
        for arm in result["measurements"].values():
            del arm["samples"], arm["median_ns"]
    elif mode == "q39-threshold-semantic":
        del result["binary64_row_changes"]
        arm = result["native"]["4"]
        del arm["exact_binary64_disagreements"]
        if not 0 <= arm.pop("max_ulp") <= 2:
            raise ValueError("Q39 exceeded the pinned ULP bound")
    else:
        raise ValueError(f"unknown receipt projection: {mode}")
    return result


def expect(case, observed, expected, policy):
    if mode := case.get("projection"):
        try:
            equal = projected(observed, mode) == projected(expected, mode)
        except (ValueError, KeyError, TypeError):
            equal = False
        return "PASS_stable" if equal else "FAIL_divergence"
    return compare(expected, observed, policy.get(case["case_id"], ()))


def execute(case, archive, inputs, work, args, policy):
    for name, info in case["blobs"].items():
        if not (archive / name).is_file() or digest(archive / name) != info["sha256"]:
            return "FAIL_digest", name
    needed = roles(case)
    for role in needed:
        if role in inputs and not Path(inputs[role]).exists():
            return "FAIL_input_path", role
    if missing := [role for role in needed if role not in inputs]:
        return "NA_input_binding", missing
    for item in case.get("verified_input_files", []):
        file = Path(inputs[item["role"]]) / item["file"]
        if not file.is_file() or digest(file) != item["sha256"]:
            return "FAIL_input_digest", f'{item["role"]}/{item["file"]}'

    pkg = work / "package"
    shutil.copytree(archive, pkg)
    vals = {**inputs, "SCRATCH": str(work)}
    params = [x[1:] if x.startswith("=") else x.format_map(vals) for x in case.get("args", [])]
    for home, key in ((pkg, "package_input_links"), (work, "scratch_input_links")):
        for name, role in case.get(key, {}).items():
            (home / name).symlink_to(Path(vals[role]).resolve())

    env = {**os.environ, "TMPDIR": str(work), "PROJ_NETWORK": "OFF",
           "PYTHONNOUSERSITE": "1", "OPENBLAS_NUM_THREADS": "1",
           "OBSEQ_SYSTEM_PYTHON": args.system_python}
    env.pop("PYTHONPATH", None)
    if args.zoneinfo:
        env["PYTHONTZPATH"] = str(args.zoneinfo)
    env.update({key: vals[role] for key, role in case.get("input_environment", {}).items()})
    sites = [vals[role] for role in case.get("python_path", [])]
    timeout = args.timeout or case.get("timeout", 70)

    def run(py, entry, path=sites, stdin=None, extra=()):
        settings = {**env, "PYTHONPATH": os.pathsep.join(path)} if path else env
        return subprocess.run([py, "-B" if path else "-IB", entry, *extra],
                              input=stdin, cwd=pkg, env=settings, capture_output=True, timeout=timeout)

    try:
        if case.get("arms"):
            status = "PASS"
            for arm in case["arms"]:
                proc = run(args.default_python, arm["entry"], [vals[arm["site"]]])
                if proc.returncode:
                    return "FAIL_execution", proc.stderr.decode(errors="replace")[-1600:]
                outcome = expect(case, proc.stdout, (archive / arm["expected"]).read_bytes(), policy)
                if outcome == "FAIL_divergence":
                    return outcome, arm["expected"]
                if outcome == "PASS_stable":
                    status = outcome
        else:
            stdin = None
            if case["mode"] == "producer-default" or case.get("producer"):
                producer_py = args.system_python if case.get("producer_mode") == "system" else args.default_python
                producer = run(producer_py, case.get("producer") or "producer.py")
                if producer.returncode:
                    return "FAIL_producer", producer.stderr.decode(errors="replace")[-1600:]
                stdin = producer.stdout
            py = args.default_python if case["mode"] == "default" else args.system_python
            proc = run(py, case.get("entry", "check.py"), stdin=stdin, extra=params)
            if proc.returncode:
                return "FAIL_execution", proc.stderr.decode(errors="replace")[-1600:]
            name = case.get("expected", "result.json")
            status = expect(case, proc.stdout, (archive / name).read_bytes(), policy)
            if status == "FAIL_divergence":
                return status, name
    except subprocess.TimeoutExpired:
        return "FAIL_runtime", f"timed out after {timeout} seconds"
    except FileNotFoundError as error:
        return "FAIL_runtime", str(error)
    for name in case.get("exact_generated", []):
        if not (pkg / name).is_file() or digest(pkg / name) != digest(archive / name):
            return "FAIL_generated", name
    return status, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--default-python", default=sys.executable)
    parser.add_argument("--system-python", default="/usr/bin/python3")
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--prior-root", type=Path, action="append", default=[])
    parser.add_argument("--include-prior", action="store_true")
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--zoneinfo", type=Path, default=ROOT.parent.parent / "zoneinfo")
    parser.add_argument("--timeout", type=int, help="override each producer's timeout in seconds")
    parser.add_argument("--json", action="store_true", help="write JSON Lines instead of status TSV")
    args = parser.parse_intermixed_args()
    if args.timeout is not None and args.timeout < 1:
        parser.error("--timeout must be positive")
    def bindings(path):
        content = read(path)
        if not isinstance(content, dict) or any(
            not isinstance(value, str) or not Path(value).is_absolute() for value in content.values()
        ):
            parser.error("input bindings must map role names to absolute paths")
        return content

    local = bindings(args.inputs)
    runtime = os.environ.get("OBSEQ_RUNTIME_BINDINGS")
    receipts = ROOT.parent / "submission-e-series-native-evidence"
    bundled = {
        "Q39_REFERENCE": str(receipts / "e1/q39-retry-reference.json"),
        "XLSX_SELECTION": str(receipts / "e4-workbook/per_file.csv"),
    }
    inputs = bundled | (bindings(Path(runtime)) if runtime else {}) | local
    if args.scratch:
        args.scratch.mkdir(parents=True, exist_ok=True)
        args.scratch = args.scratch.resolve()
    policy = read(ROOT / "SEMANTIC-PROJECTIONS.json")
    role_environments = read(ROOT / "INPUT-ENVIRONMENT.json")
    pins = read(ROOT / "BASE-PINS.json")["roots"]
    approved = {entry["manifest_sha256"] for entry in pins.values()}
    for path in args.prior_root:
        if not (path / "MANIFEST.json").is_file() or digest(path / "MANIFEST.json") not in approved:
            parser.error(f"prior manifest pin mismatch: {path}")
    cases = read(ROOT / "MANIFEST.json")["cases"]
    prior = []
    for revision in range(5, 10):
        name = f"extension-{revision}"
        file = ROOT / f"BASE-{revision}.json"
        if digest(file) != pins[name]["manifest_sha256"]:
            parser.error(f"baseline manifest pin mismatch: {name}")
        prior.extend(read(file)["cases"])
    if args.include_prior or set(args.ids).intersection(row["case_id"] for row in prior):
        cases = prior + cases
    if unknown := set(args.ids).difference(row["case_id"] for row in cases):
        parser.error(f"unknown cases: {', '.join(sorted(unknown))}")
    roots = [ROOT, *args.prior_root]
    failed = False
    for case in cases:
        name = case["case_id"]
        if args.ids and name not in args.ids:
            continue
        case = {**case, "input_environment": role_environments.get(name, {})}
        archive = next((r / "packages" / name for r in roots if (r / "packages" / name).is_dir()), None)
        with TemporaryDirectory(prefix="obseq-native-", dir=args.scratch) as scratch:
            status, detail = execute(case, archive, inputs, Path(scratch), args, policy) if archive else (
                "FAIL_package_root", name)
        row = {"id": name, "kind": case["kind"], "status": status}
        if status == "NA_input_binding":
            row["missing_input_roles"] = detail
            row["reason"] = f"NA (missing optional input role: {', '.join(detail)})"
        elif detail:
            row["reason"] = detail
        if args.json:
            print(json.dumps(row), flush=True)
        else:
            print(f"{name}\t{case['kind']}\t{status}", flush=True)
            if "reason" in row:
                print(row["reason"], file=sys.stderr)
        failed |= status not in PASS
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
