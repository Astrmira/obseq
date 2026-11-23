import argparse, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path
root=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('ids',nargs='*');p.add_argument('--default-python',default=sys.executable);p.add_argument('--system-python',default='/usr/bin/python3');p.add_argument('--scratch');a=p.parse_args()
cases=json.loads((root/'MANIFEST.json').read_text())['cases']; known={r['case_id'] for r in cases}
if set(a.ids)-known:p.error('unknown case ID: '+', '.join(sorted(set(a.ids)-known)))
def execute(case,t):
 id=case['case_id'];pkg=root/'packages'/id
 for name,info in case['blobs'].items():
  if not (pkg/name).is_file() or hashlib.sha256((pkg/name).read_bytes()).hexdigest()!=info['sha256']:return 'FAIL_digest',None
 env={**os.environ,'TMPDIR':str(t),'PROJ_NETWORK':'OFF','PYTHONNOUSERSITE':'1'}
 def run(py,src,stdin=None):
  return subprocess.run([py,'-IB',src],input=stdin,cwd=pkg,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40)
 try:
  mode=case['mode']
  i=None
  if mode=='producer-default':
   proc=run(a.default_python,'producer.py')
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
