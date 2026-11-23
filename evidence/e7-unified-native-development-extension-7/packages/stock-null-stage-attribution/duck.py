import hashlib,json,pathlib,sys,tempfile
sys.path.insert(0,sys.argv[1])
import duckdb
def sqlq(s):return "'"+str(s).replace("'","''")+"'"
def rows(c):return [list(x) for x in c.execute('SELECT k, v, v IS NULL FROM test ORDER BY k').fetchall()]
C=duckdb.connect(); build=C.execute('PRAGMA version').fetchone();C.execute('CREATE TABLE test(k INTEGER,v VARCHAR)')
C.execute("""INSERT INTO test VALUES (101,NULL),(102,''),(103,'NULL'),(104,'q')""")
expected=[[101,None,True],[102,'',False],[103,'NULL',False],[104,'q',False]]
assert rows(C)==expected
ret={}
with tempfile.TemporaryDirectory() as tmp:
 for name,opt,readopt in [('default_csv','', ''),('nullstr_csv',"(FORMAT csv, NULLSTR 'NULL')",",nullstr='NULL'"),('parquet','(FORMAT parquet)', '')]:
  path=pathlib.Path(tmp)/name
  C.execute(f'EXPORT DATABASE {sqlq(path)} {opt}')
  load=(path/'load.sql').read_text()
  q=duckdb.connect(); q.execute(f'IMPORT DATABASE {sqlq(path)}')
  v=rows(q);q.close()
  o=dict(generated_load=load.replace(str(path),'<EXPORT_DIR>'),expected=expected,roundtrip=v)
  if name!='parquet':
   f=path/'test.csv'; raw=f.read_text()
   o['csv_text']=raw
   for k,app in [('explicit_quoted_nulls_false','false'),('explicit_quoted_nulls_true','true')]:
    rr=C.execute("SELECT k,v,v IS NULL FROM read_csv("+sqlq(f)+",columns={'k':'INTEGER','v':'VARCHAR'},header=true,allow_quoted_nulls="+app+readopt+") ORDER BY k").fetchall()
    o[k]=list(map(list,rr))
   assert o['explicit_quoted_nulls_false']==expected
   assert o['explicit_quoted_nulls_true']!=expected
  else:
   assert v==expected
  ret[name]=o
C.close()
print(json.dumps(dict(duckdb=duckdb.__version__,build=build,paths=ret),indent=2))
