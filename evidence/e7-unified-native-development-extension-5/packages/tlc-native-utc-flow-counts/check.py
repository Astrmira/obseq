from datetime import datetime,timedelta,timezone
from collections import Counter
from zoneinfo import ZoneInfo
from pathlib import Path
from itertools import product
from random import Random
import hashlib,json,sys
import duckdb,pyarrow as pa,pyarrow.compute as pc,pyarrow.parquet as pq
file=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/pvl-eab-submission/e4/inputs/2025-11.parquet')
tzfile=Path(sys.argv[2]) if len(sys.argv)>2 else Path('/tmp/project-eab-dbt-freshness/deps/pytz/zoneinfo/America/New_York')
for path,sha in [(file,'2cf2f3127f96d4d5dea30f8afe05119cf8e4ba57bd9e60b789d3f296fc8459ab'),
                 (tzfile,'e9ed07d7bee0c76a9d442d091ef1f01668fee7c4f26014c0a868b19fe6c18a95')]:
    with path.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==sha
assert duckdb.__version__=='2.0.1' and pa.__version__=='26.0.1'
with tzfile.open('rb') as f: tz=ZoneInfo.from_file(f,key='America/New_York')
utc=timezone.utc
def options(t):
    a={t.replace(tzinfo=tz,fold=i).astimezone(utc) for i in (0,1)}
    return sorted(v for v in a if v.astimezone(tz).replace(tzinfo=None)==t)
lo=datetime(2025,11,1);hi=datetime(2025,12,1)
hour=timedelta(hours=1)
f,=[lo+k*hour for k in range(30*24) if len(options(lo+k*hour))==2]
g=f+hour
c=options(f)[1]; assert c==datetime(2025,11,2,6,tzinfo=utc)
assert len(options(f-timedelta(microseconds=1)))==len(options(g))==1
names=['tpep_pickup_datetime','tpep_dropoff_datetime']
source=pq.ParquetFile(file)
data={}
n=0
def between(a,l,h):return pc.and_kleene(pc.greater_equal(a,l),pc.less(a,h))
for block in source.iter_batches(columns=names,batch_size=65536):
    pp,dd=block.columns
    assert pp.type==dd.type==pa.timestamp('us')
    m=pc.and_kleene(pc.and_kleene(between(pp,lo,hi),between(dd,lo,hi)),
                    pc.or_kleene(between(pp,f,g),between(dd,f,g)))
    ids=pc.indices_nonzero(pc.fill_null(m,False)).to_pylist()
    if ids:
        sub=block.take(ids)
        for i,p,d in zip(ids,*(v.to_pylist() for v in sub.columns)):
            a,b=options(p),options(d)
            # bit A both after=1, B cross=2, C both before=4
            pos={(2 if y<c else 1 if x<c else 0) for x in a for y in b if x<=y}
            assert pos
            data[n+i]=(sum(1<<j for j in pos),int(a[-1]<c),int(b[-1]<c),int(a[-1]<=b[-1]))
    n+=block.num_rows
db=duckdb.connect(config={'threads':'1','memory_limit':'512MB','max_temp_directory_size':'0B'})
s=db.execute(f"""
WITH src AS (
 SELECT file_row_number AS id, {names[0]} p, {names[1]} d FROM read_parquet(?,file_row_number=true)
 WHERE {names[0]}>=? AND {names[0]}<? AND {names[1]}>=? AND {names[1]}<?
 AND (({names[0]}>=? AND {names[0]}<?) OR ({names[1]}>=? AND {names[1]}<?))
), local AS (
 SELECT *,timezone('America/New_York',p) px, timezone('America/New_York',d) dx FROM src
), pair AS (
 SELECT *,px-i*INTERVAL '1 hour' u,dx-j*INTERVAL '1 hour' v
 FROM local CROSS JOIN (VALUES (0),(1)) a(i) CROSS JOIN (VALUES (0),(1)) b(j)
), real AS (
 SELECT * FROM pair WHERE timezone('America/New_York',u)=p AND timezone('America/New_York',v)=d
)
SELECT id, COALESCE(bit_or(CASE WHEN v<? THEN 4 WHEN u<? THEN 2 ELSE 1 END)
    FILTER(WHERE u<=v),0),max((px<?)::INT),max((dx<?)::INT),max((px<=dx)::INT)
FROM real GROUP BY id""",[str(file),lo,hi,lo,hi,f,g,f,g,c,c,c,c]).fetchall()
assert len(s)==len(data) and {k:tuple(r) for k,*r in s}==data
support=Counter(r[0] for r in data.values())
assert sum(support.values())==14326
N=sum(support.values())
def extrema(H,m):
    return (sum(v for k,v in H.items() if k&m==k),sum(v for k,v in H.items() if k&m))
