import argparse,collections,json,os,pathlib,random,subprocess,sys,time
import duckdb
ns=(1000,100000,1000000,10000000,100000000)
arms=('producer','guard','family')
p=argparse.ArgumentParser()
p.add_argument('source');p.add_argument('mode',choices=('validate','worker','suite'))
p.add_argument('--cpu',type=int);p.add_argument('--n',type=int);p.add_argument('--arm',choices=arms)
a=p.parse_args();assert duckdb.__version__=='1.4.3'
if a.cpu is not None:os.sched_setaffinity(0,{a.cpu})
file=str(pathlib.Path(a.source).resolve()/'id1=*/*.parquet').replace("'","''")
def attach(n):
 assert n in ns
 c=duckdb.connect(config={'threads':'1','memory_limit':'1024MB','max_temp_directory_size':'0B','preserve_insertion_order':'false'})
 c.execute(f"CREATE TEMP VIEW x AS SELECT ordinal::BIGINT AS rid, floor(v3*100)::INTEGER AS s,id2,id3,v2 FROM read_parquet('{file}',hive_partitioning=true) WHERE ordinal<{n}")
 c.execute('BEGIN')
 return c
producer='SELECT * FROM x ORDER BY s DESC,rid ASC LIMIT 128'
other='SELECT * FROM x ORDER BY s DESC,rid DESC LIMIT 128'
equal='(x.s,x.id2,x.id3,x.v2) IS NOT DISTINCT FROM (c.s,c.id2,c.id3,c.v2)'
guard=f"""
WITH cut AS (SELECT MIN(s) b FROM candidate), shape AS
(SELECT COUNT(*) n, COUNT(DISTINCT rid) distinct_rids,
 count_if(s>(select b from cut)) above FROM candidate)
SELECT n=128 AND distinct_rids=n
 AND above=(SELECT COUNT(*) FROM x WHERE s>(SELECT b FROM cut))
 AND n=(SELECT COUNT(*) FROM candidate c JOIN x USING(rid) WHERE {equal}) FROM shape
"""
family=f"""
WITH cut AS MATERIALIZED(SELECT s b FROM x ORDER BY s DESC LIMIT 1 OFFSET 127),
 legal AS MATERIALIZED (SELECT * FROM x WHERE s>=(SELECT b FROM cut)),
 shape AS (SELECT COUNT(*) n,COUNT(DISTINCT rid) dr,MIN(s) b FROM candidate)
SELECT n=128 AND n=dr AND b=(SELECT b FROM cut)
 AND n=(SELECT COUNT(*) FROM candidate c JOIN legal x USING(rid) WHERE {equal})
 AND NOT EXISTS (SELECT rid FROM legal WHERE s>(SELECT b FROM cut) EXCEPT SELECT rid FROM candidate)
 FROM shape
"""
def one(c,s):return c.execute(s).fetchone()[0]
def hwm():return int(next(x for x in open('/proc/self/status') if x.startswith('VmHWM:')).split()[1])
def candidate(c,q=producer):c.execute("CREATE OR REPLACE TEMP TABLE candidate AS "+q)
def controls():
 c=attach(1000000)
 def both(v):
  assert one(c,guard) is v and one(c,family) is v
 candidate(c);both(True)
 x=tuple(c.execute('SELECT rid FROM candidate ORDER BY rid').fetchall())
 candidate(c,other);both(True)
 assert x!=tuple(c.execute('SELECT rid FROM candidate ORDER BY rid').fetchall())
 c.execute('DELETE FROM candidate WHERE rid=(SELECT MIN(rid) FROM candidate)');both(False)
 candidate(c);c.execute('INSERT INTO candidate SELECT * FROM candidate LIMIT 1');both(False)
 candidate(c);c.execute('UPDATE candidate SET v2=v2+1 WHERE rid=(SELECT MIN(rid) FROM candidate)');both(False)
 candidate(c);c.execute('UPDATE candidate SET s=s-1 WHERE rid=(SELECT MIN(rid) FROM candidate)');both(False)
 c.close()
 c=attach(100000000)
 assert c.execute('SELECT COUNT(*),MIN(rid),MAX(rid) FROM x').fetchone()==(100000000,0,99999999)
 cutoff=one(c,'SELECT s FROM x ORDER BY s DESC LIMIT 1 OFFSET 127')
 n_strict, n_equal=c.execute('SELECT count_if(s>?),count_if(s=?) FROM x',[cutoff,cutoff]).fetchone()
 assert n_strict<128<=n_strict+n_equal
 print(json.dumps(dict(cases=6,rows=100000000,cutoff=cutoff,strict_winners=n_strict,tied_members=n_equal),sort_keys=True))
def worker(n,arm):
 c=attach(n);base=hwm(); v0=time.process_time_ns();t0=time.perf_counter_ns()
 candidate(c)
 assert len(c.execute('SELECT * FROM candidate').fetchall())==128
 v1=time.process_time_ns();t1=time.perf_counter_ns();m1=hwm()
 if arm!='producer':assert one(c,guard if arm=='guard' else family) is True
 v2=time.process_time_ns();t2=time.perf_counter_ns();m2=hwm()
 print(json.dumps(dict(n=n,arm=arm,wall_prod_ns=t1-t0,wall_check_ns=t2-t1 if arm!='producer' else 0,
 cpu_prod_ns=v1-v0,cpu_check_ns=v2-v1 if arm!='producer' else 0,baseline_hwm_kib=base,pipeline_hwm_kib=m1,final_hwm_kib=m2),sort_keys=True))
def suite():
 r=random.Random(40069)
 for n in ns:
  for rep in range(5):
   x=list(arms);r.shuffle(x)
   for arm in x:
    cmd=[sys.executable,'-B',__file__,a.source,'worker','--n',str(n),'--arm',arm]
    if a.cpu is not None:cmd+=['--cpu',str(a.cpu)]
    try:j=json.loads(subprocess.run(cmd,capture_output=True,text=True,timeout=80,check=True).stdout)
    except subprocess.TimeoutExpired:j=dict(n=n,arm=arm,status='timeout')
    except subprocess.CalledProcessError as e:j=dict(n=n,arm=arm,status='error',details=e.stderr.splitlines()[-1:])
    print(json.dumps(dict(rep=rep,**j),sort_keys=True),flush=True)
if a.mode=='validate':controls()
elif a.mode=='suite':suite()
else:worker(a.n,a.arm)
