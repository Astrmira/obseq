"""Materialize the SHA-pinned 100 ClickBench source partitions on request."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile
from urllib.request import urlopen


MANIFEST = Path(__file__).resolve().parent / "evidence/pvldb-a7-typed-candidates/FULL-ACQUISITION.json"
BASE = "https://datasets.clickhouse.com/hits_compatible/athena_partitioned"


def verify(path, receipt):
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if path.stat().st_size != receipt["bytes"] or digest != receipt["sha256"]:
        raise ValueError(f"ClickBench publisher partition mismatch: {path}")


def acquire(target, receipt, verify_only):
    if target.exists() or verify_only:
        verify(target, receipt)
        return
    with NamedTemporaryFile(dir=target.parent, prefix=target.stem + "-", delete=False) as output:
        temp = Path(output.name)
        try:
            with urlopen(f"{BASE}/{target.name}") as download:
                shutil.copyfileobj(download, output)
        except BaseException:
            output.close()
            temp.unlink()
            raise
    try:
        verify(temp, receipt)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("store", type=Path)
    parser.add_argument("--part", type=int, action="append")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    receipt = {item["part"]: item for item in json.loads(MANIFEST.read_bytes())}
    if set(receipt) != set(range(100)):
        raise ValueError("ClickBench manifest changed")
    parts = args.part if args.part is not None else sorted(receipt)
    if set(parts) - receipt.keys():
        parser.error("part has no pinned source")
    if not args.verify_only:
        args.store.mkdir(parents=True, exist_ok=True)
    for part in parts:
        acquire(args.store / f"hits_{part}.parquet", receipt[part], args.verify_only)
        print(f"verified ClickBench partition {part}", flush=True)


if __name__ == "__main__":
    main()
