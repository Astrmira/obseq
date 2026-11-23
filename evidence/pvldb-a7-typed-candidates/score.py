"""Score two ClickBench families against exact evidence from the full source."""

import argparse
from collections import Counter, defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import runpy

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


CUTOFF = 1_372_708_801  # Pinned timestamp from the earlier footer/chunk replay.
E2_SHA = "bf7bc7a593debbf7e42559c4acbc77ab01543c58323ed9197ba617017c02edc6"


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def candidate(directory, manifest, query, threads):
    receipt = manifest[query, threads]
    payload = (directory / receipt["candidate"]).read_bytes()
    if sha(payload) != receipt["candidate_sha256"]:
        raise ValueError("candidate payload changed")
    table = pa.ipc.open_file(payload).read_all()
    return list(map(list, zip(*(column.to_pylist() for column in table.columns)))), table.schema, sha(payload)


def scan(shards, keys):
    counts, early = Counter(), defaultdict(Counter)
    population, eligible, empty_at_boundary = 0, 0, 0
    ids = sorted({uid for uid, _ in keys if uid is not None})
    for path in shards:
        for batch in pq.ParquetFile(path).iter_batches(columns=["UserID", "SearchPhrase", "EventTime"]):
            user, text, when = batch.columns
            population += batch.num_rows
            selection = pc.is_in(user, value_set=pa.array(ids, type=user.type))
            if any(uid is None for uid, _ in keys):
                selection = pc.or_(selection, pc.is_null(user))
            for uid, phrase in zip(pc.filter(user, selection).to_pylist(), pc.filter(text, selection).to_pylist()):
                pair = uid, decode(phrase)
                if pair in keys:
                    counts[pair] += 1
            empty = pa.scalar("" if pa.types.is_string(text.type) else b"", type=text.type)
            valid = pc.and_(pc.fill_null(pc.not_equal(text, empty), False), pc.is_valid(when))
            eligible += pc.sum(valid).as_py()
            at_cutoff = pc.fill_null(pc.equal(when, CUTOFF), False)
            empty_at_boundary += pc.sum(pc.and_(at_cutoff, pc.fill_null(pc.equal(text, empty), False))).as_py()
            first = pc.and_(valid, pc.fill_null(pc.less_equal(when, CUTOFF), False))
            for timestamp, phrase in zip(pc.filter(when, first).to_pylist(), pc.filter(text, first).to_pylist()):
                early[timestamp][decode(phrase)] += 1
    return counts, early, population, eligible, empty_at_boundary


def decode(value):
    return value.decode("utf-8") if isinstance(value, bytes) else value


def q18_mutants(reference):
    arms = {}
    for index, (uid, _, _) in enumerate(reference):
        if uid is not None and uid < 2**63 - 1:
            rows = [r.copy() for r in reference]
            rows[index][0] += 1
            arms["M1_integer_key_plus_one"] = rows
            break
    for index, (uid, _, _) in enumerate(reference):
        if uid is not None and (rounded := int(float(uid))) != uid and -(2**63) <= rounded < 2**63:
            rows = [r.copy() for r in reference]
            rows[index][0] = rounded
            arms["M6_id_float64_roundtrip"] = rows
            break
    for left, right in itertools.combinations(range(len(reference)), 2):
        if reference[left][2] != reference[right][2]:
            rows = [r.copy() for r in reference]
            rows[left][2], rows[right][2] = rows[right][2], rows[left][2]
            arms["M2_swap_group_counts"] = rows
            break
    return arms


def validate_q18(rows, counts):
    keys = [(uid, phrase) for uid, phrase, _ in rows]
    return len(rows) == len(set(keys)) == 10 and all(counts[key] == row[2] > 0 for key, row in zip(keys, rows))


def validate_q25(rows, early):
    position = 0
    values = [value for value, in rows]
    for stamp, group in sorted(early.items()):
        if stamp == CUTOFF:
            return len(values) == 10 and Counter(values[position:]) <= group
        end = position + group.total()
        if Counter(values[position:end]) != group:
            return False
        position = end
    raise ValueError("missing exact cutoff")


