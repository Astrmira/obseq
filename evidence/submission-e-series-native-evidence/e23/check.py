import csv, hashlib, itertools, json, math, os, sqlite3, struct, subprocess, sys, tempfile
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from zoneinfo import ZoneInfo
from io import BytesIO
for path in os.environ.get("E23_SITE","").split(os.pathsep):
 if path:sys.path.insert(0,path)
import openpyxl
import pandas as pd

p=Path(__file__).resolve().parent
def canonical(x):return json.dumps(x, sort_keys=True, ensure_ascii=False,separators=(',',':'))
def sh(x):return hashlib.sha256(x if isinstance(x,bytes) else canonical(x).encode()).hexdigest()
for line in (p/'PLAN.sha256').read_text().splitlines():
 h,n=line.split()
 assert sh((p/n).read_bytes())==h,n
P=json.loads((p/'PLAN.json').read_text());A=json.loads((p/'ADAPTER_PLAN.json').read_text())
engines={'sqlite':sqlite3.sqlite_version}
X=json.loads((p/'EXPANSION_PLAN.json').read_text())
A['O3-group-representative']['datafusion']=X['datafusion_group_representative']
try:
 import duckdb
 engines['duckdb']=duckdb.__version__
except ImportError:duckdb=None
try:
 import polars
 engines['polars']=polars.__version__
except ImportError:polars=None
try:
 import datafusion
 engines["datafusion"]=datafusion.__version__
except ImportError:datafusion=None

def sql(engine,rows,query):
 if engine=='datafusion':
  c=datafusion.SessionContext()
  c.register_record_batches('q', [[c.from_pylist([dict(zip(('id','bucket','score','tag'),r)) for r in rows]).collect()[0]]])
  return [list(r.values()) for batch in c.sql(query).collect() for r in batch.to_pylist()]
 if engine=='polars':
  d=polars.DataFrame(rows,schema=['id','bucket','score','tag'],orient='row')
  with polars.SQLContext(q=d,eager=True) as ctx:return list(map(list,ctx.execute(query).rows()))
 c=sqlite3.connect(':memory:') if engine=='sqlite' else duckdb.connect()
 try:
  c.execute('CREATE TABLE q (id INTEGER,bucket VARCHAR,score INTEGER,tag VARCHAR)')
  c.executemany('INSERT INTO q VALUES (?,?,?,?)',rows)
  return list(map(list,c.execute(query).fetchall()))
 finally:c.close()

def literal_enumeration(q,records):
 for order in itertools.permutations(records):
  if q=='O3-top-k':
   yield tuple(tuple(r) for r in sorted(order,key=lambda r:-r[2])[:2])
  else:
   P=sorted(order,key=lambda r:(r[1],-r[2]) if q=='O3-row-number' else (r[1],))
   chosen=[next(r for r in P if r[1]==g) for g in sorted({r[1] for r in P})]
   yield tuple((r[1],r[0]) if q=='O3-group-representative' else (r[1],r[0],r[3]) for r in chosen)

def all_valid(q,rows,answer):
 if len(answer)!=2:return False
 if q=='O3-top-k':
  threshold=sorted((r[2] for r in rows),reverse=True)[1]
  facts={tuple(r) for r in rows}
  return all(tuple(r) in facts and r[2]>=threshold for r in answer) and len({tuple(r) for r in answer})==2 and sorted((r[2] for r in answer),reverse=True)==[r[2] for r in answer] and {tuple(r) for r in rows if r[2]>threshold}<={tuple(r) for r in answer}
 by={g:[r for r in rows if r[1]==g] for g in {r[1] for r in rows}}
 if [r[0] for r in answer]!=sorted(by):return False
 for r in answer:
  S=by[r[0]]
  if q=='O3-row-number':
   m=max(x[2] for x in S);S=[x for x in S if x[2]==m]
  vals=[[x[1],x[0]] if q=='O3-group-representative' else [x[1],x[0],x[3]] for x in S]
  if r not in vals:return False
 return True

def sumcols(R):
 if not R:return []
 return [sum(Fraction(x) for x in col if type(x) in (int,float)) for col in zip(*R)]
def tol(a,b,e):
 if len(a)!=len(b):return False
 return all(len(r)==len(s) and all(math.isclose(x,y,rel_tol=e,abs_tol=0) if type(x) in (int,float) and type(y) in (int,float) else x==y for x,y in zip(r,s)) for r,s in zip(a,b))
