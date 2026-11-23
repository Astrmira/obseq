from collections import Counter
from datetime import datetime,timedelta,timezone
from hashlib import file_digest
from pathlib import Path
from zoneinfo import ZoneInfo
import json,sys
import duckdb,pyarrow.parquet as pq
Z='America/New_York'
COLS=('hvfhs_license_num','request_datetime','pickup_datetime','dropoff_datetime')
def run(p,zpath):
 with p.open('rb') as f: sha=file_digest(f,'sha256').hexdigest()
 assert sha=='a17ebafe3b6b1927f9b1b4cfc9062a328867b79a871ce762bfb16a841024f1e0'
 with zpath.open('rb') as f:z=ZoneInfo.from_file(f,key=Z)
 sc=pq.ParquetFile(p).schema_arrow
 assert all(str(sc.field(k).type)=='timestamp[us]' for k in COLS[1:])
 def opts(t):
  ss={t.replace(tzinfo=z,fold=k).astimezone(timezone.utc) for k in (0,1)}
  return sorted(v for v in ss if v.astimezone(z).replace(tzinfo=None)==t)
 c=duckdb.connect(config={"threads":1,"memory_limit":"384MB"})
 c.read_parquet(str(p),file_row_number=True).create_view('orig')
 ret=[]
 for day in (2,9):
  a=datetime(2025,11,day);b=a+timedelta(hours=4);l=a-timedelta(days=1);h=a+timedelta(days=2)
  ar=pq.read_table(p,columns=list(COLS),filters=[(COLS[2],'>=',a),(COLS[2],'<',b)])
  counts=Counter();excluded=Counter()
  for who,r,u,d in zip(*(ar[k].to_pylist() for k in COLS)):
   if r is None or d is None: excluded['missing']+=1;continue
   if not(l<=r<h and l<=d<h):excluded['outside']+=1;continue
   X,Y,W=opts(r),opts(u),opts(d)
   seq=[(x,y,w) for x in X for y in Y for w in W if x<=y<=w]
   default=bool(X and Y and W and X[-1]<=Y[-1]<=W[-1])
   # DuckDB admits the later ambiguous offset for these named dates.
   wait={y-x<=timedelta(minutes=15) for x,y,_ in seq}
   counts[who,len(seq),default,True in wait,False in wait]+=1
  sql="""CREATE OR REPLACE TEMP TABLE s AS SELECT file_row_number i,hvfhs_license_num who,
      request_datetime r,pickup_datetime p,dropoff_datetime d,
      timezone('America/New_York',r) rz,timezone('America/New_York',p) pz,timezone('America/New_York',d) dz
      FROM orig WHERE pickup_datetime>=? AND pickup_datetime<? AND request_datetime>=? AND request_datetime<?
      AND dropoff_datetime>=? AND dropoff_datetime<?"""
  c.execute(sql,[a,b,l,h,l,h])
  got=c.sql("""WITH R AS (SELECT i,rz+k*INTERVAL '1 hour' u FROM s CROSS JOIN range(-1,2) t(k)
       WHERE timezone('America/New_York',rz+k*INTERVAL '1 hour')=r),
     P AS (SELECT i,pz+k*INTERVAL '1 hour' u FROM s CROSS JOIN range(-1,2) t(k)
       WHERE timezone('America/New_York',pz+k*INTERVAL '1 hour')=p),
     D AS (SELECT i,dz+k*INTERVAL '1 hour' u FROM s CROSS JOIN range(-1,2) t(k)
       WHERE timezone('America/New_York',dz+k*INTERVAL '1 hour')=d),
     M AS (SELECT R.i,count(*) n,bool_or(P.u-R.u<=INTERVAL '15 minutes') ys,
       bool_or(P.u-R.u>INTERVAL '15 minutes') ns FROM R JOIN P USING(i) JOIN D USING(i)
       WHERE R.u<=P.u AND P.u<=D.u GROUP BY R.i)
     SELECT who,coalesce(n,0), rz<=pz AND pz<=dz,coalesce(ys,false),coalesce(ns,false),count(*)
       FROM s LEFT JOIN M USING(i) GROUP BY ALL""").fetchall()
  assert Counter({tuple(q[:-1]):q[-1] for q in got})==counts
  assert sum(counts.values())+sum(excluded.values())==ar.num_rows
  ret.append(dict(day=day,selected=ar.num_rows,excluded=excluded,
   legal_order_but_default_rejects=sum(n for (who,k,f,ys,ns),n in counts.items() if k and not f),
   no_legal_order=sum(n for (who,k,f,ys,ns),n in counts.items() if not k),
   both_wait_labels=sum(n for (who,k,f,ys,ns),n in counts.items() if ys and ns),
   strata=[dict(provider=who,legal_chains=k,default_order=f,wait_at_most15_possible=ys,wait_above15_possible=ns,rows=n)
    for (who,k,f,ys,ns),n in sorted(counts.items(),key=lambda x:str(x[0]))]))
 with zpath.open('rb') as f: zh=file_digest(f,'sha256').hexdigest()
 return dict(source_sha256=sha,zone_sha256=zh,observations=ret)
if __name__=='__main__':
 print(json.dumps(run(Path(sys.argv[1]),Path(sys.argv[2])),sort_keys=True,indent=2))
