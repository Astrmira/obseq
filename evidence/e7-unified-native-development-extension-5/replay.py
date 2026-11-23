import argparse, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path
root=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('ids',nargs='*');p.add_argument('--default-python',default=sys.executable);p.add_argument('--system-python',default='/usr/bin/python3');p.add_argument('--scratch');p.add_argument('--prior-root',type=Path);p.add_argument('--inputs',default=root/'LOCAL-INPUTS.json',type=Path);a=p.parse_args(); inputs=json.loads(a.inputs.read_text()) if a.inputs.is_file() else {}
cases=json.loads((root/'MANIFEST.json').read_text())['cases']; known={r['case_id'] for r in cases}
if set(a.ids)-known:p.error('unknown case ID: '+', '.join(sorted(set(a.ids)-known)))
def execute(case,t):
 id=case['case_id'];pkg=root/'packages'/id
 if not pkg.is_dir():
  if a.prior_root is None:return 'NA_prior_package',id.encode()
  pkg=a.prior_root.resolve()/'packages'/id
 for name,info in case['blobs'].items():
  if not (pkg/name).is_file() or hashlib.sha256((pkg/name).read_bytes()).hexdigest()!=info['sha256']:return 'FAIL_digest',None
 env={**os.environ,'TMPDIR':str(t),'PROJ_NETWORK':'OFF','PYTHONNOUSERSITE':'1'}
 vals={**inputs,'SCRATCH':str(t)}
 try:
  args=[x.format_map(vals) for x in case.get('args',[])]
  sites=[vals[p] for p in case.get('python_path',[])]
 except KeyError as e:return 'NA_input_binding',str(e).encode()
 if any(not Path(x).exists() for x in args+sites):return 'NA_input_path',str(args+sites).encode()
 if sites:env['PYTHONPATH']=os.pathsep.join(sites)
 def run(py,src,stdin=None,is_final=True):
  return subprocess.run([py,'-B' if sites else '-IB',src,*(args if is_final else ())],input=stdin,cwd=pkg,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=70)
 try:
  mode=case['mode']
  i=None
  if mode=='producer-default' or case.get('producer'):
   proc=run(a.system_python if case.get('producer_mode')=='system' else a.default_python,case.get('producer') or 'producer.py',is_final=False)
   if proc.returncode:return 'FAIL_producer',proc.stderr
   i=proc.stdout
  proc=run(a.default_python if mode=='default' else a.system_python,case.get('entry','check.py'),i)
 except (FileNotFoundError, subprocess.TimeoutExpired) as e:return 'NA_runtime',str(e).encode()
 if proc.returncode:return 'FAIL_execution',proc.stderr
 if proc.stdout!=(pkg/case.get('expected','result.json')).read_bytes():return 'FAIL_divergence',proc.stdout
 return 'PASS',None
failed=False
for case in cases:
 if a.ids and case['case_id'] not in a.ids:continue
 with tempfile.TemporaryDirectory(dir=a.scratch) as t:status,detail=execute(case,t)
 print(f"{case['case_id']}\t{case['kind']}\t{status}",flush=True)
 if detail:print(detail.decode(errors='replace')[-1600:],file=sys.stderr)
 failed|=status!='PASS'
sys.exit(failed)
