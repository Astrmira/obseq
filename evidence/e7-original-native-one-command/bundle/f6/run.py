import json,pathlib,sys,hashlib,importlib.util,sqlite3,itertools
from decimal import Decimal as D
sys.path.insert(0,'/tmp/pvl-eab-submission/e1/input/duck143')
import duckdb
p=pathlib.Path(sys.argv[1]);D0={'BLIND.json':'8e86163e65e0deaa46f3450f7600aa03361141f9406e73b235e0c648a5804831','check.py':'f005d93a52f8a4b69f772ef5c81a1cdc469df4c93a695f2f8ac24b57292b1cb6'}
for k,h in D0.items():assert hashlib.sha256((p/k).read_bytes()).hexdigest()==h
s=importlib.util.spec_from_file_location('oracle',p/'check.py');o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
cases=[x for x in json.loads((p/'BLIND.json').read_text()) if x['class']=='F6'];assert len(cases)==6
def plan(i,x):
 v=['SELECT 1'];mu=['SELECT 1']
 if i in (1,5):
  order='ASC' if i==1 else 'DESC';strict='<' if i==1 else '>';bad='>' if i==1 else '<'
  cutoff=f'(SELECT a FROM src ORDER BY a {order} LIMIT 1 OFFSET 1)'
  sufficient=f"NOT EXISTS(SELECT 1 FROM attempt q JOIN src s USING(id) WHERE s.a {bad} {cutoff}) AND NOT EXISTS (SELECT 1 FROM src s WHERE s.a {strict} {cutoff} AND NOT EXISTS (SELECT 1 FROM attempt q WHERE q.id=s.id))"
  scope='(SELECT count(*) FROM attempt)=2 AND (SELECT count(*) FROM attempt q JOIN src s USING(id))=2'
  return 'SELECT '+scope+" AND (SELECT count(DISTINCT id) FROM attempt)=2 AND "+sufficient,'SELECT '+scope+' AND '+sufficient
 if i==2:
  t=x['target'];q=f'SELECT count(*)=1 FROM attempt q JOIN src s USING(id) WHERE abs(s.a-{t})=(SELECT min(abs(a-{t})) FROM src)'
  return q,q.replace('abs(s.a-15)','s.a').replace('min(abs(a-15))','min(a)')
 if i==3:
  t=x['t'];q=f'SELECT count(*)=1 FROM attempt q JOIN src s USING(id) WHERE s.a<={t} AND {t}<s.b'
  return q,q.replace(f'{t}<s.b',f'{t}<=s.b')
 if i==4:
  q='SELECT count(*)=1 FROM attempt q JOIN src s USING(id) WHERE s.a=(SELECT max(a) FROM src)'
  return q,q.replace('WHERE s.a=(SELECT max(a) FROM src)','WHERE coalesce(s.a,0)=(SELECT max(coalesce(a,0)) FROM src)')
 assert i==6
 q='SELECT count(*)=1 FROM attempt q JOIN src s USING(id) WHERE s.a BETWEEN 12500 AND 15000'
 return q,q.replace('s.a BETWEEN','round(s.a/10.0)*10 BETWEEN')
out={}
for i,r in enumerate(cases,1):
 assert r['case_id']==f'E7H-F6-{i:02}'
 items=r['inputs']['rows'];x=r['inputs']
 k='ids' if 'ids'in r['candidate'] else 'id'
 ids=[s[0] for s in items]+['__absent__']
 choices=[dict(ids=list(z)) for n in range(4) for z in itertools.product(ids,repeat=n)] if k=='ids' else [dict(id=z) for z in ids]
 assert r['candidate'] in choices
 p0,mut=plan(i,x); modes={}
 for name,d in [('SQLite',sqlite3.connect(':memory:')),('DuckDB',duckdb.connect())]:
  d.execute('CREATE TABLE src(id TEXT PRIMARY KEY,a BIGINT,b BIGINT)');d.execute('CREATE TABLE attempt(id TEXT NOT NULL)')
  def scalar(y):
   if i!=6:return y
   z=D(y)*10000;assert z==z.to_integral_value();return int(z)
  d.executemany('INSERT INTO src VALUES(?,?,?)',[(row[0],scalar(row[1]),row[2] if len(row)==3 else None) for row in items])
  obs=[];bad=[]
  for v in choices:
   d.execute('DELETE FROM attempt')
   args=v['ids'] if k=='ids' else [v['id']]
   if args:d.executemany('INSERT INTO attempt VALUES (?)',[(y,) for y in args])
   a,b=[bool(d.execute(q).fetchone()[0]) for q in (p0,mut)]
   e=o.legal(dict(r,candidate=v));assert a==e,(name,r['case_id'],v,a,e)
   obs.append(a);bad.append(b)
  d.close();modes[name]=dict(native_exact=obs,changed_contract=bad)
 assert modes['SQLite']==modes['DuckDB']
 z=modes['SQLite'];orig=choices.index(r['candidate'])
 out[r['case_id']]=dict(number_proposals=len(choices),native_exact_legal=sum(z['native_exact']),original_native_legal=z['native_exact'][orig],
  mutated_false_admits=sum(not a and b for a,b in zip(z['native_exact'],z['changed_contract'])),mutated_false_rejects=sum(a and not b for a,b in zip(z['native_exact'],z['changed_contract'])),ordered_candidate_decisions=z)
print(json.dumps(dict(pins=D0,versions={'sqlite':sqlite3.sqlite_version,'duckdb':duckdb.__version__},cases=out),indent=2,sort_keys=True))
