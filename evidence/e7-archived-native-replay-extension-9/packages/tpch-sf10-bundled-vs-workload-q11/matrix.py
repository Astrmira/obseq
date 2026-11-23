from pathlib import Path
import sys,json,hashlib
E,W=map(Path,sys.argv[1:3]);sys.path.insert(0,str(E/'input/duck143'));import duckdb
p=(W/'tpch.duckdb').resolve()
D=duckdb.connect(str(p),read_only=True,config={'memory_limit':'1300MB','threads':'4','max_temp_directory_size':'1500MB','temp_directory':str(W/'spill-22')})
ext=E/'input/ext143/tpch.duckdb_extension'
assert hashlib.sha256(ext.read_bytes()).hexdigest()=='415c1b36d3e30f0d94b7eba826b03f3628787c5b8a1b1fb6336f002b478bf775'
D.execute("LOAD '"+str(ext.absolute()).replace("'","''")+"'")
qs=D.execute('SELECT query_nr,query FROM tpch_queries() ORDER BY 1').fetchall()
assert hashlib.sha256(json.dumps(qs,separators=(',',':')).encode()).hexdigest()=='0f7885bb4cc739a7a9a9e25538be91361e8ff2ceab3fe0a069bdaca74fe8f383'
for n,sql in qs:
 try:
  dst=D.execute(sql); rows=dst.fetchall();ncol=len(dst.description)
  rec={'query':n,'status':'executed','rows':len(rows),'columns':ncol}
 except Exception as exc:rec={'query':n,'status':'blocked','class':type(exc).__name__}
 print(json.dumps(rec,sort_keys=True),flush=True)
