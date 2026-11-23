import openpyxl as x
import tempfile,pathlib,json,hashlib
def fingerprint(rows):
 return hashlib.sha256(json.dumps(['typed-patch/v1',sorted(rows)],separators=(',',':')).encode()).hexdigest()
with tempfile.TemporaryDirectory() as tmp:
 out={}
 for a in ('A','B','B-repacked'):
  w=x.Workbook()
  w.active.append(['fid','op','value'])
  rows=[[11,'WRITE',0],[12,'CLEAR' if a=='A' else 'KEEP',None],[13,'KEEP' if a=='A' else 'CLEAR',None]]
  for r in reversed(rows) if a=='B-repacked' else rows:w.active.append(r)
  if a=='B-repacked':w.properties.creator='unrelated'
  p=pathlib.Path(tmp)/(a+'.xlsx');w.save(p)
  r=x.load_workbook(p,read_only=True,data_only=True)
  actual=[list(row) for row in r.active.iter_rows(min_row=2,max_col=3,values_only=True)]
  assert sorted(actual)==rows
  out[a]={'patch':actual,'semantic':fingerprint(actual)}
  r.close()
 assert out['A']['semantic']!=out['B']['semantic']==out['B-repacked']['semantic']
 print(json.dumps({'version':x.__version__,'snapshots':out},sort_keys=True))
