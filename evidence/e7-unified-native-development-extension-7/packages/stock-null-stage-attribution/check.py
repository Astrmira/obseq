import ast,hashlib,json,math,subprocess,sys,tempfile
from pathlib import Path
import pandas
D=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert digest(D/'PLAN.json')==(D/'PLAN.sha256').read_text().split()[0]
P=json.loads((D/'PLAN.json').read_text())
src=sys.argv[1]; assert digest(src)==P['cwi_source_sha256']
arrow=sys.argv[2];sys.path.insert(0,arrow)
import pyarrow as pa
x=P['author_controls']
def typed(t):
  vals=[]
  for row in t.splitlines():
    k,v=row.split('\t'); vals.append((int(k),None if v=='NULL' else float(v)))
  a=pa.array([v for k,v in vals],type=pa.float64(),from_pandas=False)
  return dict(ids=[k for k,v in vals],valid=[b.as_py() for b in a.is_valid()],values=[None if v is None else 'valid_NaN' if math.isnan(v) else v for k,v in vals],validity_byte=a.buffers()[0].to_pybytes().hex() if a.buffers()[0] else None)
typed_={k:typed(t) for k,t in x.items()}
assert typed_['swap']['ids']==typed_['reference']['ids'] and sum(typed_['swap']['valid'])==sum(typed_['reference']['valid'])
assert typed_['valid_nan']['values'][1]=='valid_NaN' and typed_['valid_nan']['valid'][1]
m=[]
with tempfile.TemporaryDirectory() as f:
  base=Path(f);dtypes={}
  for k,t in x.items():
    b=base/(k+'.tsv');b.write_text(t)
    df=pandas.read_csv(b,sep='\t',header=None)
    dtypes[k]={'dtypes':list(map(str,df.dtypes)),'pandas_null_mask':df[1].isna().tolist()}
  for k in ['swap','finite','valid_nan']:
   for i,j in [('reference',k),(k,'reference')]:
    r=subprocess.run([sys.executable,'-IB',src,str(base/(i+'.tsv')),str(base/(j+'.tsv'))],capture_output=True,text=True)
    v=ast.literal_eval(r.stdout.strip());assert not r.stderr and r.returncode==int(v['class']=='match')
    m.append(dict(reference=i,candidate=j,stock_class=v['class'],exit=r.returncode,
      typed_values_equal=typed_[i]['values']==typed_[j]['values'],typed_validity_equal=typed_[i]['valid']==typed_[j]['valid']))
assert [r['stock_class'] for r in m]==['match','match','diff','diff','match','match']
assert all(not r['typed_values_equal'] for r in m)
assert dtypes['reference']==dtypes['valid_nan'] and dtypes['reference']['dtypes'][1]=='float64'
B=[json.loads(subprocess.check_output([sys.executable,'-IB',str(D/'duck.py'),site])) for site in sys.argv[3:]]
assert [b['duckdb'] for b in B]==P['duckdb_versions']
print(json.dumps(dict(cwi_source_sha256=digest(src),pandas=pandas.__version__,arrow=pa.__version__,pandas_parse=dtypes,typed=typed_,cwi_trials=m,duckdb_trials=B),indent=2))
