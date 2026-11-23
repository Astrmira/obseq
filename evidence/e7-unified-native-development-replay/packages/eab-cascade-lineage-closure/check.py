import sqlite3,json,random,tempfile,pathlib
def model(rows,roots):
 pending=list(roots);remove=set(roots)
 children={}
 for i,p,_ in rows:children.setdefault(p,[]).append(i)
 while pending:
  for i in children.get(pending.pop(),()):
   if i not in remove:remove.add(i);pending.append(i)
 return remove,sorted(r for r in rows if r[0] not in remove)
def native(rows,roots,enforce=True):
 with tempfile.TemporaryDirectory() as t:
  p=pathlib.Path(t)/'native.sqlite'
  d=sqlite3.connect(p)
  d.execute('pragma foreign_keys='+str(int(enforce)))
  d.execute('create table t(id integer primary key,parent integer references t(id) on delete cascade,label text)')
  d.execute("begin")
  d.execute("pragma defer_foreign_keys=ON")
  d.executemany('insert into t values(?,?,?)',rows)
  d.commit() # Authored predecessor is valid even if input IDs aren't topological.
  before=d.execute('select id,parent,label from t order by id').fetchall()
  assert before==rows
  marks=','.join('?' for _ in roots)
  reported=d.execute('delete from t where id in ('+marks+') returning id',roots).fetchall()
  d.commit();d.close()
  d=sqlite3.connect(p)
  after=d.execute('select id,parent,label from t order by id').fetchall()
  observed_remove={i for i,_,_ in before}-{i for i,_,_ in after}
  bad=d.execute('pragma foreign_key_check').fetchall()
  d.close()
  return sorted(i for i, in reported),sorted(observed_remove),after,bad

cases={}
for tag,rows in {'A':[(1,None,'source'),(2,1,'child'),(3,2,'grandchild'),(4,None,'control')],
                 'B':[(1,None,'source'),(2,1,'child'),(3,4,'grandchild'),(4,None,'control')]}.items():
 for enforce in (False,True):
  expected,after=model(rows,[1]);direct,removed,actual,violations=native(rows,[1],enforce)
  if enforce:
   assert set(removed)==expected and actual==after and direct==[1] and not violations
  else:assert direct==removed==[1] and violations
  cases[tag+('/on' if enforce else '/off')]={'returning':direct,'removed':removed,'foreign_key_violations':len(violations)}
rng=random.Random(118)
for _ in range(64):
 rows=[(i,None if i==1 else rng.choice([None,*range(1,i)]),str(i)) for i in range(1,rng.randrange(12,35))]
 ids=rng.sample([i for i,p,s in rows if p is None],1)
 expected,after=model(rows,ids);a,b,c,d=native(rows,ids)
 assert a==ids and set(b)==expected and c==after and not d
print(json.dumps({'sqlite':sqlite3.sqlite_version,'cases':cases,'authored_seeded_forest_cases':64},indent=2,sort_keys=True))
