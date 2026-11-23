"""Check native grouped ClickBench windows against an independent Parquet scan."""

import argparse
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import runpy

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


QUERIES = (31, 32, 33, 39, 40, 41, 42)
OFFSETS = {31: 0, 32: 0, 33: 0, 39: 1000, 40: 1000, 41: 100, 42: 10000}
KEY_WIDTH = {31: 2, 32: 2, 33: 2, 39: 1, 40: 5, 41: 2, 42: 2}
EPOCH = date(1970, 1, 1)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rows(table):
    return list(zip(*(column.to_pylist() for column in table.columns)))


def normalize_key(value):
    if isinstance(value, str):
        return value.encode()
    if isinstance(value, date):
        return (value - EPOCH).days
    return value


def key(query, row):
    return tuple(map(normalize_key, row[:KEY_WIDTH[query]]))


def candidate(arm, directory):
    path = directory / arm["candidate"]
    payload = path.read_bytes()
    if sha(payload) != arm["candidate_sha256"]:
        raise ValueError(f"candidate changed: {path.name}")
    table = pa.ipc.open_file(payload).read_all()
    if (table.num_rows, table.num_columns) != (arm["rows"], arm["columns"]):
        raise ValueError(f"candidate shape changed: {path.name}")
    return rows(table), table.schema


def mutants(query, original):
    variants = {}
    width = KEY_WIDTH[query]
    for index, row in enumerate(original):
        for col, value in enumerate(row[:width]):
            if type(value) is int and value < 2**63 - 1:
                variants["M1_integer_key_plus_one"] = changed(original, index, col, value + 1)
                break
        if variants:
            break
    for i, j in itertools.combinations(range(len(original)), 2):
        if original[i][width:] != original[j][width:]:
            swapped = original.copy()
            swapped[i] = original[i][:width] + original[j][width:]
            swapped[j] = original[j][:width] + original[i][width:]
            variants["M2_swap_nonkeys"] = swapped
            break
    if query in (32, 33):
        for index, row in enumerate(original):
            rounded = int(float(row[0]))
            if rounded != row[0] and -(2**63) <= rounded < 2**63:
                variants["M6_id_float64_roundtrip"] = changed(original, index, 0, rounded)
                break
    if query in (31, 32, 33):
        for index, row in enumerate(original):
            old = row[-1]
            if type(old) is float and math.isfinite(old) and old:
                new = math.nextafter(math.nextafter(old, math.inf), math.inf)
                if math.isclose(old, new, rel_tol=1e-5):
                    variants["M5_two_ulp_width"] = changed(original, index, len(row)-1, new)
                    break
    for index, row in enumerate(original):
        if None in row[:width]:
            variants["M7_drop_null_group"] = original[:index] + original[index+1:]
            break
    return variants


def changed(original, index, column, value):
    result = original.copy()
    row = result[index]
    result[index] = row[:column] + (value,) + row[column+1:]
    return result


def mask_in(column, values):
    typed = pa.array(sorted(v for v in values if v is not None
                            and pa.scalar(v).as_py() == v
                            and np.iinfo(column.type.to_pandas_dtype()).min <= v <= np.iinfo(column.type.to_pandas_dtype()).max),
                     type=column.type)
    match = pc.is_in(column, value_set=typed)
    return pc.or_(match, pc.is_null(column)) if None in values else match


