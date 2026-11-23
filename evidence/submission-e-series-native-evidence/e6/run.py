import csv,ctypes,hashlib,itertools,json,math,os,platform,random,resource,sqlite3,statistics,struct,subprocess,sys,time
from collections import Counter
from fractions import Fraction
from pathlib import Path
D=Path(__file__).resolve().parent
SCALES_SQL=(1000,10000,100000,1000000)
SCALES_GEO=(1000,10000,100000)
METHODS={
 'O1':('sqlite_native_read','raw_file_sha256','sqlite_backup_only','sqlite_backup_logical'),
 'O2':('sqlite_native_consumer','latest_epoch_only','epoch_dependency_exact'),
 'O3-topk':('sqlite_native_topk','ordered_gold','truncation_exact'),
 'O3-group':('sqlite_native_group','ordered_gold','representative_exact'),
 'O4':('geos_native_orientation','raw_binary64_determinant','fraction_exact','dyadic_filter_exact')
}
Q='SELECT id,score FROM records ORDER BY score DESC,id DESC LIMIT 128'
QG='SELECT g,id,val FROM records GROUP BY g ORDER BY g'
GG='SELECT g,id,val FROM records r WHERE id=(SELECT max(id) FROM records m WHERE m.g=r.g) ORDER BY g'
# Native variant query for representative rows avoids an unindexed quadratic scan.
GV='SELECT m.g,r.id,r.val FROM (SELECT g,max(id) id FROM records GROUP BY g) m JOIN records r USING(id) ORDER BY m.g'
def rd(n):
 for i in range(1,n+1):yield (i,i%7,i%257,(i*2654435761)%104729,11,i%5)
SCHEMA='CREATE TABLE records(id INTEGER PRIMARY KEY,score INTEGER NOT NULL,g INTEGER NOT NULL,val INTEGER NOT NULL,epoch INTEGER NOT NULL,dep INTEGER NOT NULL)'
def make(n):
 f=D/f'data-{n}.sqlite'
 if f.exists():return
 db=sqlite3.connect(f);db.execute(SCHEMA);db.executemany('INSERT INTO records VALUES(?,?,?,?,?,?)',rd(n));db.commit();db.close()
def sha(f):
 h=hashlib.sha256()
 with f.open('rb') as r:
  while b:=r.read(1024*1024):h.update(b)
 return h.hexdigest()
def drain(f):
 with f.open('rb') as r:
  while r.read(1024*1024):pass
def logical(db):
 h=hashlib.sha256();h.update(db.execute("SELECT sql FROM sqlite_master WHERE name='records'").fetchone()[0].encode('ascii')+b'\0')
 p=struct.Struct('>6q')
 for r in db.execute('SELECT id,score,g,val,epoch,dep FROM records ORDER BY id'):
  h.update(p.pack(*r))
 return h.hexdigest()
def reference_logical(n):
 h=hashlib.sha256(SCHEMA.encode('ascii')+b'\0')
 for r in rd(n):h.update(b''.join(x.to_bytes(8,'big',signed=True) for x in r))
 return h.hexdigest()
def topk(db,result):
 if len(result)!=128 or len({i for i,k in result})!=128:return False
 scores=[];present={}
 need=dict(result)
 for i,k in db.execute('SELECT id,score FROM records'):
  scores.append(k)
  if i in need:present[i]=k
 if present!=need:return False
 k=sorted(scores,reverse=True)[127]
 return all(x>=k for _,x in result) and sum(x>k for x in scores)==sum(x>k for _,x in result) and all(result[j][1]>=result[j+1][1] for j in range(127))
def reps(db,result):
 want={g:(i,v) for g,i,v in result}
 if len(want)!=len(result):return False
 present=set();found=set()
 for g,i,v in db.execute('SELECT g,id,val FROM records'):
  present.add(g)
  if want.get(g)==(i,v):found.add(g)
 return present==found==set(want)
def fresh(db,n):
 ct=0
 for i,ep,d in db.execute('SELECT id,epoch,dep FROM records ORDER BY id'):
  ct+=1
  if i!=ct or ep!=11 or d!=i%5:return False
 return ct==n
ETA=math.nextafter(0.,math.inf)
def coords(i):
 j=i%10
 if j==0:return (0.,0.,ETA,0.,0.,ETA)
 if j==1:return (0.,0.,1.,1.,3.,3.)
 if j==2:return (0.,0.,0.,ETA,ETA,0.)
 x=float(i%197)
 return (x,x,x+2.,x+1.,x+1.,x+(3. if j%2 else -2.))
