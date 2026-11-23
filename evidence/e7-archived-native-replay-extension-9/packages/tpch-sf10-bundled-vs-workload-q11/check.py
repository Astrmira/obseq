from pathlib import Path
import sys,json,hashlib
from collections import defaultdict
E,W=map(Path,sys.argv[1:3]);sys.path.insert(0,str(E/'input/duck143'));import duckdb
D=duckdb.connect(str(W/'tpch.duckdb'),read_only=True,config={'memory_limit':'800MB','threads':'2','max_temp_directory_size':'800MB','temp_directory':str(W/'spill-q11')})
ext=E/'input/ext143/tpch.duckdb_extension'
assert hashlib.sha256(ext.read_bytes()).hexdigest()=='415c1b36d3e30f0d94b7eba826b03f3628787c5b8a1b1fb6336f002b478bf775'
D.execute("LOAD '"+str(ext.absolute()).replace("'","''")+"'")
q,=D.execute('SELECT query FROM tpch_queries() WHERE query_nr=11').fetchone()
assert hashlib.sha256(q.encode()).hexdigest()=='f313c766fac507c1204fb6f2bacd35719a61a11c0f69601302555150dddeda78'
assert q.count('0.0001000000')==1
full=D.execute(q).fetchall()
assert D.execute('PRAGMA tpch(11)').fetchall()==full
new=q.replace('0.0001000000','0.0000100000')
corrected=D.execute(new).fetchall()
national_suppliers={x[0] for x in D.execute("SELECT s_suppkey FROM supplier JOIN nation ON s_nationkey=n_nationkey WHERE n_name='GERMANY'").fetchall()}
sums=defaultdict(int); c=0
# Filter source by independently selected fixed supplier set; independent Python
# group accumulation and comparison do not reuse either query answer path.
cur=D.execute("SELECT ps_partkey,ps_suppkey,ps_availqty,ps_supplycost FROM partsupp WHERE ps_suppkey=ANY(?)",[sorted(national_suppliers)])
while block:=cur.fetchmany(20000):
 for k,s,qty,cost in block:
  assert s in national_suppliers and cost*100==int(cost*100)
  sums[k]+=qty*int(cost*100); c+=1
tot=sum(sums.values())
rec={}
for n,arm,r in [(10000,'bundled',full),(100000,'scale_bound',corrected)]:
 expected={k:a for k,a in sums.items() if a*n>tot}
 assert all(a*100==int(a*100) for _,a in r)
 by_key={k:int(a*100) for k,a in r}
 assert by_key==expected and len(r)==len(by_key)
 assert all(a[1]>=b[1] for a,b in zip(r,r[1:]))
 rec[arm]={'fraction':f'1/{n}','matched_exact_oracle':True,'output_rows':len(r),'threshold_cents_rational':f'{tot}/{n}','value_tie_count_excess':len(r)-len(set(by_key.values()))}
print(json.dumps({'qualifying_input_rows':c,'german_suppliers':len(national_suppliers),'qualifying_input_groups':len(sums),'biggest_group_cents':max(sums.values()),'stock_sql_digest':hashlib.sha256(q.encode()).hexdigest(),'scale_bound_sql_digest':hashlib.sha256(new.encode()).hexdigest(),'results':rec},sort_keys=True,indent=2))
