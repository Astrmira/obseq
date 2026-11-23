"""Official ClickBench partition, exact integer oracle versus actual native casts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import duckdb
import pyarrow
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent
SHA="fa134fe101e68324e0de851146fda69624f5cbb707d387141d1c2a88a219a16d"
COLUMNS=("WatchID","UserID")


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def projected(v):
    if v is None or v==0:return v
    a=abs(v)
    shift=max(0,a.bit_length()-53)
    lo,rem=divmod(a,1<<shift)
    if 2*rem>(1<<shift) or (2*rem==(1<<shift) and lo%2):
        lo+=1
    return (lo<<shift) * (-1 if v<0 else 1)


def masses(l,r):
    return sum(n*r[k] for k,n in l.items())


def reference(path,col):
    c=[Counter(),Counter()]
    ix=0
    for batch in pq.ParquetFile(path).iter_batches(columns=[col]):
        for v in batch.column(0).to_pylist():
            c[ix%2][v]+=1
            ix+=1
    l,r=c
    cnt=l+r
    keys={k for k in cnt if k is not None}
    g=Counter(projected(k) for k in keys)
    counters=[Counter(),Counter()]
    for target, source in zip(counters,c):
        for k,n in source.items():target[projected(k)]+=n
    a,b=counters
    t=masses(l,r)
    both=masses(a,b)
    mixed=masses(l,b)
    kept=sum(n*r[k] for k,n in l.items() if projected(k)==k)
    assert both>=t and mixed>=kept
    return dict(population=ix, original_nulls=cnt[None], distinct=len(keys),
        keys_changed=sum(projected(k)!=k for k in keys),
        collided_exact_keys=sum(n for n in g.values() if n>1),
        collided_buckets=sum(n>1 for n in g.values()),
        exact_pairs=t+l[None]+r[None]+1,
        source_exact_nonnull_pairs=t-l[None]*r[None],
        both_false_pairs=both-t,both_lost_pairs=0,
        unilateral_false_pairs=mixed-kept,unilateral_lost_pairs=t-kept,
        authored_null_pairs_added=l[None]+r[None]+1)


def native(path,col,c):
    c.execute(f"""CREATE OR REPLACE TABLE x AS
        SELECT file_row_number%2 arm,{col}::BIGINT k
        FROM read_parquet(?,file_row_number=true)""",[path])
    def one(q):return c.execute(q).fetchone()
    n,nil = one("SELECT COUNT(*),count(*) FILTER (WHERE k IS NULL) FROM x")
    d = one("""WITH K AS (SELECT DISTINCT k FROM x WHERE k IS NOT NULL),
      G AS (SELECT k::DOUBLE AS f, COUNT(*) cnt,
         COUNT(*) FILTER (WHERE k <> (k::DOUBLE)::HUGEINT) changed FROM K GROUP BY f)
      SELECT coalesce(sum(cnt),0),coalesce(sum(changed),0),count(*) FILTER(WHERE cnt>1),
      coalesce(sum(cnt) FILTER(WHERE cnt>1),0) FROM G""")
    nil2 = one("SELECT coalesce(sum(1) FILTER(WHERE arm=0 AND k IS NULL),0)*coalesce(sum(1) FILTER(WHERE arm=1 AND k IS NULL),0) FROM x")[0]
    c.execute("""CREATE OR REPLACE TABLE m AS SELECT arm,k,count(*) n
        FROM (SELECT * FROM x UNION ALL SELECT 0 AS arm,NULL UNION ALL SELECT 1,NULL)
        GROUP BY arm,k""")
    def pairs(join):
        return one("""SELECT coalesce(sum(l.n::HUGEINT*r.n),0)
          FROM m l JOIN m r ON """+join+" WHERE l.arm=0 AND r.arm=1")[0]
    t=pairs('l.k IS NOT DISTINCT FROM r.k')
    u=pairs('l.k::DOUBLE IS NOT DISTINCT FROM r.k::DOUBLE')
    v=pairs('l.k IS NOT DISTINCT FROM (r.k::DOUBLE)::HUGEINT')
    w=pairs('l.k IS NOT DISTINCT FROM r.k AND l.k IS NOT DISTINCT FROM (r.k::DOUBLE)::HUGEINT')
    widen = one("""WITH K AS (SELECT DISTINCT k FROM x WHERE k IS NOT NULL)
      SELECT count(*) FILTER (WHERE k::DOUBLE <> (k::HUGEINT)::DOUBLE),
             count(*) FILTER (WHERE k=(k::DOUBLE)::HUGEINT AND k::DOUBLE <> (k::HUGEINT)::DOUBLE),
             count(*) FILTER (WHERE k<0 AND k::DOUBLE <> (k::HUGEINT)::DOUBLE) FROM K""")
    vw=pairs('l.k IS NOT DISTINCT FROM ((r.k::HUGEINT)::DOUBLE)::HUGEINT')
    ww=pairs('l.k IS NOT DISTINCT FROM r.k AND l.k IS NOT DISTINCT FROM ((r.k::HUGEINT)::DOUBLE)::HUGEINT')
    exact = dict(population=n,original_nulls=nil,distinct=d[0],keys_changed=d[1],
        collided_exact_keys=d[3],collided_buckets=d[2],
        exact_pairs=t,source_exact_nonnull_pairs=t-nil2-nil-1,
        both_false_pairs=u-t,both_lost_pairs=0,
        unilateral_false_pairs=v-w,unilateral_lost_pairs=t-w,
        authored_null_pairs_added=nil+1)
    return exact, dict(distinct_widened_double_diff=widen[0], exact_before_widening=widen[1],
       negative_diff=widen[2], unilateral_false_pairs=vw-ww, unilateral_lost_pairs=t-ww)


def main():
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);a=p.parse_args()
    assert duckdb.__version__ in ("1.4.3","2.0.1") and pyarrow.__version__ in ("22.0.0","26.0.1")
    assert sha(a.input)==SHA and sha(ROOT/'PLAN.json')==(ROOT/'PRE.sha256').read_text().split()[0]
    # Round-to-even controls, including signed extremes and tie neighbors.
    for z in range(53,64):
        for y in range(-16,17):
            for sign in (-1,1):
                v=sign*((1<<z)+y)
                assert projected(v)==int(float(v))
    out={}
    with duckdb.connect(config={'threads':'2','memory_limit':'768MB'}) as c:
        for col in COLUMNS:
            x=reference(a.input,col)
            y,w=native(str(a.input),col,c)
            assert x==y,(col,x,y)
            out[col]=dict(bigint_source=x,widening_control=w)
    print(json.dumps(dict(duckdb=duckdb.__version__,pyarrow=pyarrow.__version__,columns=out),indent=2,sort_keys=True))


if __name__=='__main__':main()
