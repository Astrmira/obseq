import json,sqlite3,tempfile,pathlib,hashlib
m=json.load(open('manifest.json'));L=m['left'];R=m['right']
def independent(i,e):
 if i is None:return None
 if 0<=i<=2:return [[0,1,2],[1,2,0]][e][i]
 return i+e
def native(p,e):
 d=sqlite3.connect(p)
 d.create_function('epoch_key',1,lambda v:None if v is None else ((v+e)%3 if v in range(3) else v+e),
  deterministic=True)
 return d
def buckets(r):
 B={}
 for i,k in r:
  if k is not None:B.setdefault(k,set()).add(i)
 return B
def expected(e):
 def eq(x,y):return x is not None and y is not None and x==y
 return {(i,j) for i,k,on in L if on for j,v in R if eq(independent(k,e),v)}
with tempfile.TemporaryDirectory() as t:
 p=pathlib.Path(t)/'epoch.sqlite'
 d=native(p,0)
 d.execute('create table l(id integer primary key,x integer,active integer, stored integer generated always as(epoch_key(x)) stored)')
 d.execute('create table r(id integer primary key,k integer)')
 d.executemany('insert into l(id,x,active) values(?,?,?)',L)
 d.executemany('insert into r values(?,?)',R);d.commit();d.close()
 frozen=p.read_bytes()
 d=native(p,1)
 def pair(expr):
  q=f"select l.id,r.id,'payload' from l join r on {expr}=r.k where l.active=1 order by 1,2"
  rows=d.execute(q).fetchall();pairs={(i,j) for i,j,_ in rows}
  assert len(pairs)==len(rows)
  return pairs,sorted(v for _,_,v in rows)
 old,vals0=pair('l.stored');new,vals1=pair('epoch_key(l.x)')
 assert old==expected(0) and new==expected(1) and vals0==vals1 and not old&new and len(new)==6
 B=buckets(R)
 stale=[];use_stored=[]
 for i,x,on,sk,nk in d.execute('select id,x,active,stored,epoch_key(x) from l order by id'):
  assert sk==independent(x,0) and nk==independent(x,1)
  if not on:continue
  if sk!=nk:stale.append(i)
  old_bucket=B.get(sk,set());new_bucket=B.get(nk,set())
  certificate=sk==nk or (sk not in B and nk not in B)
  assert certificate==(old_bucket==new_bucket)
  if certificate:use_stored.append(i)
  assert (old_bucket!=new_bucket)==(any(a==i for a,b in old^new))
 assert stale==[11,12,13,14] and use_stored==[14,15]
 selector=','.join(map(str,use_stored))
 hybrid,_=pair(f'case when l.id in ({selector}) then l.stored else epoch_key(l.x) end')
 assert hybrid==new and p.read_bytes()==frozen
 assert d.execute('pragma integrity_check').fetchall()==[('ok',)]
 print(json.dumps({'sqlite':sqlite3.sqlite_version,'manifest_sha256':hashlib.sha256(json.dumps(m,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
  'materialized_pairs':sorted(old),'runtime_pairs':sorted(new),'stale_values_on_eligible_rows':stale,
  'exact_bucket_safe_stored_ids':use_stored,'same_payload_multiset':vals0==vals1,'hybrid_exact':hybrid==new},sort_keys=True,indent=2))
 d.close()