class WideScan:
    """Collect every WatchID occurrence, plus exact sums for the claimed keys."""

    NULL_IP = 2**32

    def __init__(self, population, keys):
        self.watch = np.empty(population, dtype=np.int64)
        self.client = np.empty(population, dtype=np.int64)
        self.eligible = np.empty(population, dtype=np.bool_)
        self.position = 0
        self.engine_codes = []
        self.keys = keys
        self.column_keys = {q: tuple({pair[i] for pair in pairs} for i in (0, 1))
                            for q, pairs in keys.items() if q in (31, 32, 33)}
        self.chosen = {q: defaultdict(lambda: [0, 0, 0, 0, 0]) for q in (31, 32, 33)}

    def add(self, batch):
        watch, ip, refresh, width, phrase, engine = batch.columns
        stop = self.position + batch.num_rows
        if watch.null_count:
            raise ValueError("WatchID duplicate census needs nonnull source IDs")
        self.watch[self.position:stop] = watch.to_numpy()
        ip_codes = pc.fill_null(pc.add(pc.cast(ip, pa.int64()), 2**31), self.NULL_IP).to_numpy()
        self.client[self.position:stop] = ip_codes
        eligible = pc.fill_null(pc.not_equal(phrase, b""), False)
        yes = eligible.to_numpy(zero_copy_only=False)
        self.eligible[self.position:stop] = yes
        self.position = stop
        engine_codes = pc.fill_null(pc.add(pc.cast(engine, pa.int64()), 2**15), 2**16).to_numpy()
        self.engine_codes.append((engine_codes[yes] << 33) + ip_codes[yes])
        for q, column in ((31, engine), (32, watch), (33, watch)):
            keys_a, keys_b = self.column_keys[q]
            admitted = pc.and_(mask_in(column, keys_a), mask_in(ip, keys_b))
            if q != 33:
                admitted = pc.and_(admitted, eligible)
            fields = [pc.filter(c, admitted).to_pylist() for c in (column, ip, refresh, width)]
            for k1, k2, r, w in zip(*fields):
                pair = (k1, k2)
                if pair not in self.keys[q]:
                    continue
                values = self.chosen[q][pair]
                values[0] += 1
                if r is not None:
                    values[1] += r
                    values[2] += 1
                if w is not None:
                    values[3] += w
                    values[4] += 1

    def finish(self):
        if self.position != len(self.watch):
            raise ValueError("incomplete wide scan")
        _, engine_sizes = np.unique(np.concatenate(self.engine_codes), return_counts=True)
        scores, n = np.unique(engine_sizes, return_counts=True)
        hist = {31: Counter(dict(zip(map(int, scores), map(int, n)))),
                32: Counter({1: int(self.eligible.sum())}), 33: Counter({1: self.position})}
        order = np.argsort(self.watch)
        sorted_watch = self.watch[order]
        repeat = np.flatnonzero(sorted_watch[1:] == sorted_watch[:-1])
        affected = order[np.union1d(repeat, repeat + 1)]
        repeated = Counter((int(self.watch[i]), int(self.client[i])) for i in affected)
        repeated_eligible = Counter((int(self.watch[i]), int(self.client[i])) for i in affected if self.eligible[i])
        for q, groups in ((32, repeated_eligible), (33, repeated)):
            for size in groups.values():
                if size > 1:
                    hist[q][1] -= size
                    hist[q][size] += 1
        facts = {q: {k: (count, refresh if refresh_n else None,
                         float(Fraction(width, width_n)) if width_n else None)
                     for k, (count, refresh, refresh_n, width, width_n) in groups.items()}
                 for q, groups in self.chosen.items()}
        return hist, facts


NARROW = ("CounterID", "EventDate", "IsRefresh", "IsLink", "IsDownload", "URL",
          "TraficSourceID", "SearchEngineID", "AdvEngineID", "Referer", "URLHash",
          "RefererHash", "WindowClientWidth", "WindowClientHeight", "DontCountHits")


def common_filter(block):
    start = (date(2013, 7, 1) - EPOCH).days
    end = (date(2013, 7, 31) - EPOCH).days
    return pc.and_kleene(pc.and_kleene(pc.equal(block["CounterID"], 62), pc.equal(block["IsRefresh"], 0)),
                         pc.and_kleene(pc.greater_equal(block["EventDate"], start),
                                       pc.less_equal(block["EventDate"], end)))


