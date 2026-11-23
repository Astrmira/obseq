import csv, collections, hashlib, pathlib, os, subprocess, re, json, sys, tempfile
s=pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0,sys.argv[2])
import duckdb
P=pathlib.Path(__file__).resolve().parent
files=json.loads((P/'INPUTS.json').read_text())
for name,dig in files.items():
 with (s/name).open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==dig
data=s/'generated/G1_1e7_1e2_5_0.csv'
native_source=(s/'groupby-duckdb.py').read_text()
r_source=(s/'groupby-datatable.R').read_text()
patterns=('CREATE %s TABLE ans AS (SELECT [^"]+)" % table_type', 'con\\.execute\\("(SELECT [^"]+ FROM ans)"\\)\\.fetchone\\(\\)')
seq=[re.findall(p,native_source) for p in patterns]
assert seq[1].pop(0)=="SELECT count(*) AS cnt FROM ans"  # upstream warm-up
assert all(len(v)==20 and v[::2]==v[1::2] for v in seq)
q10=re.findall(r'ans<-(x\[, \.\(v3=sum\(v3, na.rm=TRUE\), count=\.N\), by=id1:id6\])',r_source)
assert len(q10)==2 and q10[0]==q10[1]
spec={'duckdb':seq[0][::2],'checks':seq[1][::2],'datatable_q10':q10[0]}
assert hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':')).encode()).hexdigest()=='0bf446d82bc7bf3029823e2794fb2b888a8c3d80a84997c75661b855675d6f6e'
with tempfile.TemporaryDirectory(dir=s) as td:
 r_home=s/'root/usr/lib/R'
 dt_env=dict(os.environ,OMP_NUM_THREADS='4',R_HOME=str(r_home),LD_LIBRARY_PATH=str(r_home/'lib'),R_LIBS_SITE=str(r_home/'site-library'),TMPDIR=td)
 r_code='''suppressPackageStartupMessages(library(data.table))
setDTthreads(4L)
argv=commandArgs(TRUE)
x=fread(argv[1],na.strings="",showProgress=FALSE)
ans <- '''+spec['datatable_q10']+'''
setnames(ans,1:6,paste0("id",1:6))
fwrite(ans[v3==0 & !is.na(v3), c(paste0("id",1:6),"count"), with=FALSE],argv[2],quote=FALSE)
cat(paste(nrow(x),nrow(ans),sum(ans$count),sum(ans$v3==0,na.rm=TRUE),sum(is.na(ans$v3)),sep=","),"\n",sep="")
'''
 r_script=pathlib.Path(td)/'stock-r-check.R';r_script.write_text(r_code)
 r=subprocess.Popen([str(r_home/'bin/exec/R'),'--vanilla','--slave','-f',str(r_script),'--args',str(data),str(pathlib.Path(td)/"zeros.csv")],env=dt_env,stdout=subprocess.PIPE,text=True)
 try:
  rr=r.communicate();assert r.returncode==0, r.returncode
  d=duckdb.connect(str(pathlib.Path(td)/'q.duckdb'),config={'threads':'4','memory_limit':'1100MB','temp_directory':td,'max_temp_directory_size':'2200MB'})
  d.execute('CREATE TABLE y(id1 VARCHAR, id2 VARCHAR, id3 VARCHAR, id4 INT, id5 INT, id6 INT, v1 INT, v2 INT, v3 FLOAT)')
  d.execute("COPY y FROM '"+str(data).replace("'","''")+"' (AUTO_DETECT TRUE)")
  for j in (1,2):d.execute(f'CREATE TYPE id{j}ENUM AS ENUM (SELECT id{j} FROM y where id{j} IS NOT NULL)')
  d.execute('CREATE TABLE x(id1 id1ENUM, id2 id2ENUM, id3 VARCHAR, id4 INT, id5 INT, id6 INT, v1 INT, v2 INT, v3 FLOAT)')
  d.execute('INSERT INTO x (SELECT * FROM y)'); d.execute('DROP TABLE y')
  matrix=[]
  for i,(q,c) in enumerate(zip(spec['duckdb'],spec['checks']),1):
   d.execute('CREATE TABLE ans AS '+q)
   n=d.execute('SELECT count(*) FROM ans').fetchone()[0]
   a=d.execute(c).fetchone()
   # Numeric aggregate checksums can legally vary by scan order; exact diagnostic below.
   matrix.append({'q':i,'output_rows':n,'columns':len(d.execute('SELECT * FROM ans LIMIT 0').description),'checksum_fields':len(a)})
   if i<10:d.execute('DROP TABLE ans')
  n_r,g_r,total_r,zero_r,null_r=map(int,rr[0].strip().split(','))
  n_s,g_s,total_s,zero_s,null_s=d.execute('SELECT (SELECT count(*) FROM x),count(*),sum(count),count_if(v3=0),count_if(v3 IS NULL) FROM ans').fetchone()
  assert n_s==n_r==total_s==total_r==10000000 and g_s==g_r and null_s==zero_r and zero_s==null_r==0 and null_s>0
  with (pathlib.Path(td)/'zeros.csv').open(newline='') as f:
   rr_csv=csv.reader(f); assert next(rr_csv)==['id1','id2','id3','id4','id5','id6','count']
   zero_keys=set(tuple((int(x) if j>=3 else x) if x else None for j,x in enumerate(row)) for row in rr_csv)
  assert len(zero_keys)==zero_r
  null_keys=set(d.execute('SELECT id1,id2,id3,id4,id5,id6,count FROM ans WHERE v3 IS NULL').fetchall())
  assert null_keys==zero_keys
  del null_keys,zero_keys
  # Re-execute the published checksum on each map. Compare both raw rounded fields
  # and a higher-resolution decimal accumulator for a second check.
  defs={}
  for name,null_policy in [('sql','v3'),('zero_fill','COALESCE(v3,0)')]:
   d.execute(f'CREATE OR REPLACE TEMP VIEW controls AS SELECT {null_policy} AS v3,count FROM ans')
   raw=d.execute(spec['checks'][-1].replace(' FROM ans',' FROM controls')).fetchone()
   exact=d.execute('SELECT sum(cast(v3 AS DECIMAL(38,20))),sum(count) FROM controls').fetchone()
   defs[name]=(tuple(round(x,3) for x in raw),tuple(str(x) for x in exact))
  assert defs['sql']==defs['zero_fill']
  truth=collections.defaultdict(lambda:[0,0])
  with data.open(newline='') as f:
   reader=csv.reader(f);assert next(reader)==['id1','id2','id3','id4','id5','id6','v1','v2','v3']
   for row in reader:
    if row[0]=='id001':
     a=truth[tuple(row[:3])+tuple(int(x) if x else None for x in row[3:6])];a[0]+=1;a[1]+=not row[8]
  # Empty CSV text keys encode NULL in this pinned run.
  truth={tuple(x if x!='' else None for x in k):v for k,v in truth.items()}
  observed=d.execute("SELECT id1,id2,id3,id4,id5,id6,count,v3 IS NULL FROM ans WHERE id1='id001'").fetchall()
  assert len(observed)==len(truth)
  assert all(truth[row[:6]][0]==row[6] and row[7]==(truth[row[:6]][1]==row[6]) for row in observed)
 finally:
  if r.poll() is None:r.terminate();r.wait()
print(json.dumps({'duckdb':duckdb.__version__,'data_rows':n_s,'matrix':matrix,'q10':{'native_groups':g_s,'duckdb_null_aggregates':null_s,'native_exact_key_count_map_for_missing_vs_zero_identical':True,'duckdb_zero_aggregates':zero_s,'data_table_null_aggregates':null_r,'data_table_zero_aggregates':zero_r,'both_count_sum':total_s,'stock_same_engine_checksum_equal_after_null_to_zero':True,'witness_stratum':'id001','oracle_exact_keys':len(truth),'oracle_all_null_keys':sum(a==b for a,b in truth.values())}},indent=2,sort_keys=True))
