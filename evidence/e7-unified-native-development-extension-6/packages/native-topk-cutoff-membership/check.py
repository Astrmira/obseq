"""Native cutoff counts + exact provenance; independent Arrow source reference."""
from pathlib import Path
from hashlib import file_digest
from datetime import datetime
import argparse, csv, json, os, random, sys, time
import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
COL = "tpep_pickup_datetime"
POCH = datetime(1970, 1, 1)
KS = (32, 1024)


def digest(p):
    with p.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def ledger(name):
    return {n: h for h, n in (l.split() for l in (ROOT / name).read_text().splitlines())}


def micros(t):
    d = t - POCH
    return (86400*d.days+d.seconds)*10**6+d.microseconds


def db():
    return duckdb.connect(config={"threads": "1", "memory_limit": "192MB"})


def rerun(c, src, lo, hi, k, tie=""):
    return c.execute(f"""
        SELECT file_row_number, epoch_us({COL})
        FROM read_parquet(?, file_row_number=true)
        WHERE {COL} >= ? AND {COL} < ?
        ORDER BY {COL} DESC {tie}
        LIMIT {k}
    """, [src, lo, hi]).fetchall()


def guard(c, src, lo, hi, k, can, loose=False):
    """Exact except for the deliberately incorrect 'loose' control."""
    if not 0 <= len(can) <= k or len({i for i, _ in can}) != len(can):
        return False
    if any(type(i) is not int or i < 0 or i >= 2**63 or
           type(x) is not int or not micros(lo) <= x < micros(hi)
           for i,x in can):
        return False
    if any(x < y for (_,x),(_,y) in zip(can,can[1:])):
        return False
    if can:
        ids = ",".join(str(i) for i,_ in can)
        observed = c.execute(f"""
            SELECT file_row_number, epoch_us({COL})
            FROM read_parquet(?, file_row_number=true)
            WHERE file_row_number IN ({ids}) AND {COL} >= ? AND {COL} < ?
        """, [src, lo, hi]).fetchall()
        if set(observed) != set(can):
            return False
    if len(can) < k:
        n, = c.execute(f"""SELECT COUNT(*) FROM read_parquet(?)
            WHERE {COL} >= ? AND {COL} < ?""",[src,lo,hi]).fetchone()
        return n == len(can)
    if k == 0:
        return True
    t = can[-1][1]
    a, = c.execute(f"""SELECT COUNT(*) FROM read_parquet(?)
        WHERE {COL} > make_timestamp(?) AND {COL} < ?""",[src,t,hi]).fetchone()
    return a < k if loose else a == sum(x > t for _, x in can)


