import os,sys,tempfile,hashlib,subprocess,shutil,json
from pathlib import Path
P=Path(__file__).resolve().parent
K=json.loads(Path(sys.argv[1]).read_text())
assert set(K)=={'duckdb143','legacy_more','arrow26_polars21','postgres_bin','gdal_python','spatial143'}
K={k:Path(v).resolve(strict=True) for k,v in K.items()}
D=[];proof={}
def sha(f):
 with f.open('rb') as a:return hashlib.file_digest(a,'sha256').hexdigest()
for row in (P/'BUNDLE.sha256').read_text().splitlines():
 h,f=row.split();assert sha(P/f)==h,f
assert sha(K['spatial143'])=='bd3077ba46c524a0440c810ae4067cee29e82ce4d95f40c44cfee1a5087d4afe'
with tempfile.TemporaryDirectory(prefix='e7-original-native-') as t:
 T=Path(t);B=T/'data';shutil.copytree(P/'bundle',B)
 E=B/'e1/input';E.mkdir(parents=True)
 for target,key in [('duck143','duckdb143'),('more','legacy_more')]: (E/target).symlink_to(K[key],target_is_directory=True)
 Sc=B/'e7-scored'
 old=Path('/tmp/pvl-eab-submission/e1/input/duck143')
 def exact_path_sub(src,old,new):
  txt=src.read_text();assert txt.count(str(old))==1
  src.write_text(txt.replace(str(old),str(new)))
 for k in ('f6','f9'):exact_path_sub(B/k/'run.py',old,K['duckdb143'])
 exact_path_sub(B/'o4-points'/'pointset-scoped.py','/tmp/pvl-eab-submission/e7-scored/BLIND.json',Sc/'BLIND.json')
 (B/'o4-points/spatial.duckdb_extension').symlink_to(K['spatial143'])
 (T/'scratch').mkdir()
 def run(pkg,script,args=(),py=sys.executable,env=None):
  cwd=B/pkg
  r=subprocess.run([str(py),'-B',script,*map(str,args)],cwd=cwd,env={**os.environ,**(env or {})},capture_output=True,timeout=120,check=False)
  if r.returncode:
   sys.stderr.buffer.write(r.stderr);r.check_returncode()
  assert r.stdout.strip()
  return r.stdout
 def expected(pkg,f):return (P/'bundle'/pkg/f).read_bytes()
 def chk(pkg,name,got,selector=None):
  want=expected(pkg,name);mode='exact_bytes'
  if selector:
   assert selector(json.loads(got))==selector(json.loads(want)),(pkg,name)
   mode='typed_coverage_and_status_projection'
  else:assert got==want,(pkg,name)
  D.append(dict(stage=pkg+'/'+name,comparison=mode,expected_sha256=hashlib.sha256(want).hexdigest()))
  return json.loads(got)
 def cover(k,ids):
  for i in set(ids):proof.setdefault(i,[]).append(k)
 for pkg,alias in [('e7-native','f12'),('e7-native-f34','f34')]:
  got=chk(pkg,'MEASURED.json',run(pkg,'run.py'))
  cover(alias,[r['case_id'] for r in got['rows'] if r['arm']=='exact' and r['status']=='valid'])
 for pkg,extra,kind in [('f5',(K['postgres_bin'],),'cases'),('f6',(),'cases'),('f7',(K['duckdb143'],),None),('f9',(),'results'),('f10',(),'results')]:
  v=chk(pkg,'RESULT.json',run(pkg,'run.py',(Sc,*extra)))
  if pkg=='f7':
   for en,res in v['engine_results'].items():cover('f7_'+en,res['observations'])
  else:cover('f5_sqlite_and_postgresql' if pkg=='f5' else pkg,v[kind])
 rawf8=run("f8","native.py",(Sc/"BLIND.json",),env={"PYTHONPATH":str(K["arrow26_polars21"])})
 chk("f8","NATIVE.json",rawf8)
 (B/"f8/NATIVE.json").write_bytes(rawf8)
 v=chk('f8','RESULT.json',run('f8','check.py',(Sc,)))
 for x in v['native_decisions']:cover('f8_'+x['scope']+'_'+x['adapter'],[x['case_id']])
 def o3_proj(x):return x['engine_versions'],sorted((r['case_id'],r['engine'],r['arm'],r['status']) for r in x['rows'])
 o3=chk('e7-native-o3','MEASURED.json',run('e7-native-o3','run.py'),o3_proj)
 cover('o3_sql',[r['case_id'] for r in o3['rows'] if r['arm']=='exact' and r['status']=='valid'])
 z=chk('e7-native-o3','POLARS-MEASURED.json',run('e7-native-o3','polars_bridge.py'),lambda u:(u['polars_version'],sorted((r['case_id'],r['status']) for r in u['rows'])))
 cover('o3_polars_eager',[r['case_id'] for r in z['rows'] if r['status']=='valid'])
 v=run('e7-native-o4-wkb','parser.py',py=K['gdal_python'])
 chk('e7-native-o4-wkb','MEASURED.json',v)
 (B/'e7-native-o4-wkb/MEASURED.json').write_bytes(v)
 z=chk('e7-native-o4-wkb','SCORES.json',run('e7-native-o4-wkb','score.py'))
 cover('o4_wkb',[r['case_id'] for r in z['scores'] if r['method'] in ('gdal_typed','geos_typed') and r['status']=='correct'])
 zz=chk('o4-pg','RESULT.json',run('o4-pg','run.py',(Sc,K['postgres_bin'],T/'scratch')))
 cover('o4_pg_scalar',[a for a,v in zz['cells'].items() if v['native'] in ('equal','unequal','invalid')])
 v=chk('o4-points','POINTSET-SCOPED.json',run('o4-points','pointset-scoped.py',env={'PYTHONPATH':str(K['duckdb143'])}))
 cover('o4_pointset',[r['case_id'] for r in v])
 original={r['case_id'] for r in json.loads((Sc/'BLIND.json').read_bytes())}
 stored=json.loads(expected('ledger','RESULT.json'))
 assert len(original)==108 and original==set(proof)==set(stored['native_proof_aliases'])
 assert {k:set(v) for k,v in proof.items()}=={k:set(v) for k,v in stored['native_proof_aliases'].items()}
 print(json.dumps(dict(native_reexecution_stages=D,original_cases=len(proof),missing=[],support=proof),indent=2,sort_keys=True))