def schema(a):return sorted({tuple(type(x).__name__ for x in r) for r in a})
def tests(a,b,H1,H2,intg):
 sa=[canonical(r) for r in a];sb=[canonical(r) for r in b]
 return {'ordered':a==b,'multiset':Counter(sa)==Counter(sb),'set':set(sa)==set(sb),'byte_hash':H1==H2 if H1 and H2 else None,'rtol1e-5':tol(a,b,1e-5),'rtol1e-9':tol(a,b,1e-9),'sum':sumcols(a)==sumcols(b),'rowcount':len(a)==len(b),'schema':schema(a)==schema(b),'sqlite_integrity':intg}

rows=[]; errors=[];cohorts=defaultdict(list)
def arm(case,adapter,tag,value,valid,H=None):
 if not valid:errors.append({'case':case,'adapter':adapter,'arm':tag,'error':'independent reference mismatch','value':value})
 cohorts[case].append({'case':case,'adapter':adapter,'arm':tag,'value':value,'valid':bool(valid),'byte_hash':H})
def native_geometry(rings):
 command=[str(Path('/usr/bin/python3')), '-IB', str(p/'gdal_io.py')]
 data=subprocess.run(command,input=canonical(rings),text=True,capture_output=True,check=True).stdout
 return json.loads(data)
def exact_ring(R):
 assert R[0]==R[-1]
 A=set(map(tuple,R[:-1]));assert len(A)==4
 xx={x for x,y in A};yy={y for x,y in A}
 assert len(xx)==len(yy)==2 and A==set(itertools.product(xx,yy))
 assert all((a[0]==b[0])^(a[1]==b[1]) for a,b in zip(R,R[1:]))
 return tuple(sorted(A))
def csv_token(t):
 b=BytesIO(('x\n'+t+'\n').encode())
 text=next(csv.DictReader(line.decode() for line in b))['x']
 return [[text]],sh(('x\n'+t+'\n').encode()),Fraction(text)
def openxls(serial,mode):
 w=openpyxl.Workbook();c=w.active['A1'];c.value=serial
 if mode=='style':c.number_format='yyyy-mm-dd'
 out=BytesIO();w.save(out)
 # XML content is the compared artifact, avoiding varying ZIP timestamps.
 import zipfile
 raw=out.getvalue()
 with zipfile.ZipFile(BytesIO(raw)) as z: h=sh(b''.join(z.read(n) for n in ('xl/worksheets/sheet1.xml','xl/styles.xml')))
 x=openpyxl.load_workbook(BytesIO(raw),read_only=True,data_only=True).active['A1'].value
 return [[x.isoformat() if isinstance(x,datetime) else x]],h,x

def legal_variants():
 init={r[0]:r for r in P['sql']['rows']}
 for e in sorted(engines):
  for q,query in P['sql']['queries'].items():
   if q=='O3-group-representative':query=A[q][e]
   for i,perm in enumerate(P['sql']['releases']):
    R=[init[j] for j in perm]
    try:
     v=sql(e,R,query)
     exact=tuple(map(tuple,v)) in set(literal_enumeration(q,R))
     assert exact==all_valid(q,R,v), (q,v)
     arm(q,e,i,v,exact)
    except Exception as ex:errors.append(dict(case=q,adapter=e,arm=i,error=type(ex).__name__,message=str(ex).splitlines()[0]))
 for i,t in enumerate(P['formats']['decimal_strings']):
  v,H,w=csv_token(t);arm('O4-exact-numeric-text','python_csv',i,v,w==1,H)
 for s in P['formats']['serials']:
  epoch=datetime(1899,12,31); expected=epoch+timedelta(days=s-int(s>=61))
  for m in ('raw','style'):
   v,H,x=openxls(s,m);arm('O4-date-serial-'+str(s),'openpyxl',m,v,(x==s if m=='raw' else x==expected),H)
 try:
  geom=native_geometry(P['formats']['rings']);engines['gdal']=geom['version']
  for i,(ring,G) in enumerate(zip(P['formats']['rings'],geom['variants'])):
   arm('O4-point-set-and-wkb','gdal-geos',i,G['ring'],G['valid'] and exact_ring(G['ring'])==exact_ring(ring)==exact_ring(P['formats']['rings'][0]),G['wkb_sha256'])
 except (FileNotFoundError,subprocess.CalledProcessError) as ex:errors.append(dict(case='O4-point-set-and-wkb',adapter='gdal',error=type(ex).__name__))
 for q,I in sorted(cohorts.items()):
  I=sorted(I,key=lambda z:(z['adapter'],str(z['arm'])))
  ok=[i for i in I if i['valid']]
  if not ok:continue
  a=ok[0]
  for b in I:
   if a==b:continue
   rows.append(dict(experiment='E2',case=q,adapter=b['adapter'],arm=b['arm'],expected_legal=b['valid'],typed_oracle_pass=b['valid'],tests=tests(a['value'],b['value'],a['byte_hash'],b['byte_hash'],None),gold_arm=f"{a['adapter']}:{a['arm']}",observation=b['value'],gold_observation=a['value']))

