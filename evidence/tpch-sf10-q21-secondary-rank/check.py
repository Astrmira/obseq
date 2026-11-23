import pathlib,sys,json,math,hashlib
from collections import Counter
E,W=map(pathlib.Path,sys.argv[1:3]);sys.path.insert(0,str(E/'input/duck143'));import duckdb
db=duckdb.connect(str(W/'tpch.duckdb'),read_only=True,config={'memory_limit':'1300MB','threads':'4','max_temp_directory_size':'3200MB','temp_directory':str(W/'spill-q21')})
ext=E/'input/ext143/tpch.duckdb_extension'
assert hashlib.sha256(ext.read_bytes()).hexdigest()=="415c1b36d3e30f0d94b7eba826b03f3628787c5b8a1b1fb6336f002b478bf775"
db.execute("LOAD '"+str(ext.absolute()).replace("'","''")+"'")
q,=db.execute("SELECT query FROM tpch_queries() WHERE query_nr=21").fetchone()
assert hashlib.sha256(q.encode()).hexdigest()=="b29463f30a64e45a795047ee6e557e6c3c1f01fc612acc997873594048e74b59"
uncut=q.split('\nORDER BY\n',1)[0]
noncut_rows=db.execute(uncut).fetchall()
native_full=dict(noncut_rows)
assert len(native_full)==len(noncut_rows)
derive="""
WITH order_rollup AS (
 SELECT l_orderkey, min(l_suppkey) AS smin,max(l_suppkey) AS smax,
   min(l_suppkey) FILTER (WHERE l_receiptdate>l_commitdate) AS lateonly_min,
   max(l_suppkey) FILTER (WHERE l_receiptdate>l_commitdate) AS lateonly_max,
   count(*) FILTER (WHERE l_receiptdate>l_commitdate) AS nlate
 FROM lineitem GROUP BY l_orderkey
)
SELECT s_name,sum(nlate)::BIGINT AS numwait
FROM order_rollup
JOIN orders ON o_orderkey=l_orderkey AND o_orderstatus='F'
JOIN supplier ON s_suppkey=lateonly_min
JOIN nation ON n_nationkey=s_nationkey AND n_name='SAUDI ARABIA'
WHERE smin<>smax AND lateonly_min=lateonly_max
GROUP BY s_name
"""
rewrite=db.execute(derive).fetchall()
assert len(rewrite)==len(native_full) and dict(rewrite)==native_full
canon=sorted(rewrite,key=lambda r:(-r[1],r[0]))
stock=db.execute(q).fetchall()
assert stock==canon[:100]
threshold=stock[-1][1]
mandatory=[row for row in canon if row[1]>threshold]
peer_pool=[row for row in canon if row[1]==threshold]
need=100-len(mandatory)
assert len(stock)==100 and 1<=need<=len(peer_pool)
weak=db.execute(uncut+'\nORDER BY numwait DESC,s_name DESC LIMIT 100').fetchall()
assert [r[1] for r in weak]==[r[1] for r in stock]
assert set(mandatory)<=set(weak) and len(set(weak)&set(peer_pool))==need
stock_digest=hashlib.sha256(json.dumps(stock,separators=(',',':')).encode()).hexdigest()
rew_digest=hashlib.sha256(json.dumps(weak,separators=(',',':')).encode()).hexdigest()
print(json.dumps({'engine':duckdb.__version__,'query_sha256':hashlib.sha256(q.encode()).hexdigest(),'as_specified_distinct_memberships':1,'qualifying_suppliers':len(canon),'boundary_count':threshold,'mandatory_before_boundary':len(mandatory),'peers_at_boundary':len(peer_pool),'taken_from_boundary':need,'memberships_admissible_if_dropping_secondary_sort':math.comb(len(peer_pool),need),'native_reverse_secondary_membership_symmetric_difference':len(set(stock)^set(weak)),'native_full_name_order_count_histogram':dict(Counter(r[1] for r in canon)), 'ordered_position_differences_with_reverse_secondary':sum(a!=b for a,b in zip(stock,weak)), 'stock_full_order_sha256':stock_digest, 'reversed_secondary_full_order_sha256':rew_digest,'native_complete_supplier_count_map_equals_rollup_rewrite':True},sort_keys=True,indent=2))
