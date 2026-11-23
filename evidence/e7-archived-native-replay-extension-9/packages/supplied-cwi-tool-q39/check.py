import ast,csv,hashlib,io,json,math,subprocess,sys,tempfile
from pathlib import Path
import pandas
P=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(P/'PLAN.json')==(P/'PLAN.sha256').read_text().split()[0]
cfg=json.loads((P/'PLAN.json').read_text())
source,reference=sys.argv[1:3]
assert sha(source)==cfg['source_sha256']
assert sha(reference)==cfg['q39_reference_sha256']
z=json.loads(Path(reference).read_text())
def table(rows):
 return [[k[0],k[1],1,float.fromhex(v[0]),float.fromhex(v[1]),k[0],k[1],2,float.fromhex(v[2]),float.fromhex(v[3])] for r in rows for k,v in [(r['key'],r['values'])]]
a,b=[table(z['variants'][k]) for k in ('1','4')]
assert len(a)==len(b)==243 and a!=b
I=(0,1,2,5,6,7);R=(3,4,8,9)
def ordered_keys(X):return [tuple(v[j] for j in I) for v in X]
def independent(x,y):
 if ordered_keys(x)!=ordered_keys(y):return False
 return all(abs(r[j]-s[j])<=3*max(math.ulp(r[j]),math.ulp(s[j])) for r,s in zip(x,y) for j in R)
# Pair-to-pair 3 ULP permits differences of separate 2/1 ULP runs to the exact reference.
c=[x[:] for x in b]; c[0][1]+=1;c[0][6]+=1
d=[x[:] for x in b]; j=next(i for i in R if d[0][i]);d[0][j]*=2
def tsv(r):
 out=io.StringIO();csv.writer(out,delimiter='\t',lineterminator='\n').writerows(r);return out.getvalue()
with tempfile.TemporaryDirectory() as t:
 Q=Path(t);files=[]
 for i,z0 in enumerate((a,b,c,d)):
  n=Q/f'{i}.ans';n.write_text(tsv(z0));files.append(n)
 out=[]
 for name,i,j,X,Y in [
   ('native one to four',0,1,a,b),('native four to one',1,0,b,a),
   ('coherent integer key mutation',0,2,a,c),('large numerical mutation',0,3,a,d)]:
  r=subprocess.run([sys.executable,'-IB',source,str(files[i]),str(files[j])],capture_output=True,text=True)
  v=ast.literal_eval(r.stdout.strip());assert not r.stderr and v['class'] in {'match','diff'} and r.returncode==int(v['class']=='match')
  out.append(dict(arm=name,stock_cwi=v['class'],stock_exit=r.returncode,typed_contract=independent(X,Y)))
 assert [v['stock_cwi'] for v in out]==['match','match','match','diff']
 assert [v['typed_contract'] for v in out]==[True,True,False,False]
 if '--csv' in sys.argv:
  w=csv.DictWriter(sys.stdout,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
 else:print(json.dumps(dict(pandas=pandas.__version__,source_commit=cfg['source_commit'],source_sha256=sha(source),ref_sha256=sha(reference),rows=243,results=out),indent=2))