def expect(i):
 j=i%10
 return 0 if j==1 else (1 if j==0 or (j>2 and j%2) else -1)
def sign(y):return int(y>0)-int(y<0)
def exact(A):
 x,y,z,w,a,b=map(Fraction,A)
 return sign((z-x)*(b-y)-(w-y)*(a-x))
def naive(A):
 x,y,z,w,a,b=A
 return sign((z-x)*(b-y)-(w-y)*(a-x))
def outward(a,b):
 if not math.isfinite(a) or not math.isfinite(b):raise OverflowError
 a,b=math.nextafter(a,-math.inf),math.nextafter(b,math.inf)
 if not math.isfinite(a) or not math.isfinite(b):raise OverflowError
 return a,b
def sub(A,B):return outward(A[0]-B[1],A[1]-B[0])
def mul(A,B):
 s=[x*y for x in A for y in B]
 if not all(map(math.isfinite,s)):raise OverflowError
 return outward(min(s),max(s))
def filtered(A,C):
 x,y,z,w,a,b=A
 if x==z==a or y==w==b or len({(x,y),(z,w),(a,b)})<3:C[0]+=1;return 0
 J=[(v,v) for v in A]
 try:
  l,h=sub(mul(sub(J[2],J[0]),sub(J[5],J[1])),mul(sub(J[3],J[1]),sub(J[4],J[0])))
  if l>0 or h<0:C[1]+=1;return 1 if l>0 else -1
 except OverflowError:C[3]+=1
 else:C[2]+=1
 return exact(A)
def geos():
 L=ctypes.CDLL('libgeos_c.so.1')
 argc=ctypes.CFUNCTYPE(None,ctypes.c_char_p)
 cb=argc(lambda _:None)
 L.initGEOS.argtypes=(argc,argc)
 L.initGEOS(cb,cb)
 L.GEOSversion.restype=ctypes.c_char_p
 q=L.GEOSOrientationIndex;q.argtypes=[ctypes.c_double]*6;q.restype=ctypes.c_int
 return L,cb,q
def geometry(n,m):
 if m=='geos_native_orientation':
  lib,cb,q=geos();fun=lambda x:q(*x)
 elif m=='raw_binary64_determinant':fun=naive
 elif m=='fraction_exact':fun=exact
 else:
  C=[0]*4;fun=lambda x:filtered(x,C)
 return fun,locals().get('C')
def hwm():
 P={}
 for l in Path('/proc/self/status').read_text().splitlines():
  if l.startswith(('VmHWM:','VmRSS:')):P[l.split(':')[0]]=int(l.split()[1])
 return P
