import os,sys,pathlib,time,subprocess,json
sys.path.insert(0,'/tmp/pvl-eab-submission/e1/input/duck143')
import duckdb
path=pathlib.Path(os.getenv('PACKED','/workspace/shared/eab-h2o-group100m-stream/native-100m-hive'))
def q(s):return "'"+str(s).replace("'","''")+"'"
def read(p):return f"read_parquet({q(p)},hive_partitioning=true)"
def setup():
 c=duckdb.connect(config={'threads':'1','memory_limit':'400MB','max_temp_directory_size':'0B','preserve_insertion_order':'false'})
 c.execute("""create table stage(id1 varchar,rid bigint,op utinyint,val integer,primary key(id1,rid),check(op in(0,1,2)),check((op=2)=(val is not null)));
 create table overlay(id1 varchar,rid bigint,v integer,primary key(id1,rid));
 create table receipt(id1 varchar,rid bigint,op utinyint,val integer,primary key(id1,rid),check(op in(0,1,2)),check((op=2)=(val is not null)));""")
 # Four original nonnull rows, same stable producer-bound identity.
 a=c.execute(f"select ordinal,v1 from {read(path/'id1=id001/*.parquet')} where v1 is not null order by ordinal limit 4").fetchall()
 assert len(a)==4
 expected=[('id001',a[0][0],0,None),('id001',a[1][0],1,None),('id001',a[2][0],2,a[2][1]),('id001',a[3][0],2,a[3][1]+1)]
 c.executemany('insert into stage values (?,?,?,?)',expected)
 return c,sorted(expected)
def apply(c,expected):
 c.execute('begin')
 m=c.execute('insert into overlay select id1,rid,val from stage where op<>0 returning id1,rid,v').fetchall()
 assert sorted(m)==sorted((i,r,v) for i,r,op,v in expected if op)
 out=c.execute('insert into receipt select * from stage returning id1,rid,op,val').fetchall()
 assert sorted(out)==expected
 c.execute('commit')
 return len(m),len(out)
def witness(c,expected):
 return c.execute('select * from receipt order by id1,rid').fetchall()==expected
def verify(c,expected,files):
 # Expected projection comes from independent host-side frozen fixture, never receipt/overlay.
 c.execute('create temp table oracle(id1 varchar,rid bigint,op utinyint,val integer,primary key(id1,rid))')
 c.executemany('insert into oracle values (?,?,?,?)',expected)
 n=bad=covered=0
 for f in files:
  n1,b1,hits=c.execute(f"""select count(*),count(*) filter(where
  (case when o.rid is null then b.v1 else o.v end) is distinct from
  (case when e.op is null or e.op=0 then b.v1 when e.op=1 then NULL::INTEGER else e.val end)),
  count(o.rid) from {read(f)} b left join overlay o on b.id1=o.id1 and b.ordinal=o.rid
  left join oracle e on b.id1=e.id1 and b.ordinal=e.rid""").fetchone()
  n+=n1;bad+=b1;covered+=hits
 c.execute('drop table oracle')
 return [n,bad,covered,c.execute('select count(*) from overlay').fetchone()[0]-covered,witness(c,expected)]
def controls(c,e,files):
 f=files[0]
 initial=verify(c,e,[f]);assert initial[1:]==[0,3,0,True],initial
 target=next(z for z in e if z[2]==2)
 c.execute('update receipt set op=0,val=null where id1=? and rid=?',target[:2])
 x=verify(c,e,[f]);assert x[1:]==[0,3,0,False],x
 dest=next(z for z in e if z[2]==2 and z!=target)
 c.execute('update overlay set v=v+1 where id1=? and rid=?',dest[:2])
 y=verify(c,e,[f]);assert y[1:]==[1,3,0,False],y
 return {'baseline':initial,'equal_write_receipt_replaced_with_keep':x,'additional_poststate_change':y}
if len(sys.argv)>1:
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 c,e=setup(); files=sorted(path.glob('id1=*/*.parquet'));assert len(files)==100
 t=time.perf_counter();a=apply(c,e);t1=time.perf_counter();assert a==(3,4)
 w=witness(c,e);t2=time.perf_counter();assert w
 if sys.argv[1]=='control': print(json.dumps(controls(c,e,files)));sys.exit()
 r=verify(c,e,files); t3=time.perf_counter();assert r==[100000000,0,3,0,True],r
 h=lambda:int(next(z.split()[1] for z in open('/proc/self/status') if z.startswith('VmHWM:')))
 print(json.dumps(dict(apply_wall_s=t1-t,witness_wall_s=t2-t1,verify_wall_s=t3-t2,rows=r[0],poststate_diffs=r[1],orphan_overlays=r[3],overlay_rows=a[0],receipt_rows=a[1],vmhwm_kib=h(),duckdb=duckdb.__version__)))
else:
 for i in range(5):
  d=json.loads(subprocess.check_output([sys.executable,__file__,'rep'],timeout=150));print(json.dumps(dict(rep=i,**d)),flush=True)
 print(json.dumps(dict(controls=json.loads(subprocess.check_output([sys.executable,__file__,'control'],timeout=60)))),flush=True)
