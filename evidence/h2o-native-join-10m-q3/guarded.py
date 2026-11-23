"""Candidate monitor. Run only after independent launch authorization/reservation."""
import argparse, hashlib, json, os, pathlib, shutil, subprocess, time
P=pathlib.Path
p=argparse.ArgumentParser();p.add_argument('prerequisites',type=P);p.add_argument('new_disk_workspace',type=P);p.add_argument('--reserved-and-cleared',action='store_true');a=p.parse_args()
assert a.reserved_and_cleared
src=a.prerequisites.resolve();dst=a.new_disk_workspace.resolve()
assert dst.parent.is_dir() and not dst.exists()
GiB=1024**3
def available():
 return int(next(x for x in P('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')).split()[1])*1024
assert shutil.disk_usage(dst.parent).free>=3*GiB and available()>=int(3.7*GiB)
gen=src/'join-generator.R'
assert hashlib.sha256(gen.read_bytes()).hexdigest()=='d59ddc78df4d6114ccc784fa8a3f9678b1977cfd83680767357877fa062dab9d'
dst.mkdir()
rk=src/'root/usr/lib/R';r=rk/'bin/exec/R'
cpu=min(os.sched_getaffinity(0))
argv=['taskset','-c',str(cpu),str(r),'--vanilla','--slave','-f',str(gen),'--args','1e7','0','5','0']
env=os.environ|dict(R_HOME=str(rk),LD_LIBRARY_PATH=str(rk/'lib'),R_LIBS_SITE=str(rk/'site-library'),TMPDIR=str(dst),OMP_NUM_THREADS='1',OMP_THREAD_LIMIT='1')
def status(pid):
 try:return int(next(x for x in P(f'/proc/{pid}/status').read_text().splitlines() if x.startswith('VmRSS:')).split()[1])*1024
 except (FileNotFoundError,StopIteration,ProcessLookupError):return 0
reason=None;peak=0;high=0
with (dst/'generator.log').open('wb') as log:
 t=time.monotonic()
 c=subprocess.Popen(argv,cwd=dst,stdout=log,stderr=subprocess.STDOUT,env=env)
 try:
  while c.poll() is None:
   peak=max(status(c.pid),peak)
   high=max(sum(x.stat().st_size for x in dst.rglob('*') if x.is_file()),high)
   if peak>int(2.5*GiB):reason='rss_guard'
   elif available()<GiB:reason='available_memory_guard'
   elif high>int(1.5*GiB) or shutil.disk_usage(dst).free<2*GiB:reason='disk_guard'
   elif time.monotonic()-t>180:reason='timeout_guard'
   if reason:c.terminate();break
   time.sleep(.2)
  try:rc=c.wait(timeout=3)
  except subprocess.TimeoutExpired:c.kill();rc=c.wait()
 finally:
  if c.poll() is None:c.kill();c.wait()
receipt=dict(exit=rc,guard=reason,sampled_peak_rss=peak,sampled_output_bytes=high,admitted_generator=False)
if rc==0 and reason is None and 'Join datagen of 1e7 rows finished' in (dst/'generator.log').read_text():
 names={'J1_1e7_NA_5_0.csv':10_000_000,'J1_1e7_1e1_5_0.csv':10,'J1_1e7_1e4_5_0.csv':10_000,'J1_1e7_1e7_5_0.csv':10_000_000}
 if {p.name for p in dst.glob('*.csv')}==set(names):
  observed={};
  for k,n in names.items():
   with (dst/k).open('rb') as w:
    header=w.readline().decode('utf-8').strip()
    expected={'J1_1e7_NA_5_0.csv':'id1,id2,id3,id4,id5,id6,v1','J1_1e7_1e1_5_0.csv':'id1,id4,v2','J1_1e7_1e4_5_0.csv':'id1,id2,id4,id5,v2','J1_1e7_1e7_5_0.csv':'id1,id2,id3,id4,id5,id6,v2'}[k]
    count=sum(b.count(b'\n') for b in iter(lambda:w.read(1<<20),b''))
   with (dst/k).open('rb') as w:d=hashlib.file_digest(w,'sha256').hexdigest()
   observed[k]=dict(header=header,expected=expected,rows=count,expected_rows=n,sha256=d)
  receipt['files']=observed;receipt['admitted_generator']=all(x['rows']==x['expected_rows'] and x['header']==x['expected'] for x in observed.values())
(dst/'MONITOR.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
print(json.dumps(receipt))