def worker(o,m,n,pin,validation=False):
 os.sched_setaffinity(0,{pin})
 cpu0=tuple(os.sched_getaffinity(0));assert cpu0==(pin,)
 t=[];ctx={}
 if o!='O4':
  f=D/f'data-{n}.sqlite';drain(f)
  db=sqlite3.connect(f.resolve().as_uri()+'?mode=ro',uri=True)
  if o=='O3-topk':
   if m!='sqlite_native_topk':ctx['candidate']=db.execute(Q).fetchall()
   if m=='ordered_gold':ctx['gold']=db.execute(Q.replace('id DESC','id ASC')).fetchall()
  if o=='O3-group':
   if m!='sqlite_native_group':ctx['candidate']=db.execute(GV).fetchall()
   if m=='ordered_gold':ctx['gold']=db.execute(QG).fetchall()
  if ctx:
   db.close();db=sqlite3.connect(f.resolve().as_uri()+'?mode=ro',uri=True)
 else:
  fun,C=geometry(n,m)
 if o=='O1' and m in ('sqlite_backup_only','sqlite_backup_logical'):bk=sqlite3.connect(':memory:')
 P=hwm();wall=time.perf_counter_ns();cpu=time.process_time_ns()
 if o=='O1':
  if m=='sqlite_native_read':ans=db.execute('SELECT count(*),sum(val) FROM records').fetchone()
  elif m=='raw_file_sha256':ans=sha(f)
  else:
   db.backup(bk)
   ans=logical(bk) if m=='sqlite_backup_logical' else None
 elif o=='O2':
  if m=='sqlite_native_consumer':ans=db.execute('SELECT sum(val) FROM records WHERE val%17=0').fetchone()
  elif m=='latest_epoch_only':ans=db.execute('SELECT max(epoch) FROM records').fetchone()[0]==11
  else:ans=fresh(db,n)
 elif o=='O3-topk':
  if m=='sqlite_native_topk':ans=db.execute(Q).fetchall()
  elif m=='ordered_gold':ans=ctx['candidate']==ctx['gold']
  else:ans=topk(db,ctx['candidate'])
 elif o=='O3-group':
  if m=='sqlite_native_group':ans=db.execute(GV).fetchall()
  elif m=='ordered_gold':ans=ctx['candidate']==ctx['gold']
  else:ans=reps(db,ctx['candidate'])
 else:
  ans=bytearray(fun(coords(i))+1 for i in range(n))
 cpu=time.process_time_ns()-cpu;wall=time.perf_counter_ns()-wall;M=hwm()
 if o=='O4':
  expected=bytearray(expect(i)+1 for i in range(n));bad=sum(a!=b for a,b in zip(ans,expected))
  valid=not bad if 'exact' in m else True
  verdict=f'mismatches={bad}'
  if C is not None:verdict+=';structural,interval,zero,overflow='+','.join(map(str,C))
 elif m=='ordered_gold':
  valid=ans is False;verdict=str(ans)
 elif m in ('truncation_exact','representative_exact','epoch_dependency_exact','latest_epoch_only'):
  valid=ans is True;verdict=str(ans)
 elif m=='sqlite_backup_only':
  valid=bk.execute('SELECT count(*) FROM records').fetchone()[0]==n;verdict='copied_count='+str(n)
 elif m=='sqlite_backup_logical':
  # Compare against deterministic independent manifest outside timed segment.
  valid=(ans==REFERENCE[str(n)]['logical']);verdict=ans
 elif m=='raw_file_sha256':
  valid=(ans==REFERENCE[str(n)]['physical']);verdict=ans
 elif m=='sqlite_native_read':
  valid=list(ans)==REFERENCE[str(n)]['aggregate'];verdict=repr(ans)
 elif m=='sqlite_native_consumer':
  valid=ans[0]==REFERENCE[str(n)]['consumer'];verdict=repr(ans)
 elif m=='sqlite_native_topk':
  # Generator embeds score 6 and ID descending tie break.
  ids=[i for i in range(n,0,-1) if i%7==6][:128]
  valid=(ans==[(i,6) for i in ids]);verdict='native_rows='+str(len(ans))
 else:
  expected=[]
  for g in range(257):
   i=n-((n-g)%257)
   if i>0:expected.append((g,i,(i*2654435761)%104729))
  valid=ans==expected;verdict='native_rows='+str(len(ans))
 assert valid,(o,m,n,verdict)
 return dict(oracle=o,method=m,n=n,wall_ns=wall,cpu_ns=cpu,rss_setup_kib=P['VmRSS'],hwm_setup_kib=P['VmHWM'],
             hwm_after_kib=M['VmHWM'],hwm_increase_kib=max(0,M['VmHWM']-P['VmHWM']),validation=verdict,
             raw_valid=valid,pin=pin)
def refs():
 R={}
 for n in SCALES_SQL:
  make(n)
  total=c=0
  for i,k,g,v,e,d in rd(n):
   total+=v
   if v%17==0:c+=v
  R[str(n)]={'logical':reference_logical(n),'physical':sha(D/f'data-{n}.sqlite'),'aggregate':[n,total],'consumer':c}
 (D/'manifest.json').write_text(json.dumps(R,indent=2,sort_keys=True)+'\n')
def run():
 plan=json.loads((D/'PLAN.json').read_text())
 assert sha(D/'run.py')==plan['impl_sha256']
 jobs=[(o,m,n,r) for o,ml in METHODS.items() for m in ml for n in (SCALES_GEO if o=='O4' else SCALES_SQL) for r in range(5)]
 random.Random(251113).shuffle(jobs)
 with (D/'raw.csv').open('w',newline='') as f:
  writer=None
  for o,m,n,r in jobs:
   Z=json.loads(subprocess.check_output([sys.executable,'-IB',__file__,'trial',o,m,str(n),str(plan['pin'])]))
   Z['repeat']=r
   if writer is None:writer=csv.DictWriter(f,fieldnames=Z.keys());writer.writeheader()
   writer.writerow(Z);f.flush()
if __name__=='__main__':
 assert sys.float_info.radix==2 and sys.float_info.mant_dig==53 and ETA.hex()=='0x0.0000000000001p-1022'
 if sys.argv[1]=='refs':refs()
 elif sys.argv[1]=='suite':run()
 else:
  REFERENCE=json.loads((D/'manifest.json').read_text())
  _,_,o,m,n,pin=sys.argv
  print(json.dumps(worker(o,m,int(n),int(pin))))
