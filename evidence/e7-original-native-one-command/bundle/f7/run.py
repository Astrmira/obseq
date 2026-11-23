import json, pathlib, sys, hashlib, importlib.util, sqlite3
sys.path.insert(0,sys.argv[2])
import duckdb
ROOT=pathlib.Path(sys.argv[1])
PIN={'BLIND.json':'8e86163e65e0deaa46f3450f7600aa03361141f9406e73b235e0c648a5804831','check.py':'f005d93a52f8a4b69f772ef5c81a1cdc469df4c93a695f2f8ac24b57292b1cb6'}
for f,h in PIN.items():assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h
spec=importlib.util.spec_from_file_location('oracle',ROOT/'check.py')
oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
cases=[r for r in json.loads((ROOT/'BLIND.json').read_text()) if r['class']=='F7']
assert [r['case_id'] for r in cases]==['E7H-F7-%02d'%i for i in range(1,7)]
assert duckdb.__version__=='1.4.3'
def make(i,C):
 if i in (1,3,5):return [(k,v) for k,v in C.items()]
 if i==2:return [(x,) for x in C['items']]
 if i==4:return [(C['net'],)]
 return list(map(tuple,C['events']))
def tests(i,X,R):
 if i==1:return [{'north':23,'south':38},{'north':28,'south':33},{'north':23,'other':38}]
 if i==2:return [{'items':R},{'items':[-9,3,7]},{'items':[-8,2,3,7]},{'items':[-9,3,7,0,3]}]
 if i==3:return [R,{'open':3,'closed':2,'held':1},{'open':3,'closed':1,'notheld':2}]
 if i==4:return [{'net':6},{'net':0},{'net':-6},{'net':-2}]
 if i==5:return [R,{'a':4,'b':-4,'d':0},{'a':4,'b':-4,'c':0,'d':0}]
 if i==6:return [{'events':R},{'events':[['a','refund',2],['b','sale',-2]]},{'events':[['a','refund',-2],['b','sale',2],['b','sale',2]]}]
def typed(db,table,rows,schema,is_sqlite):
 cols=['c'+str(i) for i in range(len(schema))]
 db.execute('DROP TABLE IF EXISTS '+table)
 db.execute('CREATE TABLE '+table+'('+','.join(k+' '+t+' NOT NULL' for k,t in zip(cols,schema))+')'+(' STRICT' if is_sqlite else ''))
 if rows:db.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for x in cols)+')',rows)
 assert db.execute('SELECT * FROM '+table).fetchall()==rows
 for k,t in zip(cols,schema):
  tags=db.execute('SELECT DISTINCT lower(typeof('+k+')) FROM '+table).fetchall()
  assert tags==[(('text' if is_sqlite else 'varchar') if t=='TEXT' else 'integer',)] if rows else not tags
 return cols
res={}
for engine in ('SQLite','DuckDB'):
 lite=engine=='SQLite'; db=sqlite3.connect(':memory:') if lite else duckdb.connect(config={'threads':'1','autoload_known_extensions':'false','autoinstall_known_extensions':'false'})
 vers=sqlite3.sqlite_version if lite else duckdb.__version__
 assert vers==('3.53.1' if lite else '1.4.3')
 output={}
 for i,r in enumerate(cases,1):
  X,C=r['inputs'],r['candidate']; R=X.get('reference')
  ref= [(z,) for z in X['amounts']] if i==4 else make(i,R if i in (1,3,5) else {('items' if i==2 else 'events'):R})
  schema=['TEXT','INTEGER'] if i in (1,3,5) else ['TEXT','TEXT','INTEGER'] if i==6 else ['INTEGER']
  cols=typed(db,'reference_rows',ref,schema,lite); cols=','.join(cols);metric='c'+str(len(schema)-1)
  arm=[]
  seen=set()
  for tag,cand in [('original',C)]+[(f'authored-{i+1}',c) for i,c in enumerate(tests(i,X,R))]:
   z=json.dumps(cand,sort_keys=True)
   if z in seen:continue
   seen.add(z)
   candrows=make(i,cand)
   typed(db,'candidate_rows',candrows,schema,lite)
   if i==4:
    q='SELECT count(*)=1 AND min(c0)=(SELECT sum(c0) FROM reference_rows) FROM candidate_rows'
   else:
    q=f'SELECT NOT EXISTS (SELECT {cols} FROM (SELECT {cols},1 AS sign FROM reference_rows UNION ALL SELECT {cols},-1 AS sign FROM candidate_rows) AS bag GROUP BY {cols} HAVING sum(sign)<>0)'
   exact=bool(db.execute(q).fetchone()[0])
   assert exact==oracle.legal({**r,'candidate':cand})
   sr,nr=db.execute('SELECT sum('+metric+'),count(*) FROM reference_rows').fetchone()
   sc,nc=db.execute('SELECT sum('+metric+'),count(*) FROM candidate_rows').fetchone()
   arm.append(dict(arm=tag,candidate=cand,exact=exact,net_only=(sc==sr),net_and_presented_row_count=(None if i==4 else sc==sr and nr==nc),native_sums=[sr,sc],native_counts=[nr,nc]))
  output[r['case_id']]=arm
 res[engine]=dict(version=vers,observations=output)
 db.close()
assert res['SQLite']['observations']==res['DuckDB']['observations']
A=res['SQLite']['observations']
assert [v[0]['exact'] for k,v in A.items()]==[False,True,False,True,False,True]
summary={}
for k,entries in [('original',[l[0] for l in A.values()]),('authored',[a for l in A.values() for a in l[1:]])]:
 summary[k]=dict(proposals=len(entries),exact_accept=sum(x['exact'] for x in entries),net_false_admit=sum(x['net_only'] and not x['exact'] for x in entries),net_plus_count_false_admit=sum(x['net_and_presented_row_count'] is True and not x['exact'] for x in entries))
print(json.dumps(dict(engine_results=res,summary_per_engine=summary),indent=2,sort_keys=True))
