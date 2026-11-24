import argparse,json,os,pathlib,random,resource,subprocess,sys,time
from collections import Counter
import duckdb

SIZES=(1000,100000,1000000,10000000,100000000)
ARMS=('producer','claimed','family')
p=argparse.ArgumentParser()
p.add_argument('db',type=pathlib.Path)
p.add_argument('mode',choices=('validate','suite','worker'))
p.add_argument('--size',type=int)
p.add_argument('--arm',choices=ARMS)
p.add_argument('--cpu',type=int)
a=p.parse_args()
assert duckdb.__version__=='1.4.3'
if a.cpu is not None:
    os.sched_setaffinity(0,{a.cpu})
q="""SELECT ordinal::BIGINT rid, CAST(substr(id1,3) AS INTEGER) g,
 CAST(FLOOR(v3*100) AS INTEGER) s,id2 k,id3 i,v2 d
 FROM {source} WHERE ordinal>=0 AND ordinal<"""
group="SELECT g,max(s) m FROM x GROUP BY g"
producer="""SELECT g, s, w.rid rid,w.k k,w.i i,w.d d
FROM (SELECT g,max(s) s,arg_max(struct_pack(rid:=rid,k:=k,i:=i,d:=d),s) w
FROM x GROUP BY g) y"""
base_cte="mx AS MATERIALIZED ("+group+"), duplicates AS (SELECT g,count(*) n FROM candidate GROUP BY g HAVING count(*)!=1)"
basic="""(SELECT count(*) FROM duplicates)=0
AND NOT EXISTS (SELECT g FROM candidate EXCEPT SELECT g FROM mx)
AND NOT EXISTS (SELECT g FROM mx EXCEPT SELECT g FROM candidate)"""
eq="(x.g,x.s,x.k,x.i,x.d) IS NOT DISTINCT FROM (c.g,c.s,c.k,c.i,c.d)"
claimed="""WITH """+base_cte+"""
SELECT """+basic+""" AND (SELECT count(*) FROM candidate) = (SELECT count(*) FROM candidate c
JOIN x ON x.rid=c.rid JOIN mx ON mx.g=c.g AND mx.m IS NOT DISTINCT FROM c.s
WHERE """+eq+""")"""
family="""WITH """+base_cte+""", full_family AS MATERIALIZED (
 SELECT x.* FROM x JOIN mx ON x.g=mx.g AND x.s IS NOT DISTINCT FROM mx.m
)
SELECT """+basic+""" AND NOT EXISTS (SELECT 1 FROM candidate c WHERE NOT EXISTS (
 SELECT 1 FROM full_family x WHERE x.rid=c.rid AND """+eq+"""))"""
def setup(n):
    assert n in SIZES
    con=duckdb.connect(config={'threads':'1','memory_limit':'1200MB','max_temp_directory_size':'0B','preserve_insertion_order':'false'})
    source="read_parquet(" + ("'"+str(a.db.resolve()/'id1=*/*.parquet').replace("'","''")+"'") + ",hive_partitioning=true)"
    con.execute('CREATE TEMP VIEW x AS '+q.format(source=source)+str(n))
    con.execute('BEGIN')
    return con
def fetch(c,sql):return c.execute(sql).fetchall()
def single(c,sql):return fetch(c,sql)[0][0]
def make(c):
    c.execute('CREATE TEMP TABLE candidate AS '+producer)
    rows=fetch(c,'SELECT * FROM candidate ORDER BY g')
    assert len(rows)==len({r[0] for r in rows}) and all(all(v is not None for v in r) for r in rows)
    return len(rows)
def rss():
    return int(next(l.split()[1] for l in open('/proc/self/status') if l.startswith('VmHWM:')))
def validate():
    c=setup(1000000); n=make(c); assert n>1
    def both(expected):
        assert single(c,claimed) is expected and single(c,family) is expected
    both(True)
    g,rid,s,k,i,d=fetch(c,'''SELECT x.g,x.rid,x.s,x.k,x.i,x.d FROM x JOIN candidate c
      ON (x.g,x.s)=(c.g,c.s) WHERE x.rid!=c.rid ORDER BY x.g,x.rid LIMIT 1''')[0]
    old=fetch(c,'SELECT * FROM candidate WHERE g='+str(g))[0]
    c.execute('UPDATE candidate SET rid=?,s=?,k=?,i=?,d=? WHERE g=?',[rid,s,k,i,d,g])
    both(True)
    c.execute('UPDATE candidate SET d=d+10 WHERE g=?',[g]);both(False)
    c.execute('DELETE FROM candidate WHERE g=?',[g]);both(False)
    c.execute('INSERT INTO candidate VALUES (?,?,?,?,?,?)',old);both(True)
    c.execute('INSERT INTO candidate VALUES (?,?,?,?,?,?)',old);both(False)
    c.execute('DELETE FROM candidate WHERE g=?',[g])
    c.execute('INSERT INTO candidate VALUES (?,?,?,?,?,?)',(old[0],old[1],old[2]-1,*old[3:]));both(False)
    c.close()
    c=setup(100000000)
    rows,gcount,tied=fetch(c,"WITH m AS ("+group+") SELECT count(*),count(DISTINCT x.g),count_if(x.s=m.m) FROM x JOIN m USING(g)")[0]
    minrid,maxrid=fetch(c,'SELECT min(rid),max(rid) FROM x')[0]
    assert rows==100000000 and minrid==0 and maxrid==99999999 and gcount==100 and tied>gcount
    print(json.dumps(dict(cases=6,original_group_count=gcount,physical_rows=rows,allowed_distinct_tied_members=tied),sort_keys=True))
def worker(n,arm):
    c=setup(n)
    vm0=rss();t0=time.perf_counter_ns(); cpu0=time.process_time_ns()
    ng=make(c)
    cpu1=time.process_time_ns();t1=time.perf_counter_ns();vm1=rss()
    if arm!='producer':
        assert single(c,claimed if arm=='claimed' else family) is True
    cpu2=time.process_time_ns();t2=time.perf_counter_ns();vm2=rss()
    print(json.dumps(dict(arm=arm,n=n,groups=ng,wall_prod_ns=t1-t0,wall_check_ns=t2-t1 if arm!='producer' else 0,
       cpu_prod_ns=cpu1-cpu0,cpu_check_ns=cpu2-cpu1 if arm!='producer' else 0,
       baseline_hwm_kib=vm0,pipeline_hwm_kib=vm1,final_hwm_kib=vm2),sort_keys=True))
def suite():
    rnd=random.Random(80137)
    for n in SIZES:
        for rep in range(5):
            arms=list(ARMS);rnd.shuffle(arms)
            for arm in arms:
                cmd=[sys.executable,'-B',__file__,str(a.db),'worker','--size',str(n),'--arm',arm]
                if a.cpu is not None:cmd+=['--cpu',str(a.cpu)]
                try:
                    z=subprocess.run(cmd,text=True,timeout=95,capture_output=True,check=True)
                    out=json.loads(z.stdout)
                except subprocess.TimeoutExpired:
                    out=dict(n=n,arm=arm,status='timeout_95s')
                except subprocess.CalledProcessError as e:
                    out=dict(n=n,arm=arm,status='not_measured',stderr=e.stderr.splitlines()[-1:])
                print(json.dumps(dict(rep=rep,**out),sort_keys=True),flush=True)
if a.mode=='validate':validate()
elif a.mode=='worker':worker(a.size,a.arm)
else:suite()
