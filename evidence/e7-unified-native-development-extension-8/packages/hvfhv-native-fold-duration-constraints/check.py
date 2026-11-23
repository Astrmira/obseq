from collections import Counter
from datetime import datetime,timedelta,timezone
from hashlib import file_digest
from pathlib import Path
from zoneinfo import ZoneInfo
import json, sys
import duckdb, pyarrow as pa, pyarrow.parquet as pq
Z='America/New_York'
COLS=('hvfhs_license_num','pickup_datetime','dropoff_datetime','trip_time')
def picks(t,z):
    a={t.replace(tzinfo=z,fold=i).astimezone(timezone.utc) for i in (0,1)}
    return sorted(u for u in a if u.astimezone(z).replace(tzinfo=None)==t)
def secs(t):
    return ((t.days*86400+t.seconds)*1_000_000+t.microseconds)
def py(p,start,stop,dlo,dhi,tz):
    ar=pq.read_table(p,columns=list(COLS),filters=[(COLS[1],'>=',start),(COLS[1],'<',stop)])
    out=Counter(); guards=0
    for who,a,b,n in zip(*(ar[c].to_pylist() for c in COLS)):
        if b is None or not dlo<=b<dhi: guards+=1; continue
        X,Y=picks(a,tz),picks(b,tz)
        ds=[secs(y-x) for x in X for y in Y if y>=x]
        usable=n is not None and n>=0
        k=sum(d==n*1_000_000 for d in ds) if usable else -1
        w=usable and secs(b-a)==n*1_000_000
        out[who,len(X),len(Y),len(ds),k,w,n is None,n is not None and n<0]+=1
    return out,ar.num_rows,guards
def native(p,start,stop,dlo,dhi):
    c=duckdb.connect(config={'threads':1,'memory_limit':'384MB'})
    c.read_parquet(str(p),file_row_number=True).create_view('orig')
    base=c.execute("""SELECT count(*),count(*) FILTER (WHERE dropoff_datetime IS NULL OR dropoff_datetime < ? OR dropoff_datetime >= ?)
                      FROM orig WHERE pickup_datetime>=? AND pickup_datetime<?""",
                   [dlo,dhi,start,stop]).fetchone()
    c.execute("""CREATE TEMP TABLE scope AS SELECT file_row_number i, hvfhs_license_num who, pickup_datetime a, dropoff_datetime b, trip_time n,
        timezone('America/New_York',pickup_datetime) aa,timezone('America/New_York',dropoff_datetime) bb
        FROM orig WHERE pickup_datetime>=? AND pickup_datetime<? AND dropoff_datetime>=? AND dropoff_datetime<?""",
        [start,stop,dlo,dhi])
    raw=c.sql("""WITH P AS
      (SELECT i,aa+k*INTERVAL '1 hour' AS z FROM scope CROSS JOIN range(-1,2) s(k)
       WHERE timezone('America/New_York',aa+k*INTERVAL '1 hour')=a),
     D AS
      (SELECT i,bb+k*INTERVAL '1 hour' AS z FROM scope CROSS JOIN range(-1,2) s(k)
       WHERE timezone('America/New_York',bb+k*INTERVAL '1 hour')=b),
     PC AS (SELECT i,count(*) v FROM P GROUP BY i), DC AS (SELECT i,count(*) v FROM D GROUP BY i),
     pairs AS (SELECT P.i,count(*) v,
       count(*) FILTER (WHERE date_diff('microsecond',P.z,D.z)=scope.n::HUGEINT*1000000) matched
       FROM P JOIN D ON P.i=D.i JOIN scope ON P.i=scope.i WHERE D.z>=P.z GROUP BY P.i)
     SELECT who,coalesce(PC.v,0) pc,coalesce(DC.v,0) dc,coalesce(pairs.v,0) pp,
       CASE WHEN n>=0 THEN coalesce(matched,0) ELSE -1 END kk,
       coalesce(n>=0 AND date_diff('microsecond',a,b)=n::HUGEINT*1000000,FALSE) wall,
       n IS NULL missing, coalesce(n<0,FALSE) negative,count(*) nn
     FROM scope LEFT JOIN PC USING(i) LEFT JOIN DC USING(i) LEFT JOIN pairs USING(i)
     GROUP BY ALL""").fetchall()
    c.close()
    return Counter({tuple(r[:-1]):r[-1] for r in raw}),*base
def run(p,zfile):
    with zfile.open('rb') as f: tz=ZoneInfo.from_file(f,key=Z)
    with p.open('rb') as f: sha=file_digest(f,'sha256').hexdigest()
    source=pq.ParquetFile(p)
    assert str(source.schema_arrow.field(COLS[1]).type)==str(source.schema_arrow.field(COLS[2]).type)=='timestamp[us]'
    assert source.schema_arrow.field(COLS[3]).type==pa.int64()
    out=[]
    for day in (2,9):
        start=datetime(2025,11,day); stop=start+timedelta(hours=4)
        glo=start-timedelta(days=1); ghi=start+timedelta(days=2)
        c,rows,bad=py(p,start,stop,glo,ghi,tz)
        assert (c,rows,bad)==native(p,start,stop,glo,ghi)
        rx=[]
        for r,count in sorted(c.items(),key=lambda x:str(x[0])):
            who,pc,dc,np,nm,w,missing,negative=r
            rx.append(dict(provider=who,pickup_candidates=pc,dropoff_candidates=dc,nonnegative_pairs=np,
                matching_reported_duration=nm,wall_difference_equals_duration=w,missing_duration=missing,negative_duration=negative,rows=count))
        out.append(dict(day=day,selected=rows,invalid_endpoint_guard=bad,strata=rx))
    with zfile.open('rb') as f: zh=file_digest(f,'sha256').hexdigest()
    return dict(source_sha256=sha,zone_sha256=zh,monthly_rows=source.metadata.num_rows,
                pyarrow=pa.__version__,duckdb=duckdb.__version__,cohorts=out)
if __name__=='__main__':
    print(json.dumps(run(Path(sys.argv[1]),Path(sys.argv[2])),sort_keys=True,indent=2))
