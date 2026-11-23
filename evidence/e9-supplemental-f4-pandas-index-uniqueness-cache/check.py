import csv,hashlib,json,os,subprocess,sys
from pathlib import Path
P=Path(__file__).resolve().parent
def native():
 import pandas as p,numpy as n
 rows=[]
 for offset in (0,10,-20):
  data=[x+offset for x in (1,1,2,3,4)]
  ref=data[2:]
  idx=p.Index(data)
  assert idx.is_unique==False
  warm=idx[2:].copy()
  cold=p.Index(data)[2:].copy()
  fresh=p.Index(ref)
  dup=p.Index(data)[:3].copy()
  assert tuple(warm)==tuple(cold)==tuple(fresh)==tuple(ref)
  expected=len(set(ref))==len(ref)
  assert expected and cold.is_unique and fresh.is_unique and not dup.is_unique
  rows.append(dict(offset=offset,values=ref,warmed_child=bool(warm.is_unique),unwarmed_child=bool(cold.is_unique),fresh_equals=bool(warm.equals(fresh)),expected=expected))
 print(json.dumps(dict(pandas=p.__version__,numpy=n.__version__,rows=rows),sort_keys=True))
if sys.argv[1:] == ['native']:
 native()
else:
 root,roster=map(Path,sys.argv[1:])
 b=roster.read_bytes(); assert hashlib.sha256(b).hexdigest()==(P/'ROSTER.sha256').read_text().strip()
 urls={r['url'].rstrip('/') for r in csv.DictReader(b.decode().splitlines())}
 assert len(urls)==300 and 'https://github.com/pandas-dev/pandas/issues/57911' not in urls
 out={}
 for ver in ('2.2.2','2.3.3','3.0.0'):
  env={**os.environ,'PYTHONPATH':str((root/ver).resolve()),'PYTHONNOUSERSITE':'1'}
  d=json.loads(subprocess.check_output([sys.executable,'-sB',str(Path(__file__).resolve()),'native'],env=env,text=True))
  assert d['pandas']==ver and d['numpy']=='2.3.5'
  assert all(x['warmed_child']==(ver=='3.0.0') and x['fresh_equals'] for x in d['rows'])
  out[ver]=d
 print(json.dumps(out,sort_keys=True,indent=2))