def narrow_scan(shards):
    counts = {q: Counter() for q in (39, 40, 41, 42)}
    seen = 0
    for shard in shards:
        for batch in pq.ParquetFile(shard).iter_batches(columns=NARROW):
            seen += batch.num_rows
            source = dict(zip(batch.schema.names, batch.columns))
            include = common_filter(source)
            b = {name: pc.filter(source[name], include) for name in NARROW
                 if name not in ("CounterID", "IsRefresh")}
            q39 = pc.and_kleene(pc.not_equal(b["IsLink"], 0), pc.equal(b["IsDownload"], 0))
            counts[39].update((value,) for value in pc.filter(b["URL"], q39).to_pylist())
            has_source = pc.fill_null(pc.and_kleene(pc.equal(b["SearchEngineID"], 0),
                                                   pc.equal(b["AdvEngineID"], 0)), False)
            src = pc.if_else(has_source, b["Referer"], b"")
            counts[40].update(zip(*(b[name].to_pylist() for name in ("TraficSourceID", "SearchEngineID", "AdvEngineID")),
                                  src.to_pylist(), b["URL"].to_pylist()))
            q41 = pc.and_kleene(pc.is_in(b["TraficSourceID"], value_set=pa.array([-1, 6], type=pa.int16())),
                                pc.equal(b["RefererHash"], 3594120000172545465))
            counts[41].update(zip(*(pc.filter(b[name], q41).to_pylist() for name in ("URLHash", "EventDate"))))
            q42 = pc.and_kleene(pc.equal(b["DontCountHits"], 0), pc.equal(b["URLHash"], 2868770270353813622))
            counts[42].update(zip(*(pc.filter(b[name], q42).to_pylist() for name in ("WindowClientWidth", "WindowClientHeight"))))
    return {q: Counter(groups.values()) for q, groups in counts.items()}, {
        q: {k: (n,) for k, n in groups.items()} for q, groups in counts.items()
    }, seen


def window(hist, offset):
    count, end, answer = 0, offset + 10, []
    for score, peers in sorted(hist.items(), reverse=True):
        right = count + peers
        answer.extend([score] * max(0, min(end, right) - max(offset, count)))
        count = right
        if count >= end:
            break
    return answer


def check(query, candidate_rows, hist, groups):
    candidate_keys = [key(query, row) for row in candidate_rows]
    if len(candidate_keys) != len(set(candidate_keys)):
        return False
    width = KEY_WIDTH[query]
    if [row[width] for row in candidate_rows] != window(hist, OFFSETS[query]):
        return False
    return all(groups.get(k) == row[width:] for k, row in zip(candidate_keys, candidate_rows))


def carrier_copy(candidate_rows, schema):
    table = pa.Table.from_arrays([pa.array(col, type=field.type) for col, field in
                                  zip(zip(*candidate_rows), schema)], schema=schema)
    output = pa.BufferOutputStream()
    with pa.ipc.new_file(output, schema) as writer:
        writer.write_table(table)
    return sha(output.getvalue().to_pybytes())


def visible(candidate_rows):
    return [[int(value) if isinstance(value, Decimal) and value == value.to_integral_value()
             else value.isoformat() if isinstance(value, date) else value
             for value in row] for row in candidate_rows]


