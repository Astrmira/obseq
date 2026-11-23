"""Reproduce the timing summary using the published path-free input provenance."""

from collections import defaultdict
import json
from pathlib import Path
from statistics import median, quantiles


def summarize(provenance, raw):
    config = json.loads(provenance.read_bytes())
    rows = [json.loads(line) for line in raw.read_bytes().splitlines()]
    seen, groups = set(), defaultdict(list)
    failures = []
    metrics = ["producer_ns", "validator_ns", "compile_ns", "candidate_ns", "staged_check_ns",
               "e2e_worker_peak_rss_kib", "staged_worker_peak_rss_kib"]
    for row in rows:
        key = row["suite"], row["query"], row["repeat"]
        if key in seen or row["config_sha256"] != config["original_config_sha256"]:
            raise ValueError(f"Duplicate worker or wrong frozen input binding: {key}")
        seen.add(key)
        if row["status"] != "ok":
            failures.append(row)
            continue
        for stage in ("validator", "compile", "candidate", "staged_check"):
            row[f"{stage}_over_producer"] = row[f"{stage}_ns"] / row["producer_ns"]
        groups[key[:2]].append(row)
    expected = {(suite, w["query"], rep) for suite, windows in config["windows"].items()
                for w in windows for rep in range(config["repeats"])}
    if seen != expected:
        raise ValueError("The published timing roster differs from the frozen full 116-window roster")
    metrics += [f"{stage}_over_producer" for stage in ("validator", "compile", "candidate", "staged_check")]
    queries = []
    for suite, windows in config["windows"].items():
        for window in windows:
            workers = groups[suite, window["query"]]
            if len(workers) == config["repeats"]:
                if any(row["candidate_rows"] != window["candidate_rows"] for row in workers):
                    raise ValueError(f"Candidate count differs from its census for {suite}/{window['query']}")
                queries.append({"suite": suite, **window,
                                **{name: median(row[name] for row in workers) for name in metrics}})
    distribution = {}
    for name in metrics:
        values = [query[name] for query in queries]
        if len(values) > 1:
            distribution[name] = {"median": median(values), "p90": quantiles(values, n=10, method="inclusive")[8],
                                  "max": max(values)}
    return {"workers": len(rows), "expected_workers": len(expected), "complete_windows": len(queries),
            "failures": failures, "distribution": distribution,
            "slowest_validator": sorted(queries, key=lambda q: q["validator_ns"], reverse=True)[:3],
            "largest_candidate": max(queries, key=lambda q: q["candidate_rows"], default=None),
            "largest_boundary_peer_group": max(queries, key=lambda q: max(q["lower_peers"] or 0,
                                                                         q["upper_peers"] or 0), default=None),
            "per_query": queries}


if __name__ == "__main__":
    packet = Path(__file__).resolve().parent
    print(json.dumps(summarize(packet / "AST-PROVENANCE.json", packet / "AST-RAW.jsonl"), indent=2, sort_keys=True))
