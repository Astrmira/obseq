import json,sys,subprocess,os,hashlib,csv
from datetime import datetime,timedelta
from pathlib import Path
S=Path(__file__).resolve()
IDS=(50946,56134,56147)
URL={n:f'https://github.com/pandas-dev/pandas/issues/{n}' for n in IDS}
def iso(a):return [x.isoformat() for x in a]
def frame():
 import pandas as pd,numpy as np
 rows=[]
 for shift in (-6,0,3):
  a,b=datetime(2021+shift,12,31,0,0,1),datetime(2023+shift,11,1)
  actual=iso(pd.date_range(a,b,freq=pd.offsets.YearEnd()))
  ex=iso(datetime(y,12,31,0,0,1) for y in range(a.year,b.year+1) if a<=datetime(y,12,31,0,0,1)<=b)
  ctl=iso(pd.date_range(a.replace(second=0),b,freq=pd.offsets.YearEnd()))
  assert ctl==iso(datetime(y,12,31) for y in range(a.year,b.year+1) if a.replace(second=0)<=datetime(y,12,31)<=b)
  rows.append(dict(issue=56134,shift=shift,expected=ex,actual=actual,midnight_control=ctl))
  a,b=datetime(2023+shift,10,31),datetime(2021+shift,11,1)
  actual=iso(pd.date_range(a,b,freq=pd.offsets.YearEnd(-1)))
  ex=iso(datetime(y,12,31) for y in range(a.year,b.year-1,-1) if b<=datetime(y,12,31)<=a)
  ctl=iso(pd.date_range(a.replace(month=12,day=31),b.replace(month=12,day=31),freq=pd.offsets.YearEnd(-1)))
  assert ctl==iso(datetime(y,12,31) for y in range(a.year,b.year-1,-1) if b<=datetime(y,12,31)<=a.replace(month=12,day=31))
  rows.append(dict(issue=56147,shift=shift,expected=ex,actual=actual,anchored_start_control=ctl))
 for shift in (0,120,365):
  x=datetime(2021,8,5)+timedelta(days=shift)
  vals=[x+timedelta(days=d) for d in range(6)]+[x+timedelta(days=6,seconds=1)]
  index=pd.DatetimeIndex(vals)
  key=(x+timedelta(days=4))
  expected=max(t for t in vals if t<=key)
  act=index.asof(key.date().isoformat()).isoformat()
  ctrl=index.asof(key).isoformat()
  assert ctrl==expected.isoformat()
  rows.append(dict(issue=50946,shift=shift,expected=expected.isoformat(),actual=act,typed_key_control=ctrl))
 return dict(pandas=pd.__version__,numpy=np.__version__,rows=rows)
if len(sys.argv)==2 and sys.argv[1]=='one':
 print(json.dumps(frame(),sort_keys=True));raise SystemExit
old,fixed,roster=map(Path,sys.argv[1:])
pin='057b0c7256bea60b1da76462e76654d0c978ef950699c11ae7eb9cd8e990383f'
b=roster.read_bytes(); assert hashlib.sha256(b).hexdigest()==pin
fr={r['url'].rstrip('/') for r in csv.DictReader(b.decode().splitlines())}
assert len(fr)==300 and not set(URL.values())&fr
output={}
for v,path in zip(('2.2.3','2.3.3','3.0.0'),(None,old,fixed)):
 env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'};env['PYTHONNOUSERSITE']='1'
 if path: env['PYTHONPATH']=str(path.resolve())
 x=json.loads(subprocess.check_output([sys.executable,'-B',str(S),'one'],env=env,text=True))
 assert x['pandas']==v and x['numpy']=='2.3.5'
 output[v]=x
expected_bad={n:0 for n in IDS}
for v,r in output.items():
 for x in r['rows']:
  if v=='3.0.0':assert x['actual']==x['expected'],x
  else:
   if x['actual']!=x['expected']:expected_bad[x['issue']]+=1
assert expected_bad[50946]>=2 and expected_bad[56134]==6 and expected_bad[56147]==6,expected_bad
assert all(x['actual']!=x['expected'] for v in ('2.2.3','2.3.3') for x in output[v]['rows'] if x['issue']==50946 and x['shift']==0)
print(json.dumps(dict(frozen_roster_sha256=pin,independent_fix_families=2,roster_new=0,observations=output,old_fail_counts=expected_bad,issue_links=URL),indent=2,sort_keys=True))
