"""Acquire the original ClickBench shards, bound to the frozen footer audit."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import struct
import time
from urllib.request import Request, urlopen


PREFIX = (
    "https://clickhouse-public-datasets.s3.eu-central-1.amazonaws.com/"
    "hits_compatible/athena_partitioned"
)


def validate(path, record):
    if path.stat().st_size != record["object_bytes"]:
        raise ValueError("publisher object length mismatch")
    with path.open("rb") as source:
        if source.read(4) != b"PAR1":
            raise ValueError("missing Parquet header")
        source.seek(-8, 2)
        length, magic = struct.unpack("<I4s", source.read(8))
        if magic != b"PAR1" or length != record["footer_payload_bytes"]:
            raise ValueError("publisher footer framing mismatch")
        source.seek(-(8 + length), 2)
        if hashlib.sha256(source.read(length + 8)).hexdigest() != record["footer_sha256"]:
            raise ValueError("publisher footer digest mismatch")
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def fetch(record, directory):
    name = f"hits_{record['part']}.parquet"
    path = directory / name
    temporary = directory / (name + ".part")
    if path.is_file():
        return {"part": record["part"], "bytes": record["object_bytes"],
                "etag": record["etag"], "sha256": validate(path, record)}
    for attempt in range(1, 4):
        try:
            size = record["object_bytes"]
            offset = temporary.stat().st_size if temporary.is_file() else 0
            if offset > size:
                raise ValueError("partial file is longer than the source object")
            if offset < size:
                headers = {"If-Match": record["etag"]}
                if offset:
                    headers["Range"] = f"bytes={offset}-"
                request = Request(f"{PREFIX}/{name}", headers=headers)
                with urlopen(request, timeout=45) as response:
                    if response.headers["ETag"] != record["etag"]:
                        raise ValueError("publisher ETag mismatch")
                    if offset and (
                        response.status != 206
                        or response.headers["Content-Range"] != f"bytes {offset}-{size - 1}/{size}"
                    ):
                        raise ValueError("publisher resume range mismatch")
                    with temporary.open("ab" if offset else "wb") as out:
                        shutil.copyfileobj(response, out, length=1 << 20)
            digest = validate(temporary, record)
            temporary.replace(path)
            print(f"{name} {record['object_bytes']} bytes verified", flush=True)
            return {"part": record["part"], "bytes": record["object_bytes"],
                    "etag": record["etag"], "sha256": digest}
        except (OSError, ValueError) as exc:
            print(f"{name} attempt {attempt}: {type(exc).__name__} {exc}", flush=True)
            if attempt == 3:
                raise
            time.sleep(attempt * 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("first_store", type=Path)
    parser.add_argument("second_store", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--split", type=int, default=41)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    records = sorted(json.loads(args.manifest.read_bytes()), key=lambda row: row["part"])
    if [row["part"] for row in records] != list(range(100)):
        raise ValueError("requires the pinned 100-shard manifest")
    stores = [args.first_store, args.second_store]
    for store, subset in zip(stores, [records[:args.split], records[args.split:]]):
        store.mkdir(parents=True, exist_ok=True)
        need = sum(
            record["object_bytes"] - max(
                ((store / f"hits_{record['part']}.parquet{suffix}").stat().st_size
                 for suffix in ("", ".part")
                 if (store / f"hits_{record['part']}.parquet{suffix}").is_file()),
                default=0,
            )
            for record in subset
        )
        if shutil.disk_usage(store).free < need:
            raise ValueError(f"{store} has insufficient free space for {need} bytes")
    with ThreadPoolExecutor(max_workers=args.workers) as workers:
        receipt = list(workers.map(
            lambda row: fetch(row, stores[row["part"] >= args.split]), records
        ))
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