def main():
    p = argparse.ArgumentParser()
    for name in ("acquisition", "stock", "results", "frozen_runner", "a2_runner", "e2"):
        p.add_argument(name, type=Path)
    p.add_argument("stores", type=Path, nargs=2)
    p.add_argument("--pairs", type=Path, help="write comparator inputs to private scratch")
    a = p.parse_args()
    upstream = runpy.run_path(str(a.frozen_runner))
    stock, acquisition = a.stock.read_bytes(), a.acquisition.read_bytes()
    if pa.__version__ != "22.0.0" or sha(stock) != upstream["STOCK_SHA"]:
        raise ValueError("source SQL or Arrow runtime changed")
    source_lines = stock.decode().splitlines()
    shards = upstream["load_shards"](a.acquisition, a.stores)
    source_rows = upstream["POPULATION"]
    cutoffs = {r["query"]: r for r in map(json.loads, (a.results/"CUTOFFS.jsonl").read_bytes().splitlines())}
    private = a.results/"private-candidates"
    manifest = {(r["query"], r["threads"]): r for r in map(json.loads, (private/"manifest.jsonl").read_bytes().splitlines())}
    arms = {}
    for q in QUERIES:
        for threads in (8, 1):
            receipt = manifest[q, threads]
            if receipt["acquisition_sha256"] != sha(acquisition) or receipt["sql_sha256"] != sha(source_lines[q-1].encode()):
                raise ValueError("native receipt source identity mismatch")
            arms[q, threads] = candidate(receipt, private)
    variants = {q: mutants(q, arms[q, 8][0]) for q in QUERIES}
    claimed = {q: {key(q, row) for table in [arms[q, 8][0], arms[q, 1][0], *variants[q].values()]
                   for row in table} for q in (31, 32, 33)}
    wide = WideScan(source_rows, claimed)
    for shard in shards:
        for batch in pq.ParquetFile(shard).iter_batches(
            columns=["WatchID", "ClientIP", "IsRefresh", "ResolutionWidth", "SearchPhrase", "SearchEngineID"],
        ):
            wide.add(batch)
    hist, facts = wide.finish()
    other_hist, other_facts, seen = narrow_scan(shards)
    if seen != source_rows:
        raise ValueError("incomplete narrow scan")
    hist.update(other_hist)
    facts.update(other_facts)

    observe = runpy.run_path(str(a.a2_runner))["observer"](a.e2)
    result = {}
    pairs = []
    for q in QUERIES:
        census = cutoffs[q]
        if census["sql_sha256"] != sha(source_lines[q-1].encode()) or census["candidate_rows"] != hist[q].total():
            raise ValueError(f"Q{q} independent group count differs from frozen census")
        scores = window(hist[q], OFFSETS[q])
        if scores and (hist[q][scores[0]], hist[q][scores[-1]]) != (census["lower_peers"], census["upper_peers"]):
            raise ValueError(f"Q{q} independent boundary counts differ")
        old, schema = arms[q, 8]
        new, new_schema = arms[q, 1]
        native = {str(arm): check(q, rows, hist[q], facts[q]) for arm, rows in ((8, old), (1, new))}
        if schema != new_schema:
            raise ValueError(f"Q{q} native schemas differ")
        base_sha = manifest[q, 8]["candidate_sha256"]
        observations = [{"arm": "native_1_thread", "legal": native["1"],
                         "observers": observe(visible(old), visible(new), base_sha,
                                              manifest[q, 1]["candidate_sha256"], None)}]
        if a.pairs:
            pairs.append(["benchmark", f"clickbench-{q}", "native_1_thread", native["1"], visible(old), visible(new)])
        not_invalid = []
        for kind, changed_rows in variants[q].items():
            if check(q, changed_rows, hist[q], facts[q]):
                not_invalid.append(kind)
                continue
            try:
                mutant_sha = carrier_copy(changed_rows, schema)
            except (pa.ArrowInvalid, OverflowError):
                not_invalid.append(kind)
                continue
            observations.append({"arm": kind, "legal": False,
                                 "observers": observe(visible(old), visible(changed_rows), base_sha, mutant_sha, None)})
            if a.pairs:
                pairs.append(["benchmark", f"clickbench-{q}", kind, False, visible(old), visible(changed_rows)])
        result[str(q)] = {"native_membership": native, "offset": OFFSETS[q], "scores_in_window": scores,
                          "group_count": hist[q].total(), "lower_peers": census["lower_peers"],
                          "upper_peers": census["upper_peers"], "observations": observations,
                          "not_admitted_mutations": sorted(not_invalid)}
    print(json.dumps({"acquisition_sha256": sha(acquisition), "stock_sql_sha256": sha(stock),
                      "e2_sha256": sha(a.e2.read_bytes()), "source_rows": source_rows,
                      "queries": result}, indent=2, sort_keys=True))
    if not all(all(row["native_membership"].values()) for row in result.values()):
        raise SystemExit("some captured output failed its independent source check")
    if a.pairs:
        a.pairs.write_text(json.dumps(pairs, allow_nan=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