class Ref:
    def __init__(self, path, lo, hi):
        p = pq.ParquetFile(path)
        a = p.read(columns=[COL]).column(0)
        assert a.type == pa.timestamp("us")
        self.ts = np.concatenate([
            b.cast(pa.int64()).fill_null(-2**63).to_numpy() for b in a.chunks
        ])
        self.n = p.metadata.num_rows
        assert self.n == len(self.ts)
        self.lo = micros(lo)
        self.hi = micros(hi)
        self.eligible = np.count_nonzero((self.ts >= self.lo) & (self.ts < self.hi))

    def check(self, k, can):
        if len(can) != min(k,self.eligible) or len({i for i,x in can}) != len(can):
            return False
        if any(x < y for (_,x),(_,y) in zip(can,can[1:])):
            return False
        if any(not 0 <= i < len(self.ts) or self.ts[i] != x
               or not self.lo <= x < self.hi for i,x in can):
            return False
        if not can:
            return True
        t = can[-1][1]
        strict = {int(i) for i in np.flatnonzero((self.ts > t) & (self.ts < self.hi))}
        return strict <= {i for i,x in can}

    def peers(self, t):
        return np.flatnonzero(self.ts == t)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("inputs", type=Path)
    p.add_argument("--timing", action="store_true")
    a = p.parse_args()
    if duckdb.__version__ != "2.0.1" or pa.__version__ != "26.0.1":
        raise RuntimeError("pinned DuckDB 2.0.1 and PyArrow 26.0.1 required")
    for name,want in ledger("PREEXECUTION.sha256").items():
        assert digest(ROOT / name) == want, name
    if hasattr(os,"sched_getaffinity"):
        cpu = min(os.sched_getaffinity(0))
        os.sched_setaffinity(0,{cpu})
    results = []
    rng = random.Random(1741)
    if a.timing:
        writer = csv.writer(sys.stdout,lineterminator="\n")
        writer.writerow(("file","k","method","wall_ns"))
    for name,want in ledger("INPUTS.sha256").items():
        path = a.inputs / name
        assert digest(path) == want, name
        y = int(name[:4])
        lo, hi = datetime(y,3,1), datetime(y,4,1)
        src = str(path)
        if a.timing:
            for k in KS:
                with db() as c:
                    can = rerun(c,src,lo,hi,k,", file_row_number ASC")
                    assert guard(c,src,lo,hi,k,can)
                arms = ["topn", "guard"]*7
                rng.shuffle(arms)
                for method in arms:
                    with db() as worker:
                        start = time.perf_counter_ns()
                        output = (rerun(worker,src,lo,hi,k)
                                  if method=="topn" else guard(worker,src,lo,hi,k,can))
                        elapsed = time.perf_counter_ns()-start
                        assert (guard(worker,src,lo,hi,k,output) if method=="topn" else output)
                    writer.writerow((name,k,method,elapsed))
                    sys.stdout.flush()
            continue
        ref = Ref(src, lo, hi)
        with db() as c:
            for k in KS:
                lower = rerun(c,src,lo,hi,k,", file_row_number ASC")
                higher = rerun(c,src,lo,hi,k,", file_row_number DESC")
                can = [(i,x) for i,x in lower]
                t = can[-1][1]
                assert len(can) == k and ref.eligible >= k
                countstrict = sum(x > t for _,x in can)
                peers = ref.peers(t)
                ids = {i for i,x in can}
                worse = int(np.flatnonzero((ref.ts >= ref.lo) & (ref.ts < t))[0])
                assert worse not in ids
                reordering = list(can)
                gap = next(j for j in range(k-1) if can[j][1] > can[j+1][1])
                reordering[gap], reordering[gap+1] = reordering[gap+1], reordering[gap]
                cases = [
                    ("legal_ascending_peer_id",True,lower),
                    ("legal_descending_peer_id",True,higher),
                    ("native_default_order",True,rerun(c,src,lo,hi,k)),
                    ("duplicate_id", False, can[:-1]+[can[-2]]),
                    ("wrong_score_on_real_id", False, [(can[0][0],can[0][1]+1)]+can[1:]),
                    ("outside_file_id", False, can[:-1]+[(ref.n,can[-1][1])]),
                    ("non_monotone", False, reordering),
                    ("displaced_by_below_cutoff", False, can[1:]+[(worse,int(ref.ts[worse]))]),
                    ("too_short", False, can[:-1]),
                ]
                peer = next((int(i) for i in peers if int(i) not in ids),None)
                if peer is not None and countstrict:
                    cases.append(("missing_strict_winner_same_cutoff",False,can[1:]+[(peer,t)]))
                ds = []
                for id_, good, out in cases:
                    native = guard(c,src,lo,hi,k,out)
                    independent = ref.check(k,out)
                    assert native == independent == good, (name,k,id_,native,independent)
                    looser = guard(c,src,lo,hi,k,out,loose=True)
                    if id_ == "missing_strict_winner_same_cutoff":
                        assert looser is True
                    ds.append([id_, native, looser])
                assert guard(c,src,lo,hi,0,[])
                assert not guard(c,src,lo,hi,1,[])
                # Verified short-result behavior on an empty half-open interval.
                assert guard(c,src,lo,lo,1,[])
                assert len(set(lower) ^ set(higher)) % 2 == 0
                results.append(dict(file=name,file_rows=ref.n,eligible=int(ref.eligible),
                    k=k,cutoff_us=t, strictly_above=countstrict, cutoff_peers=len(peers),
                    peer_choices_symmetric_difference=len(set(lower) ^ set(higher)), cases=ds))
        del ref
    if not a.timing:
        print(json.dumps(results,indent=2))


if __name__ == "__main__":
    main()