def encoded_sha(rows, schema):
    columns = [pa.array(values, type=field.type) for field, values in zip(schema, zip(*rows))]
    table = pa.Table.from_arrays(columns, schema=schema)
    output = pa.BufferOutputStream()
    with pa.ipc.new_file(output, schema) as writer:
        writer.write_table(table)
    return sha(output.getvalue().to_pybytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("acquisition", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("frozen_runner", type=Path)
    parser.add_argument("observer_runner", type=Path)
    parser.add_argument("e2", type=Path)
    parser.add_argument("stores", nargs=2, type=Path)
    parser.add_argument("--pairs", type=Path, help="write comparator inputs to private scratch")
    args = parser.parse_args()
    if pa.__version__ != "22.0.0" or sha(args.e2.read_bytes()) != E2_SHA:
        raise ValueError("arrow version or E2 observer mismatch")
    frozen = runpy.run_path(str(args.frozen_runner))
    shards = frozen["load_shards"](args.acquisition, args.stores)
    upstream = json.loads((args.results / "RESULT.json").read_bytes())
    acquisition_sha = sha(args.acquisition.read_bytes())
    if upstream["acquisition_sha256"] != acquisition_sha:
        raise ValueError("result manifest bound to another input")
    directory = args.results / "private-candidates"
    manifest = {(r["query"], r["threads"]): r for r in map(json.loads, (directory / "manifest.jsonl").read_bytes().splitlines())}
    native = {(query, threads): candidate(directory, manifest, query, threads)
              for query in (18, 25) for threads in (1, 8)}
    mutations = q18_mutants(native[18, 8][0])
    keys = {(uid, phrase) for rows in [native[18, 1][0], native[18, 8][0], *mutations.values()]
            for uid, phrase, _ in rows}
    counts, early, population, eligible, empty = scan(shards, keys)
    mandatory = sum(group.total() for stamp, group in early.items() if stamp < CUTOFF)
    peers = early[CUTOFF]
    upstream_q25 = upstream["two_independent_family_checks"]
    if (population, eligible, mandatory, peers.total(), len(peers)) != (
        upstream["source_rows"], upstream_q25["q25_qualifying_rows"], upstream_q25["q25_mandatory_rows"],
        upstream_q25["q25_boundary_rows"], upstream_q25["q25_boundary_distinct_phrases"],
    ):
        raise ValueError("full input reference diverged from producer receipt")

    test = runpy.run_path(str(args.observer_runner))["observer"](args.e2)
    observations = []
    pairs = []
    applicable = {"M1_integer_key_plus_one", "M2_swap_group_counts", "M6_id_float64_roundtrip"}
    uninstantiated = {18: sorted(applicable - mutations.keys()), 25: []}
    for query in (18, 25):
        reference, schema, reference_sha = native[query, 8]
        observed, native_schema, observed_sha = native[query, 1]
        if schema != native_schema:
            raise ValueError("native thread arms use different Arrow schemas")
        arms = [("native_1_thread", observed, observed_sha, True)]
        if query == 18:
            check = lambda rows: validate_q18(rows, counts)
            arms.extend((kind, rows, encoded_sha(rows, schema), False) for kind, rows in mutations.items()
                        if not check(rows))
            uninstantiated[18].extend(kind for kind, rows in mutations.items() if check(rows))
        else:
            check = lambda rows: validate_q25(rows, early)
            omitted = sorted((peers - Counter(value for value, in reference[mandatory:])).keys())
            alternate = [[*row] for row in reference]
            alternate[mandatory][0] = omitted[0]
            arms.append(("derived_legal_boundary_alternate", alternate, encoded_sha(alternate, schema), True))
            if empty:
                invalid = [row.copy() for row in reference]
                invalid[mandatory][0] = ""
                arms.append(("M3_same_score_ineligible_empty_phrase", invalid, encoded_sha(invalid, schema), False))
            else:
                uninstantiated[25].append("M3_same_score_ineligible_empty_phrase")
        if not check(reference):
            raise ValueError(f"native reference outside Q{query} family")
        for name, rows, output_sha, legal in arms:
            if check(rows) != legal:
                raise ValueError(f"Q{query} {name} legality inconsistent with source")
            observations.append({"query": query, "arm": name, "legal": legal,
                                 "candidate_sha256": output_sha,
                                 "observers": test(reference, rows, reference_sha, output_sha, None)})
            if args.pairs:
                pairs.append(["benchmark", f"clickbench-{query}", name, legal,
                              list(map(list, reference)), list(map(list, rows))])
    print(json.dumps({"acquisition_sha256": acquisition_sha, "e2_sha256": E2_SHA,
                      "reference_threads": 8, "population": population,
                      "q25_cutoff": {"unix_seconds": CUTOFF, "empty_phrases_at_cutoff": empty,
                                    "mandatory_rows": mandatory, "peers": peers.total(), "slots": 10 - mandatory},
                      "uninstantiated": uninstantiated, "observations": observations}, indent=2, sort_keys=True))
    if args.pairs:
        args.pairs.write_text(json.dumps(pairs, allow_nan=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