def yes(H,q):
    if min(q)<0 or sum(q)!=sum(H.values()):return False
    return all(sum(q[i] for i in range(3) if 1<<i&m)<=extrema(H,m)[1] for m in range(1,8))
def as_quota(p,d):
    return (N-p,p-d,d)
pmin,pmax=extrema(support,6)
dmin,dmax=extrema(support,4)
bmin,bmax=extrema(support,2)
def choose(score):
    q=[0]*3
    for mask,nm in support.items():
        i=min((x for x in range(3) if mask&(1<<x)),key=score)
        q[i]+=nm
    assert yes(support,q)
    return q
assert choose(lambda i:i!=1)[1]==bmax and choose(lambda i:i==1)[1]==bmin
# Marginals and ordinary global chronological inequality alone can pass a
# claim that omits all forced crossings; search at the deterministic edge.
w=None
for early_drop in (dmin,dmax):
    for early_pick in (max(early_drop,pmin),min(pmax,early_drop+bmin-1)):
        if pmin<=early_pick<=pmax and dmin<=early_drop<=dmax and 0<=early_pick-early_drop<bmin:
            q=as_quota(early_pick,early_drop)
            if not yes(support,q):w=(early_pick,early_drop,list(q));break
    if w:break
assert w
# At maximally allowed early drops, adjoining integer claims differ by
# one forced crossing. These are a concrete strict joint boundary pair.
adjacent=(dmax+bmin-1,dmax)
admitted=(dmax+bmin,dmax)
assert not yes(support,as_quota(*adjacent)) and yes(support,as_quota(*admitted))
independent_ordered=accepted=0
for P in range(pmin,pmax+1):
    independent_ordered+=max(0,min(P,dmax)-dmin+1)
    accepted+=max(0,min(dmax,P-bmin)-max(dmin,P-bmax)+1)
assert 0<accepted<independent_ordered
stock=[sum(r[i] for r in data.values()) for i in (1,2,3)]
def exhaustive():
    rng=Random(7); k=0
    for _ in range(160):
        masks=[rng.randint(1,7) for i in range(rng.randint(1,6))]
        H=Counter(masks);n=len(masks)
        S={tuple(a.count(i) for i in range(3)) for a in product(*(tuple(i for i in range(3) if m&(1<<i)) for m in masks))}
        for i in range(n+1):
            for j in range(n+1-i):
                x=(i,j,n-i-j)
                singletons=all(extrema(H,1<<l)[0]<=x[l]<=extrema(H,1<<l)[1] for l in range(3))
                assert yes(H,x)==singletons==(x in S);k+=1
    return k
print(json.dumps(dict(source_rows=n,cohort=N,transition=c.isoformat(),category_support=dict(support),
    aggregate_bounds={'early_pickup':[pmin,pmax],'early_dropoff':[dmin,dmax],'crossing':[bmin,bmax]},
    authored_infeasible_inside_marginals_and_chronological=w,
    adjacent_rejected_counts=adjacent,adjacent_accepted_counts=admitted,
    count_pairs_independent_ordered=independent_ordered,count_pairs_joint_feasible=accepted,
    stock_default={'early_pickup':stock[0],'early_dropoff':stock[1],'crossing_inferred':stock[0]-stock[1],
        'physically_unordered':N-stock[2],'aggregate_feasible':yes(support,as_quota(stock[0],stock[1]))},
    exhaustive_quota_tests=exhaustive(),duckdb=duckdb.__version__,arrow=pa.__version__),sort_keys=True,indent=2))
