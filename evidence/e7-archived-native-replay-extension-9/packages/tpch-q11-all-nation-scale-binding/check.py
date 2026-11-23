from collections import Counter,defaultdict
from pathlib import Path
from hashlib import sha256
from math import gcd
import json,sys
E,W=map(Path,sys.argv[1:3]);sys.path.insert(0,str(E/'input/duck143'));import duckdb
P=Path(__file__).resolve().parent
assert sha256((P/'PLAN.json').read_bytes()).hexdigest()==(P/'PLAN.sha256').read_text().split()[0]
assert duckdb.__version__=='1.4.3'
ext=E/'input/ext143/tpch.duckdb_extension'
assert sha256(ext.read_bytes()).hexdigest()=="415c1b36d3e30f0d94b7eba826b03f3628787c5b8a1b1fb6336f002b478bf775"
D=duckdb.connect(str(W/'tpch.duckdb'),read_only=True,config={
    'memory_limit':'900MB','threads':'3','max_temp_directory_size':'1300MB','temp_directory':str(W/'spill-q11-global')})
D.execute("LOAD '"+str(ext.absolute()).replace("'","''")+"'")
q,=D.execute("SELECT query FROM tpch_queries() WHERE query_nr=11").fetchone()
assert sha256(q.encode()).hexdigest()=="f313c766fac507c1204fb6f2bacd35719a61a11c0f69601302555150dddeda78"
assert q.count("'GERMANY'")==2 and q.count("0.0001000000")==1
N=[k for k, in D.execute("SELECT n_name FROM nation ORDER BY n_name").fetchall()]
assert len(N)==25 and len(set(N))==len(N)
out=[]
# Independent exact grouping and total, compared with native stock separate nested SQL.
for key in N:
 def txt(x):return "'" + x.replace("'","''") + "'"
 r=D.execute("""SELECT p.ps_partkey,sum((p.ps_supplycost*100)::BIGINT*p.ps_availqty) AS cents,count(*) AS rows
 FROM partsupp p JOIN supplier s ON p.ps_suppkey=s.s_suppkey
 JOIN nation n ON s.s_nationkey=n.n_nationkey
 WHERE n.n_name=? GROUP BY p.ps_partkey""",[key]).fetchall()
 assert r
 tot=sum(a[1] for a in r)
 m=max(a[1] for a in r)
 g=gcd(tot,m)
 qual=q.replace("'GERMANY'",txt(key))
 rec=dict(nation=key,eligible_source_rows=sum(a[2] for a in r),eligible_parts=len(r),
          highest_group_share_exact=f"{m//g}/{tot//g}")
 for n,label,body in [(10000,'qualification_literal',qual),
                     (100000,'scale10_workload',qual.replace("0.0001000000","0.0000100000"))]:
  expected={k:x for k,x,_ in r if x*n>tot}
  z=D.execute(body).fetchall()
  vals={int(a):int(b*100) for a,b in z}
  assert all(v*100==int(v*100) for _,v in z)
  assert len(vals)==len(z) and vals==expected
  assert all(a[1]>=b[1] for a,b in zip(z,z[1:]))
  rec[label]=len(z)
  rec[label+'_tied_value_excess']=len(z)-len(set(vals.values()))
 out.append(rec)
print(json.dumps(out,indent=2,sort_keys=True))