def wilson(a,b):
 if not b:return None
 z=1.959963984540054;P=a/b
 c=(P+z*z/(2*b))/(1+z*z/b);v=z*math.sqrt((P*(1-P)+z*z/(4*b))/b)/(1+z*z/b)
 return [round(max(0,c-v),9),round(min(1,c+v),9)]

def e3():
 def add(F,i,a,b,legal,typed,adapter='sqlite',H1=None,H2=None,intg=None,detail=None):
  rows.append(dict(experiment='E3',case=F,adapter=adapter,arm=i,expected_legal=legal,typed_oracle_pass=typed,tests=tests(a,b,H1,H2,intg),observation=b,gold_observation=a,detail=detail))
 for i in P['fault_variants']:
  with tempfile.TemporaryDirectory() as T:
   c=sqlite3.connect(':memory:')
   # F1: compare native columns before/after casting high integer identities.
   n=(1<<54)+i*8
   a=[[n],[n+1]];c.execute('create table ids(n integer)');c.executemany('insert into ids values(?)',a)
   r=list(map(list,c.execute('select cast(n as real) from ids order by rowid')))
   assert [int(y[0]) for y in r]!=[n,n+1]
   add('F1',i,a,r,False,[int(y[0]) for y in r]==[n,n+1])
   # F2: actual equality vs IS on independently enumerated rows.
   L=[(i,10),(None,11)];R=[(i,30),(None,31),(None,32)]
   for t,v in (('l',L),('r',R)):
    c.execute(f'create table {t}(k integer,v integer)');c.executemany(f'insert into {t} values(?,?)',v)
   expect=[[x[1],y[1]] for x in L for y in R if x[0] is not None and y[0] is not None and x[0]==y[0]]
   actual=list(map(list,c.execute('select l.v,r.v from l join r on l.k=r.k order by 1,2')))
   assert actual==expect
   wrong=list(map(list,c.execute('select l.v,r.v from l join r on l.k is r.k order by 1,2')))
   add('F2',i,actual,wrong,False,wrong==expect)
   # F3: confirmed active WAL on owned scratch; sqlite main-file byte check misses logical mutation.
   import shutil
   old=Path(T)/'water.sqlite'; stale=Path(T)/'stale.sqlite'
   with sqlite3.connect(old) as w:
    assert w.execute('pragma journal_mode=wal').fetchone()[0]=='wal'
    w.execute('pragma wal_autocheckpoint=0')
    w.execute('create table vals(k int,v int)');w.execute('insert into vals values(1,?)',(i,));w.commit()
    w.execute('pragma wal_checkpoint(truncate)')
    main0=sh(old.read_bytes())
    w.execute('update vals set v=?',(i+100,));w.commit()
    assert Path(str(old)+'-wal').stat().st_size>0
    live=list(map(list,w.execute('select * from vals')))
    shutil.copyfile(old,stale); main1=sh(stale.read_bytes())
    with sqlite3.connect(stale) as s:
     rec=list(map(list,s.execute('select * from vals')))
     intg=s.execute('pragma integrity_check').fetchone()==('ok',)
    assert live==[[1,i+100]] and rec==[[1,i]]
    add('F3',i,live,rec,False,rec==[[1,i+100]],H1=main0,H2=main1,intg=intg,detail='old main-file digest vs active WAL main-file digest')
   # F4: changed deterministic UDF after reopening a stored generated expression.
   gen=Path(T)/'stored.sqlite'
   con=sqlite3.connect(gen)
   con.create_function('derive',1,lambda x:2*x,deterministic=True)
   con.execute('create table g(x integer,y integer generated always as(derive(x)) stored)')
   con.execute('insert into g(x) values(?)',(i+3,));con.commit();con.close()
   con=sqlite3.connect(gen)
   con.create_function('derive',1,lambda x:2*x+1,deterministic=True)
   v=con.execute('select x,y,derive(x) from g').fetchone();intg=con.execute('pragma integrity_check').fetchone()==('ok',)
   assert v[2]==2*v[0]+1 and v[1]==2*v[0]
   add('F4',i,[[v[0],v[2]]],[[v[0],v[1]]],False,v[1]==2*v[0]+1,intg=intg);con.close()
   # F5: keep and clear are observationally equivalent only in the NULL starting state.
   c.execute('create table intent(k int,v int)');c.execute('insert into intent values(1,null)')
   def effects(command):
    if command=='clear':c.execute('update intent set v=null where k=1')
    return list(map(list,c.execute('select * from intent')))
   a=effects('keep');b=effects('clear');assert a==b
   c.execute('update intent set v=?',(i+4,));a2=effects('keep');b2=effects('clear')
   assert a2==[[1,i+4]] and b2==[[1,None]]
   add('F5',i,a,b,False,b2==[[1,i+4]],detail={'keep_nonnull':a2,'clear_nonnull':b2})
   # F6: same score, independent membership at fixed boundary.
   top=[[1,10+i],[2,9+i]];bad=[[1,10+i],[100+i,9+i]]
   expect={1,2,3};assert {a[0] for a in top}<=expect
   add('F6',i,top,bad,False,{a[0] for a in bad}<=expect,'python_fixture')
   # F7: effect of wrong per-row stale values cancels in the sum.
   c.execute('create table g(k int,v int)');a=[[1,10+i],[2,30-i]]
   c.executemany('insert into g values(?,?)',a);c.execute('update g set v=v+case k when 1 then 3 else -3 end')
   b=list(map(list,c.execute('select * from g order by k')));assert sumcols(a)==sumcols(b)
   add('F7',i,a,b,False,b==a)
   # F8: independently enumerate UTC lifts; pandas native chooses or normalizes.
   t=datetime.fromisoformat(('2024-11-03T01:15','2025-11-02T01:31','2025-03-09T02:18')[i]);z=ZoneInfo('America/New_York')
   lifts={g for f in (0,1) if (g:=t.replace(tzinfo=z,fold=f).astimezone(timezone.utc)).astimezone(z).replace(tzinfo=None)==t}
   assert len(lifts)==(0 if i==2 else 2)
   d=pd.Timestamp(t).tz_localize('America/New_York',ambiguous=(i==0),nonexistent='shift_forward')
   add('F8',i,[[str(t),'reject']],[[str(t),d.isoformat()]],False,len(lifts)==1,'pandas')
   # F9: native storage class is what downstream typeof will see, not mixed numeric equality.
   b,t=c.execute(('select cast(1 as real),typeof(cast(1 as real))','select cast(1 as text),typeof(cast(1 as text))','select cast(1 as real),typeof(cast(1 as real))')[i]).fetchone()
   assert t!='integer'
   add('F9',i,[[1]],[[b]],False,type(b) is int,detail={'native_typeof':t})
   # F10: exact planar dyadic coverage can be lost when an edge is snapped.
   X=Fraction(17+i,16);q0=Fraction(33+i*2,32);extent=round(X)
   expected=0<=q0<=X;after=0<=q0<=extent
   assert expected and not after
   add('F10',i,[[int(expected)]],[[int(after)]],False,after==expected,'python_fraction_control')
   c.close()

