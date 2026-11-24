import os,sys,pathlib,random,time,subprocess,json
sys.path.insert(0,'/tmp/pvl-eab-submission/e1/input/duck143')
import duckdb
root=pathlib.Path(os.getenv("H2O_ROOT","/workspace/shared/eab-h2o-group100m-stream"))
data=root/'native-100m-hive'
stock=root.parent/'eab-h2o/groupby-duckdb.py'
def lit(s):return "'"+str(s).replace("'","''")+"'"
def src(path):return f"read_parquet({lit(path)}, hive_partitioning=true)"
def setup():
 c=duckdb.connect(config={'threads':'1','memory_limit':'400MB','max_temp_directory_size':'0B','preserve_insertion_order':'false'})
 c.execute(f"CREATE VIEW x AS SELECT id1,CAST(v1 AS INTEGER) v1,ordinal FROM {src(data/'id1=*/*.parquet')};CREATE TABLE epoch(token BIGINT); INSERT INTO epoch VALUES (0); CREATE TABLE edits(lineage INTEGER,id1 VARCHAR,ordinal BIGINT,v1 INTEGER,unused INTEGER,PRIMARY KEY(lineage,id1,ordinal));CREATE VIEW candidate AS SELECT x.id1,coalesce(e.v1,x.v1) v1,x.ordinal FROM x LEFT JOIN edits e ON e.id1=x.id1 AND e.ordinal=x.ordinal AND e.lineage=1;")
 return c
def epoch(c):return c.execute('select token from epoch').fetchone()==(0,)
def producer(c):
 q='SELECT id1, sum(v1) AS v1 FROM x GROUP BY id1'
 assert q.lower() in stock.read_text().lower()
 return c.execute(q.replace(' FROM x',' FROM candidate')+' ORDER BY id1').fetchall()
def exact(c,files):
 n=m=0
 for f in files:
  a=f"SELECT id1,ordinal,CAST(v1 AS INTEGER) v1 FROM {src(f)}"
  b=f"SELECT a.id1,a.ordinal,coalesce(e.v1,a.v1) v1 FROM ({a}) a LEFT JOIN edits e ON e.id1=a.id1 AND e.ordinal=a.ordinal AND e.lineage=1"
  k,d=c.execute(f'SELECT count(*),count(*) FILTER (WHERE a.ordinal IS NULL OR b.ordinal IS NULL OR a.v1 IS DISTINCT FROM b.v1) FROM ({a}) a FULL JOIN ({b}) b USING (id1,ordinal)').fetchone()
  n+=k;m+=d
 return n,m
def controls(c,files):
 f=files[0];a=c.execute(f'SELECT id1,ordinal,v1 FROM {src(f)} where v1 is not null ORDER BY ordinal LIMIT 1').fetchone()
 base=exact(c,[f]);assert base[1]==0
 p0=producer(c)
 def write(delta,unused=False,rollback=False,bypass=False):
  c.execute("BEGIN")
  vals=(None,1) if unused else (a[2]+delta,None)
  c.execute("INSERT OR REPLACE INTO edits VALUES (1,?,?,?,?)",[a[0],a[1],*vals])
  if not (unused or bypass):c.execute("UPDATE epoch SET token=token+1")
  c.execute('ROLLBACK' if rollback else 'COMMIT')
 def chk(ee,dd,pp):
  return dict(epoch=epoch(c),typed_diffs=exact(c,[f])[1],producer_equal=producer(c)==p0)
 out={}
 for name,args,flags,expected in [
 ('irrelevant_column',(0,),dict(unused=True),(True,0,True)),
 ('rolled_back_relevant',(1,),dict(rollback=True),(True,0,True)),
 ('committed_relevant',(1,),{},(False,1,False))]:
  write(*args,**flags);z=chk(*expected);assert tuple(z.values())==expected,(name,z);out[name]=z
 c.execute('UPDATE epoch SET token=0')
 out['simulated_missed_token']=chk(True,1,False);assert tuple(out['simulated_missed_token'].values())==(True,1,False)
 return out
if len(sys.argv)>1:
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 c=setup();files=sorted(data.glob('id1=*/*.parquet'));assert len(files)==100
 arm=sys.argv[1]
 if arm!='control':c.execute('BEGIN')
 t=time.perf_counter()
 if arm=='epoch':z=epoch(c);assert z
 elif arm=='exact':z=exact(c,files);assert z==(100000000,0),z
 elif arm=='producer':p=producer(c);z=[len(p),sum(y for _,y in p)];assert z==[100,299991302],z
 elif arm=='control':z=controls(c,files)
 else:raise ValueError(arm)
 wall=time.perf_counter()-t
 h=int(next(x.split()[1] for x in open('/proc/self/status') if x.startswith('VmHWM:')))
 print(json.dumps(dict(arm=arm,wall_s=wall,vmhwm_kib=h,result=z,duckdb=duckdb.__version__)))
else:
 rng=random.Random(130139)
 for rep in range(5):
  arms=['producer','exact','epoch'];rng.shuffle(arms)
  for arm in arms:
   z=json.loads(subprocess.check_output([sys.executable,__file__,arm],text=True,timeout=180))
   print(json.dumps(dict(rep=rep,**z)),flush=True)
 z=json.loads(subprocess.check_output([sys.executable,__file__,'control'],text=True,timeout=180))
 print(json.dumps(z),flush=True)
