"""Joint order-constrained UTC hypotheses for native TLC meter intervals."""
from pathlib import Path
import argparse
from collections import Counter
from datetime import datetime,timedelta,timezone
import hashlib,json
from zoneinfo import ZoneInfo
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent
ZONE="America/New_York"
P="tpep_pickup_datetime"
D="tpep_dropoff_datetime"
HOUR=timedelta(hours=1)
UTC=timezone.utc

def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

def options(t,tz):
    can=[t.replace(tzinfo=tz,fold=f).astimezone(UTC) for f in (0,1)]
    return sorted({u for u in can if u.astimezone(tz).replace(tzinfo=None)==t})

def support(p,d,tz):
    a,b=options(p,tz),options(d,tz)
    paths=[(u,v) for u in a for v in b if v>=u]
    durations={v-u for u,v in paths}
    late=b[-1]>=a[-1]
    early=b[0]>=a[0]
    return len(a),len(b),len(paths),len(durations),int(late),int(early)

def timezone_bounds(y,tz):
    # Enumerate the month, rather than assuming the transition date by wall arithmetic.
    lo=datetime(y,11,1);hi=datetime(y,12,1)
    h=lo
    folds=[]
    while h<hi:
        if len(options(h,tz))==2:
            assert len(options(h+HOUR-timedelta(microseconds=1),tz))==2
            folds.append(h)
        h+=HOUR
    [f]=folds
    assert len(options(f-timedelta(microseconds=1),tz))==len(options(f+HOUR,tz))==1
    return lo,hi,f,f+HOUR

def independent(src,tz,lo,hi,f,g):
    before=[(c,">=",lo) for c in (P,D)]+[(c,"<",hi) for c in (P,D)]
    tbl=pq.read_table(src,columns=[P,D],filters=[
        before+[(c,">=",f),(c,"<",g)] for c in (P,D)
    ])
    assert tbl.column(0).type==tbl.column(1).type==pa.timestamp("us")
    result=Counter()
    for block in tbl.to_batches():
        for p,d in zip(block.column(0).to_pylist(),block.column(1).to_pylist()):
            result[(p,d,*support(p,d,tz))]+=1
    return result

def native(con,src,lo,hi,f,g):
    sql=f"""
    WITH paths AS (
      SELECT file_row_number AS id, {P} AS p, {D} AS d
      FROM read_parquet(?, file_row_number=true)
      WHERE {P}>=? AND {P}<? AND {D}>=? AND {D}<?
      AND (({P}>=? AND {P}<?) OR ({D}>=? AND {D}<?))
    ), localized AS (
      SELECT *, timezone('{ZONE}',p) AS px, timezone('{ZONE}',d) AS dx
      FROM paths
    ), all_folds AS (
      SELECT id, p, d, i, j, px, dx,
         px-i*INTERVAL '1 hour' AS u, dx-j*INTERVAL '1 hour' AS v
      FROM localized CROSS JOIN (VALUES(0),(1)) a(i) CROSS JOIN (VALUES(0),(1)) b(j)
    ), valid AS (
      SELECT * FROM all_folds
      WHERE timezone('{ZONE}',u)=p AND timezone('{ZONE}',v)=d
    ), signatures AS (
      SELECT id,any_value(p) AS pp,any_value(d) AS dd,count(DISTINCT u) AS m,count(DISTINCT v) AS n,
        count(*) FILTER (WHERE v>=u) AS legal_pairs,
        count(DISTINCT epoch_us(v)-epoch_us(u)) FILTER (WHERE v>=u) AS durations,
        max(CASE WHEN px<=dx THEN 1 ELSE 0 END) AS stock,
        CASE WHEN max(v-u) FILTER (WHERE u=(CASE WHEN timezone('{ZONE}',px-INTERVAL '1 hour')=p THEN px-INTERVAL '1 hour' ELSE px END)
             AND v=(CASE WHEN timezone('{ZONE}',dx-INTERVAL '1 hour')=d THEN dx-INTERVAL '1 hour' ELSE dx END)) >= INTERVAL '0 seconds' THEN 1 ELSE 0 END AS early
      FROM valid GROUP BY id
    ) SELECT pp,dd,m,n,legal_pairs,durations,stock,early,count(*) FROM signatures GROUP BY ALL
    """
    return Counter({tuple(r[:-1]):r[-1] for r in con.execute(sql,
        [src,lo,hi,lo,hi,f,g,f,g]).fetchall()})

def summarize(y,result):
    groups=[dict(pickup_choices=p,dropoff_choices=d,valid_pairs=u,valid_durations=v,stock_valid=s,earliest_valid=t,rows=n) for (p,d,u,v,s,t),n in sorted(result.items())]
    def filt(pred):return sum(n for key,n in result.items() if pred(*key))
    return dict(year=y,cohort=sum(result.values()),
      pickup_ambiguous=filt(lambda p,d,u,v,s,t:p==2),
      dropoff_ambiguous=filt(lambda p,d,u,v,s,t:d==2),
      both_ambiguous=filt(lambda p,d,u,v,s,t:p==2 and d==2),
      no_feasible_pair=filt(lambda p,d,u,v,s,t:u==0),
      unique_feasible_pair=filt(lambda p,d,u,v,s,t:u==1),
      unique_duration_ambiguous_instants=filt(lambda p,d,u,v,s,t:u>1 and v==1),
      multiple_feasible_durations=filt(lambda p,d,u,v,s,t:v>1),
      stock_invalid_despite_exists=filt(lambda p,d,u,v,s,t:u>0 and not s),
      earliest_invalid_despite_exists=filt(lambda p,d,u,v,s,t:u>0 and not t),
      groups=groups)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("inputs",type=Path)
    p.add_argument("tzif",type=Path)
    args=p.parse_args()
    for ln in (ROOT/"PRE.sha256").read_text().splitlines():
        want,n=ln.split()
        assert sha(ROOT/n)==want
    assert sha(args.tzif)==(ROOT/"TZ.sha256").read_text().split()[0]
    assert duckdb.__version__=="2.0.1" and pa.__version__=="26.0.1"
    with args.tzif.open("rb") as f:tz=ZoneInfo.from_file(f,key=ZONE)
    results=[]
    with duckdb.connect(config={"threads":"2","memory_limit":"512MB"}) as c:
        for row in (ROOT/"INPUTS.sha256").read_text().splitlines():
            want,n=row.split()
            path=args.inputs/n
            assert sha(path)==want
            y=int(n[:4])
            l,h,f,g=timezone_bounds(y,tz)
            # Authored domain examples, not corpus rows: clock appears to reverse,
            # appears to progress, and progresses from an ambiguous source into EST.
            assert support(f+timedelta(minutes=50),f+timedelta(minutes=10),tz)==(2,2,1,1,0,0)
            assert support(f+timedelta(minutes=10),f+timedelta(minutes=50),tz)==(2,2,3,2,1,1)
            assert support(f+timedelta(minutes=50),g+timedelta(minutes=10),tz)==(2,1,2,2,1,1)
            a=independent(path,tz,l,h,f,g)
            b=native(c,str(path),l,h,f,g)
            assert a==b,(y,sum((a-b).values()),sum((b-a).values()))
            ag=Counter()
            for key,n in a.items():ag[key[2:]]+=n
            results.append(summarize(y,ag))
    print(json.dumps(results,indent=2))

if __name__=="__main__":main()
