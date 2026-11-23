"""Narrow exact join key repair; no literal source identifiers in diagnostics."""
from pathlib import Path
from collections import Counter,defaultdict
from hashlib import file_digest
import json,sys
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import duckdb

ROOT=Path(__file__).resolve().parent

def digest(p):
    with p.open("rb") as f:return file_digest(f,"sha256").hexdigest()

def canonical(i):
    a=abs(i)
    d=1<<max(0,a.bit_length()-53)
    q,r=divmod(a,d)
    v=(q+int(2*r>d or (2*r==d and q%2==1)))*d
    return -v if i<0 else v

def twins(L,R,engine,corp):
    # Independent exact integer cohort. No rank data needed for singleton float buckets.
    bucket=defaultdict(list)
    for k in sorted(set(L)|set(R)):bucket[canonical(k)].append(k)
    rank={k:i for keys in bucket.values() if len(keys)>1 for i,k in enumerate(keys)}
    bits={k:(len(keys)-1).bit_length() for keys in bucket.values() if len(keys)>1 for k in keys}
    expected_left,expected_right=Counter(L),Counter(R)
    repaired_ids=[Counter((canonical(k),rank.get(k,0)) for k in row) for row in (L,R)]
    assert all(len(set((canonical(k),rank.get(k,0)) for k in keys))==len(keys) for keys in bucket.values())
    exact=sum(n*expected_right[k] for k,n in expected_left.items())+1
    r0,r1=[Counter(canonical(k) for k in row) for row in (L,R)]
    rounded=sum(n*r1[k] for k,n in r0.items())+1
    repaired=sum(n*repaired_ids[1][k] for k,n in repaired_ids[0].items())+1
    assert repaired==exact
    idcol=np.array(L+R,dtype=np.int64)
    group=np.array([0]*len(L)+[1]*len(R),dtype=np.uint8)
    tagcol=np.array([rank.get(k,0) for k in L+R],dtype=np.int16)
    values=pa.table({"i":pa.array(idcol),"side":pa.array(group),"tag":pa.array(tagcol)})
    engine.register("source_arrow",values)
    # Float uses stock cast. Null has one typed authored row on each side, fixed tag 0.
    engine.execute("""CREATE OR REPLACE TABLE mult AS SELECT side,i,i::DOUBLE AS f,tag,count(*) n
        FROM (SELECT * FROM source_arrow UNION ALL SELECT NULL::BIGINT,0,0
            UNION ALL SELECT NULL::BIGINT,1,0)
        GROUP BY ALL""")
    sql="SELECT coalesce(sum(l.n::HUGEINT*r.n),0) FROM mult l JOIN mult r ON {} WHERE l.side=0 AND r.side=1"
    arms=[engine.execute(sql.format(filter_)).fetchall()[0][0] for filter_ in (
        'l.i IS NOT DISTINCT FROM r.i', 'l.f IS NOT DISTINCT FROM r.f',
        'l.f IS NOT DISTINCT FROM r.f AND l.tag=r.tag')]
    assert arms==[exact,rounded,repaired]
    engine.execute("""CREATE OR REPLACE TABLE wire AS
        SELECT side,f,tag,sum(n) AS n FROM mult GROUP BY ALL""")
    only_wire=engine.execute(sql.replace("mult","wire").format(
        "l.f IS NOT DISTINCT FROM r.f AND l.tag=r.tag")).fetchall()[0][0]
    assert only_wire==exact
    # Full native disjoint difference using typed individual keys and per-key row multiplicities.
    # This avoids materializing millions of duplicate row pairs.
    a=engine.execute(sql.format('l.f IS NOT DISTINCT FROM r.f AND l.tag=r.tag AND l.i IS DISTINCT FROM r.i')).fetchall()[0][0]
    b=engine.execute(sql.format('l.i IS NOT DISTINCT FROM r.i AND (l.f IS DISTINCT FROM r.f OR l.tag<>r.tag)')).fetchall()[0][0]
    assert a==b==0
    if corp.startswith("Tweet"):
        # Values are unique within each side; exact full tuple comparison includes NULL.
        raw=engine.execute("""SELECT l.i,r.i FROM mult l JOIN mult r ON
            l.f IS NOT DISTINCT FROM r.f AND l.tag=r.tag WHERE l.side=0 AND r.side=1""").fetchall()
        assert set(raw)=={(k,k) for k in set(L)&set(R)}|{(None,None)} and len(raw)==exact
    engine.unregister("source_arrow")
    return dict(case=corp,left=len(L),right=len(R),all_domain_distinct=len(set(L)|set(R)),
                known_colliding_buckets=sum(len(k)>1 for k in bucket.values()),
                pair_counts={"exact":arms[0],"symmetric_float":arms[1],"repaired":arms[2]},
                authored_null_pair=1,
                float_false_pairs=arms[1]-arms[0],
                ambiguous_occurrences=sum(bool(bits.get(k)) for k in L+R),
                conditional_tag_bits=sum(bits.get(k,0) for k in L+R),
                max_conditional_bits=max(bits.values(),default=0))

def main():
    a,b=map(Path,sys.argv[1:])
    for ln in (ROOT/'PRE.sha256').read_text().splitlines():
        h,n=ln.split()
        assert digest(ROOT/n)==h
    tweet=[]
    for ln in (ROOT/'TWEET-INPUTS.sha256').read_text().splitlines():
        h,n=ln.split();p=a/n
        assert digest(p)==h
        tweet+=list(map(int,p.read_text().splitlines()))
    assert len(set(tweet))==len(tweet)==22743
    tweet.sort()
    assert digest(b)=="fa134fe101e68324e0de851146fda69624f5cbb707d387141d1c2a88a219a16d"
    native_keys=pq.read_table(b,columns=['UserID']).column(0)
    assert native_keys.type==pa.int64() and len(native_keys)==1000000 and native_keys.null_count==0
    click=native_keys.to_pylist()
    assert duckdb.__version__=='2.0.1' and pa.__version__=='26.0.1'
    with duckdb.connect(config={'threads':'2','memory_limit':'512MB'}) as c:
        out=[twins(tweet,tweet,c,"TweetIDs-self"),
             twins(tweet[::2],tweet[1::2],c,"TweetIDs-parity"),
             twins(click[::2],click[1::2],c,"ClickBench-UserID-parity")]
    print(json.dumps(out,indent=2,sort_keys=True))

if __name__=="__main__":main()
