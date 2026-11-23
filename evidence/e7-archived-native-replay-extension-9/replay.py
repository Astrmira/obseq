import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
root=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('ids',nargs='*');p.add_argument('--default-python',default=sys.executable);p.add_argument('--system-python',default='/usr/bin/python3');p.add_argument('--scratch');p.add_argument('--prior-root',action='append',type=Path,default=[]);p.add_argument('--include-prior',action='store_true');p.add_argument('--inputs',default=root/'INPUT-ROLES.example.json',type=Path);a=p.parse_args(); inputs=json.loads(a.inputs.read_text()) if a.inputs.is_file() else {}
cases=json.loads((root/'MANIFEST.json').read_text())['cases']
pin=json.loads((root/'BASE-PINS.json').read_text())
base=[]
for x in (5,6,7,8):
 base_blob=(root/f'BASE-{x}.json').read_bytes()
 assert hashlib.sha256(base_blob).hexdigest()==pin['roots'][f'extension-{x}']['manifest_sha256']
 base.extend(json.loads(base_blob)['cases'])
known={r['case_id'] for r in base+cases}
assert len(known)==len(base)+len(cases)
approved={v['manifest_sha256'] for v in pin['roots'].values()}
for path in a.prior_root:
 if not (path/'MANIFEST.json').is_file() or hashlib.sha256((path/'MANIFEST.json').read_bytes()).hexdigest() not in approved:p.error('prior manifest pin mismatch: '+str(path))
if a.include_prior or set(a.ids)&{r['case_id'] for r in base}:cases=base+cases
if set(a.ids)-known:p.error('unknown case ID: '+', '.join(sorted(set(a.ids)-known)))
def execute(case,t):
 id=case['case_id']
 pkg=next((q/'packages'/id for q in [root,*a.prior_root] if (q/'packages'/id).is_dir()),None)
 if pkg is None:return 'NA_package_root',id.encode()
 for name,info in case['blobs'].items():
  if not (pkg/name).is_file() or hashlib.sha256((pkg/name).read_bytes()).hexdigest()!=info['sha256']:return 'FAIL_digest',None
 env={**os.environ,'TMPDIR':str(t),'PROJ_NETWORK':'OFF','PYTHONNOUSERSITE':'1','OPENBLAS_NUM_THREADS':'1'}
 vals={**inputs,'SCRATCH':str(t)}
 try:
  args=[x.format_map(vals) for x in case.get('args',[])]
  sites=[vals[p] for p in case.get('python_path',[])]
 except KeyError as e:return 'NA_input_binding',str(e).encode()
 if any(not Path(x).exists() for x in args+sites):return 'NA_input_path',str(args+sites).encode()
 archive=pkg
 if case.get('copy_package_to_scratch'):
  pkg=Path(t)/'package'
  for name in case['blobs']:
   dst=pkg/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(archive/name,dst)
 for home,kind in ((pkg,'package_input_links'),(Path(t),'scratch_input_links')):
  for name,role in case.get(kind,{}).items():
   if role not in vals or not Path(vals[role]).exists():return 'NA_input_path',role.encode()
   (home/name).symlink_to(Path(vals[role]).resolve())
 if sites:env['PYTHONPATH']=os.pathsep.join(sites)
 def run(py,src,stdin=None,is_final=True):
  return subprocess.run([py,'-B' if sites else '-IB',src,*(args if is_final else ())],input=stdin,cwd=pkg,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=case.get('timeout',70))
 try:
  if case.get('arms'):
   for arm in case['arms']:
    site=vals[arm['site']]
    if not Path(site).is_dir():return 'NA_input_path',site.encode()
    r=subprocess.run([a.default_python,'-B',arm['entry']],cwd=pkg,env={**env,'PYTHONPATH':site},stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=70)
    if r.returncode:return 'FAIL_execution',r.stderr
    if r.stdout!=(pkg/arm['expected']).read_bytes():return 'FAIL_divergence',r.stdout
   return 'PASS',None
  mode=case['mode']
  i=None
  if mode=='producer-default' or case.get('producer'):
   proc=run(a.system_python if case.get('producer_mode')=='system' else a.default_python,case.get('producer') or 'producer.py',is_final=False)
   if proc.returncode:return 'FAIL_producer',proc.stderr
   i=proc.stdout
  proc=run(a.default_python if mode=='default' else a.system_python,case.get('entry','check.py'),i)
 except (FileNotFoundError, subprocess.TimeoutExpired, KeyError) as e:return 'NA_runtime',str(e).encode()
 if proc.returncode:return 'FAIL_execution',proc.stderr
 if proc.stdout!=(archive/case.get('expected','result.json')).read_bytes():return 'FAIL_divergence',proc.stdout
 for name in case.get('exact_generated',[]):
  if not (pkg/name).is_file() or (pkg/name).read_bytes()!=(archive/name).read_bytes():return 'FAIL_generated',name.encode()
 return 'PASS',None
failed=False
for case in cases:
 if a.ids and case['case_id'] not in a.ids:continue
 with tempfile.TemporaryDirectory(dir=a.scratch) as t:status,detail=execute(case,t)
 print(f"{case['case_id']}\t{case['kind']}\t{status}",flush=True)
 if detail:print(detail.decode(errors='replace')[-1600:],file=sys.stderr)
 failed|=status!='PASS'
sys.exit(failed)
