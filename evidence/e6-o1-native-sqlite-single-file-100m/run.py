import hashlib,itertools,importlib.util,json,os,random,shutil,sqlite3,subprocess,sys,time
from pathlib import Path
import argparse
from tempfile import TemporaryDirectory
O=Path(__file__).resolve().parents[1]/'submission-e-series-native-evidence/e6'
sp=importlib.util.spec_from_file_location('e6',O/'run.py');orig=importlib.util.module_from_spec(sp);sp.loader.exec_module(orig)
assert orig.sha(O/'run.py')=='2f146c269f343802982992b3856963da02c3fe4f90303022c24b082d0f952fe6'
METHODS=tuple(orig.METHODS['O1'])
args=argparse.ArgumentParser()
args.add_argument('mode',choices=['tiny','build','reference','run','worker'])
args.add_argument('--source',type=Path)
args.add_argument('--n',type=int,default=100_000_000)
args.add_argument('--min-disk-mib',type=int,default=2850)
args.add_argument('--start-repeat',type=int,default=0)
args.add_argument('--end-repeat',type=int,default=5)
args.add_argument('--ref',type=Path)
args.add_argument('--method',choices=METHODS)
a=args.parse_args()
if a.mode!='tiny': assert a.source and a.n==100_000_000
n=a.n
assert sqlite3.sqlite_version=='3.53.1'
def pin():os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
def emit(x):print(json.dumps(x,sort_keys=True),flush=True)
def tiny():
 refs=json.loads((O/'manifest.json').read_text())
 with TemporaryDirectory() as tmp:
  orig.D=Path(tmp)
  orig.make(1000)
  with sqlite3.connect((orig.D/"data-1000.sqlite").as_uri()+"?mode=ro",uri=True) as db:
   assert con_result(db)==(1000,sumval(1000))
  orig.REFERENCE=refs
  for m in METHODS:
   x=orig.worker('O1',m,1000,min(os.sched_getaffinity(0)))
   assert x['raw_valid'] and orig.reference_logical(1000)==refs['1000']['logical']
   emit(dict(method=m,verified_against_original=True))
def source_info(path):
 with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as d:
  assert d.execute("SELECT sql FROM sqlite_master WHERE name='records'").fetchone()[0]==orig.SCHEMA
  assert con_result(d)[0]==n
  pages=d.execute('pragma page_count').fetchone()[0];psz=d.execute('pragma page_size').fetchone()[0]
  assert pages*psz==path.stat().st_size and psz==4096
 return dict(page_count=pages,page_size=psz,file_bytes=path.stat().st_size)
def con_result(d):return d.execute('SELECT count(*),sum(val) FROM records').fetchone()
def build():
 p=a.source.resolve()
 assert not p.exists()
 free=shutil.disk_usage(p.parent).free//2**20
 assert free>=a.min_disk_mib,(free,a.min_disk_mib)
 tmp=p.with_name(p.name+'.partial');assert not tmp.exists()
 pin()
 start=time.monotonic()
 with sqlite3.connect(tmp) as d:
  d.execute(orig.SCHEMA)
  assert d.execute('pragma journal_mode').fetchone()[0]=='delete'
  iterator=orig.rd(n)
  for stop in range(1_000_000,n+1,1_000_000):
   d.executemany('INSERT INTO records VALUES(?,?,?,?,?,?)',itertools.islice(iterator,1_000_000))
   free=shutil.disk_usage(tmp.parent).free//2**20
   if stop%5_000_000==0:emit(dict(phase='insert',rows=stop,current_bytes=tmp.stat().st_size,free_disk_mib=free))
   assert free>=200,('stop before filling disk',stop,free)
  assert d.execute('SELECT max(id) FROM records').fetchone()[0]==n
  d.commit()
 tmp.rename(p)
 emit(dict(phase='sealed_single_source',generation_s=time.monotonic()-start,**source_info(p)))
def sumval(n):
 m=104729
 blocks,tail=divmod(n,m)
 assert __import__('math').gcd(2654435761,m)==1
 return blocks*m*(m-1)//2+sum(i*2654435761%m for i in range(1,tail+1))
def ref():
 pin();f=a.source.resolve()
 # Frozen independent serializer uses Python integer to_bytes, different from measured SQLite + struct.pack.
 h=orig.reference_logical(n)
 emit(dict(n=n,logical=h,physical=orig.sha(f),aggregate=[n,sumval(n)],sqlite=sqlite3.sqlite_version,**source_info(f)))
def worker():
 pin();f=a.source.resolve(); ref=json.loads(a.ref.read_text());assert ref['n']==n and ref['file_bytes']==f.stat().st_size
 if a.method in ('sqlite_backup_only','sqlite_backup_logical'):
  free=int(next(s.split()[1] for s in open('/proc/meminfo') if s.startswith('MemAvailable:')))*1024
  assert free>=f.stat().st_size*1.35+256*2**20,('stop before memory backup',free)
 orig.drain(f)
 db=sqlite3.connect(f.as_uri()+'?mode=ro',uri=True)
 bk=sqlite3.connect(':memory:') if a.method in ('sqlite_backup_only','sqlite_backup_logical') else None
 P=orig.hwm();tm=time.perf_counter_ns();cpu=time.process_time_ns()
 if a.method=='sqlite_native_read':z=list(con_result(db))
 elif a.method=='raw_file_sha256':z=orig.sha(f)
 else:
  db.backup(bk)
  z=orig.logical(bk) if a.method=='sqlite_backup_logical' else None
 cpu=time.process_time_ns()-cpu;tm=time.perf_counter_ns()-tm;M=orig.hwm()
 if a.method=='sqlite_native_read':assert z==ref['aggregate']
 elif a.method=='raw_file_sha256':assert z==ref['physical']
 elif a.method=='sqlite_backup_only':z=list(con_result(bk));assert z==ref['aggregate']
 else:assert z==ref['logical']
 emit(dict(method=a.method,n=n,wall_ns=tm,cpu_ns=cpu,setup_hwm_kib=P['VmHWM'],hwm_kib=M['VmHWM'],valid=True,result=z))
def run():
 for repeat in range(a.start_repeat,a.end_repeat):
  m=list(METHODS);random.Random(251113+repeat).shuffle(m)
  for name in m:
   p=subprocess.run([sys.executable,'-B',__file__,'worker','--source',str(a.source),'--ref',str(a.ref),'--method',name],capture_output=True,text=True,timeout=450)
   if p.returncode:
    sys.stderr.write(p.stderr);p.check_returncode()
   emit(dict(repeat=repeat,**json.loads(p.stdout)))
{'tiny':tiny,'build':build,'reference':ref,'worker':worker,'run':run}[a.mode]()