def main():
 legal_variants();e3()
 assert all(r['typed_oracle_pass']==r['expected_legal'] for r in rows)
 group={}
 for exp in ['E2','E3']:
  block=[r for r in rows if r['experiment']==exp and r['expected_legal']==(exp=='E2')]
  for rule in ['typed_oracle',*rows[0]['tests']]:
   V=[r['typed_oracle_pass'] if rule=='typed_oracle' else r['tests'][rule] for r in block]
   K=[v for v in V if v is not None]
   count=sum((not v) if exp=='E2' else bool(v) for v in K)
   group[exp+'/'+rule]={'metric': 'false_reject' if exp=='E2' else 'false_accept','events':count,'assessed':len(K),'na':len(V)-len(K),'wilson95':wilson(count,len(K))}
 versions={**engines,'python':sys.version.split()[0],'pandas':pd.__version__,'openpyxl':openpyxl.__version__}
 if '--csv' in sys.argv:
  w=csv.writer(sys.stdout);w.writerow(['experiment','cohort','case','adapter','arm','expected_legal','typed_oracle','test','accepts'])
  for r in rows:
   for test,v in [('typed_oracle',r['typed_oracle_pass']),*r['tests'].items()]:
    w.writerow([r['experiment'],'authored_development',r['case'],r['adapter'],r['arm'],r['expected_legal'],r['typed_oracle_pass'],test,'NA' if v is None else int(v)])
 else:print(json.dumps({'plan_hash':sh((p/'PLAN.json').read_bytes()),'cohort':'authored_development','engine_versions':versions,'observations':rows,'errors':errors,'comparators':group},indent=2))
if __name__=='__main__':main()
