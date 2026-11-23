import datetime as D,hashlib,json,tempfile,sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo,TZPATH
import openpyxl,pandas as pd
m=json.load(open('manifest.json'));assert m['schema']=='civil-time-binding/v1'
zone=m['zone'];z=ZoneInfo(zone);utc=D.timezone.utc
zonefile=next(p for t in TZPATH if (p:=Path(t)/zone).is_file())
provider=pd.Timestamp('2024-01-01').tz_localize(zone).tzinfo.__class__.__module__
assert provider.startswith('pytz')
import pytz
def native_candidates(wall):
 # Here bool chooses daylight/standard interpretation; sort by UTC rather than
 # importing that bool as a general occurrence-order convention.
 candidates=set()
 for ambig in (True,False):
  t=pd.Timestamp(wall).tz_localize(zone,ambiguous=ambig,nonexistent='NaT')
  if not pd.isna(t):candidates.add(int(t.value//10**9))
 return sorted(candidates)
def checked(wall):
 candidates={wall.replace(tzinfo=z,fold=fold).astimezone(utc) for fold in (0,1)}
 return sorted(int(u.timestamp()) for u in candidates if u.astimezone(z).replace(tzinfo=None)==wall)
def bind(cs,occ):
 if not cs:return None,'invalid-gap'
 if len(cs)==1 and occ=='unique':return cs[0],'bound'
 if len(cs)==2 and occ in ('earliest','latest'):
  return cs[0 if occ=='earliest' else 1],'bound'
 return None,'unresolved-occurrence'
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'calendar.xlsx'; w=openpyxl.Workbook();s=w.active
 s.append(['id','wall-local','occurrence'])
 for i,local,occ,exp in m['rows']:s.append([i,D.datetime.fromisoformat(local),occ])
 w.save(p)
 results={}
 with sqlite3.connect(':memory:') as db:
  db.execute('create table t(arm text,id integer,time integer,status text,day text,primary key(arm,id))')
  w=openpyxl.load_workbook(p,read_only=True,data_only=True)
  obs=list(w.active.iter_rows(min_row=2,values_only=True));w.close()
  by_id={x[0]:x for x in m['rows']}
  for i,wall,occ in obs:
   row=by_id[i];assert [wall.isoformat(),occ]==row[1:3]
   cand=native_candidates(wall);assert cand==checked(wall)
   base,status=bind(cand,occ)
   assert base==row[3]
   default=(cand[0] if cand else None,'bound' if cand else 'invalid-gap')
   for arm,(ts,st) in {'typed':(base,status),'collapse-earliest':default}.items():
    db.execute('insert into t values(?,?,?,?,?)',(arm,i,ts,st,wall.date().isoformat()))
  for arm in ('typed','collapse-earliest'):
   got=db.execute('select id,time,status,day from t where arm=? order by id',(arm,)).fetchall()
   bad=[i for i,t,_,_ in got if t!=by_id[i][3]]
   assert bad==([12] if arm=='collapse-earliest' else [])
   results[arm]={'mismatches':bad,'observed':got}
  same=obs[0][1]==obs[1][1];assert same
  day=db.execute("select day,date(time,'unixepoch') from t where arm='typed' and id=16").fetchone()
  assert day==('2024-11-02','2024-11-03')
print(json.dumps({'openpyxl':openpyxl.__version__,'pandas':pd.__version__,'sqlite':sqlite3.sqlite_version,
 'zone':zone,'pandas_zone_provider':provider,'pytz_olson':pytz.OLSON_VERSION,'zoneinfo_file_sha256':hashlib.sha256(zonefile.read_bytes()).hexdigest(),'manifest_sha256':hashlib.sha256(json.dumps(m,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
 'results':results,'row16_local_date_and_utc_date':day},sort_keys=True,indent=2))
