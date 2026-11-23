from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
import hashlib,itertools,json,sys
import duckdb,pyarrow as pa,pyarrow.compute as pc,pyarrow.parquet as pq
path=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/pvl-eab-submission/e4/inputs/2025-11.parquet')
with path.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()=='2cf2f3127f96d4d5dea30f8afe05119cf8e4ba57bd9e60b789d3f296fc8459ab'
assert duckdb.__version__=='1.4.3' and pa.__version__=='26.0.1'
cols=['VendorID','PULocationID','tpep_pickup_datetime','passenger_count']
t0=datetime(2025,11,1); t1=datetime(2025,12,1)
source=pq.ParquetFile(path)
G=defaultdict(list)
end=0
for batch in source.iter_batches(columns=cols,batch_size=65536):
    p=batch.column(1)
    idx=pc.indices_nonzero(pc.is_in(p,value_set=pa.array([132,138],type=p.type))).to_pylist()
    if idx:
        selected=batch.take(idx)
        tup=list(zip(*(a.to_pylist() for a in selected.columns)))
        for offset,(v,z,t,pax) in zip(idx,tup):
            if v is not None and t is not None and t0<=t<t1:
                G[v,z].append((t,end+offset,pax is not None))
    end+=batch.num_rows
assert end==4_181_444
for a in G.values(): a.sort()
D=duckdb.connect(config={'threads':'1','memory_limit':'512MB','max_temp_directory_size':'0B'})
D.execute("""CREATE TABLE src AS SELECT VendorID v, PULocationID z,
             tpep_pickup_datetime t,file_row_number k,passenger_count IS NOT NULL known
             FROM read_parquet(?,file_row_number=true)
             WHERE PULocationID IN (132,138) AND VendorID IS NOT NULL
               AND tpep_pickup_datetime>=TIMESTAMP '2025-11-01' AND tpep_pickup_datetime<TIMESTAMP '2025-12-01'""",[str(path)])
truth=[(v,z,t,k,b) for (v,z),r in sorted(G.items()) for t,k,b in r]
assert truth==D.execute('SELECT * FROM src ORDER BY v,z,t,k').fetchall()
def oracle(secs,known):
    out={}
    for (v,z),r in G.items():
        p=None; episode=0
        for t,k,b in r:
            if known and not b: continue
            delta=(t-p) if p else None
            if delta is None or (delta.days*86400+delta.seconds)*1000000+delta.microseconds>secs*1000000:episode+=1
            p=t
            out[(v,z,k)]=(episode,b)
    return out
# Span IDs count known occurrences strictly before the row. A known row
# closes its incoming span, which covers all removed events since the
# previous known row; span 0 has no previous known.
bridge=D.execute("""WITH runs AS (
 SELECT *,lag(t) OVER (PARTITION BY v,z ORDER BY t,k) AS p,
          COALESCE(sum(known::INTEGER) OVER (PARTITION BY v,z ORDER BY t,k
                     ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),0) AS span
 FROM src
), witnessed AS (
 SELECT *,max(epoch_us(t)-epoch_us(p)) OVER(PARTITION BY v,z,span) AS max_us FROM runs
) SELECT v,z,k,CASE WHEN span=0 THEN NULL ELSE max_us END FROM witnessed WHERE known
ORDER BY v,z,t,k""").fetchall()
def scalar_reference():
    for (v,z),r in sorted(G.items()):
        previous=None
        since_known=None
        first=True
        for t,k,b in r:
            if previous is not None:
                d=t-previous
                d=(d.days*86400+d.seconds)*1000000+d.microseconds
                since_known=d if since_known is None else max(since_known,d)
            if b:
                yield v,z,k,None if first else since_known
                since_known=None; first=False
            previous=t
assert bridge==list(scalar_reference())
out={}
for sec in (60,300):
    def native(known):
        values=D.execute("""WITH prev AS (
          SELECT *,lag(t) OVER (PARTITION BY v,z ORDER BY t,k) p FROM src WHERE (known OR NOT ?)
        ), flags AS (
          SELECT *,CASE WHEN p IS NULL OR t-p > (? * INTERVAL '1 second') THEN 1 ELSE 0 END b FROM prev
        ) SELECT v,z,k, sum(b) OVER (PARTITION BY v,z ORDER BY t,k ROWS UNBOUNDED PRECEDING), known FROM flags""",[known,sec]).fetchall()
        return {(v,z,k):(s,b) for v,z,k,s,b in values}
    all_s=oracle(sec,False); known_s=oracle(sec,True)
    assert native(False)==all_s and native(True)==known_s
    surviving=defaultdict(set); reverse=defaultdict(set)
    for k,(new,b) in known_s.items():
        assert b and all_s[k][1]
        prev=all_s[k][0]
        surviving[k[:2]+(prev,)].add(new)
        reverse[k[:2]+(new,)].add(prev)
    assert all(len(v)==1 for v in reverse.values())
    # Rebuild the same survivor partition from one scalar per adjacent
    # surviving pair. Episode ordinals can differ where all-unknown
    # original episodes lie between survivors; compare actual membership.
    rebuilt=defaultdict(set)
    ep=defaultdict(int)
    for v,z,k,us in bridge:
        if us is None or us>sec*1_000_000:ep[v,z]+=1
        rebuilt[v,z,ep[v,z]].add(all_s[v,z,k][0])
    assert all(len(v)==1 for v in rebuilt.values())
    assert len(rebuilt)==len(surviving)
    assert {(v,z,next(iter(a))) for (v,z,_),a in rebuilt.items()}==surviving.keys()
    assert len(bridge)==len(known_s)
    complete={k[:2]+(ep,) for k,(ep,b) in all_s.items()}
    split={k for k,v in surviving.items() if len(v)>1}
    bridged=0
    for (v,z),r in G.items():
        for a,b in itertools.pairwise([k for _,k,pax in r if pax]):
            k1,k2=(v,z,a),(v,z,b)
            if all_s[k1][0]==all_s[k2][0] and known_s[k1][0]!=known_s[k2][0]:
                bridged+=1
    assert bridged==sum(len(v)-1 for v in surviving.values())
    out[sec]=dict(all_sessions=len(complete),surviving_baseline_sessions=len(surviving),
        all_unknown_sessions=len(complete-surviving.keys()),known_drop_sessions=len(reverse),
        surviving_sessions_split=len(split),altered_known_to_known_edges=bridged,cross_baseline_merges=0,
        known_rows_in_split_baseline=sum(k[:2]+(all_s[k][0],) in split for k in known_s))
print(json.dumps(dict(physical_rows=end,eligible_rows=len(truth),known_rows=sum(t[-1] for t in truth),
    vendor_zones=len(G),unknown_rows=sum(not t[-1] for t in truth),thresholds=out,verified_bridge_scalars=sum(us is not None for _,_,_,us in bridge),
    duckdb=duckdb.__version__,arrow=pa.__version__),sort_keys=True,indent=2))
