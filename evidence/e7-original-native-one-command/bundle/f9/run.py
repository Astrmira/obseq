import sys,json,itertools,hashlib,sqlite3,importlib.util
from pathlib import Path
sys.path.insert(0,'/tmp/pvl-eab-submission/e1/input/duck143')
import duckdb
p=Path(sys.argv[1]); pins={'BLIND.json':'8e86163e65e0deaa46f3450f7600aa03361141f9406e73b235e0c648a5804831','check.py':'f005d93a52f8a4b69f772ef5c81a1cdc469df4c93a695f2f8ac24b57292b1cb6'}
assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in pins.items())
s=importlib.util.spec_from_file_location('frozen',p/'check.py');o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
def role(v):
 tag,value=v
 if tag in ('binary64-bits','bytes') and type(value)is str and len(value)%2==0:
  try:return tag,'blob',None,None,None,bytes.fromhex(value)
  except ValueError:pass
 if type(value)is bool:return tag,'bool',None,None,value,None
 if type(value)is int:return tag,'int',None,value,None,None
 return tag,'text',value,None,None,None
cols=['tag','typ','txt','inum','bval','bits']
tag='p.tag=q.tag'; payload=' AND '.join(f'p.{x} IS NOT DISTINCT FROM q.{x}' for x in cols[1:])
out={}
for r in json.loads((p/'BLIND.json').read_text()):
 if r['class']!='F9':continue
 ins='inOrder'in r['inputs']; peers=r['inputs'].get('inOrder',r['inputs'].get('peers'))
 orig=r['candidate']['repr']
 choices=list({json.dumps(x):x for x in [*peers,orig,*(list(g) for g in itertools.product([x[0] for x in peers],[x[1] for x in peers])),['other',peers[0][1]]]}.values())
 if r['case_id']=='E7H-F9-04':choices+=[['boolean',1],['integer',True]]
 if r['case_id']=='E7H-F9-06':choices+=[['binary64-bits','8000000000000001']]
 choices=list({json.dumps(x):x for x in choices}.values())
 methods={}
 for eng,db in [('DuckDB',duckdb.connect()),('SQLite',sqlite3.connect(':memory:'))]:
  schema='tag TEXT,typ TEXT,txt TEXT,inum BIGINT,bval BOOLEAN,bits BLOB'
  db.execute(f'CREATE TABLE source(n INTEGER,{schema})')
  db.execute(f'CREATE TABLE proposal({schema})')
  rows=[role(x) for x in peers]
  db.executemany('INSERT INTO source VALUES (?,?,?,?,?,?,?)',[(i,*x) for i,x in enumerate(rows)])
  got=db.execute('SELECT '+','.join(cols)+' FROM source ORDER BY n').fetchall()
  assert got==rows
  appoint=' AND p.n=0' if ins else ''
  base=' FROM source p,proposal q WHERE '
  res=[]
  for v in choices:
   db.execute('DELETE FROM proposal')
   db.execute('INSERT INTO proposal VALUES (?,?,?,?,?,?)',role(v))
   def exists(sql):return bool(db.execute('SELECT EXISTS(SELECT 1'+base+sql+')').fetchone()[0])
   exact=exists(tag+' AND '+payload+appoint)
   assert exact==o.legal(dict(r,candidate={'repr':v})),(r['case_id'],eng,v)
   weak={'tag_unbound':exists(payload+appoint),'slotwise':exists(tag+appoint) and exists(payload+appoint),
         'order_unbound':exists(tag+' AND '+payload),'fixed_first':exists(tag+' AND '+payload+' AND p.n=0'),'typed_coupled':exact}
   res.append(weak)
  db.close();methods[eng]=res
 assert methods['DuckDB']==methods['SQLite']
 res=methods['DuckDB'];b=list(zip(choices,res))
 out[r['case_id']]=dict(proposals=len(b),original_admissible=next(x['typed_coupled'] for z,x in b if json.dumps(z)==json.dumps(orig)),cases=[dict(candidate=z,decisions=x) for z,x in b],
  false_admits={k:sum(x[k] and not x['typed_coupled'] for x in res) for k in ('tag_unbound','slotwise','order_unbound')},fixed_first_false_rejects=sum(x['typed_coupled'] and not x['fixed_first'] for x in res))
assert len(out)==6
print(json.dumps(dict(versions={'sqlite':sqlite3.sqlite_version,'duckdb':duckdb.__version__},pins=pins,results=out),indent=2,sort_keys=True))
