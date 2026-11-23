import sqlite3,itertools as it,json,random
def allowed(rows,k):
 groups={}
 for g,i,s,x,y in rows:groups.setdefault(g,[]).append((i,s,x,y))
 members=[]
 for a in groups.values():
  threshold=sorted((s for _,s,_,_ in a),reverse=True)[k-1]
  mandatory=[r for r in a if r[1]>threshold];ties=[r for r in a if r[1]==threshold]
  members.append((mandatory,ties,k-len(mandatory)))
 return members
def range_only(parts,alpha,beta):
 lo=hi=0
 for must,ties,q in parts:
  f=lambda row:row[2]*alpha+row[3]*beta
  constant=sum(map(f,must));w=sorted(map(f,ties))
  lo+=constant+sum(w[:q]);hi+=constant+sum(w[len(w)-q:])
 return lo,hi
def full(parts):
 out=set()
 for selection in it.product(*(list(it.combinations(ties,q)) for _,ties,q in parts)):
  vec=[0,0]
  for (must,_,_),selected in zip(parts,selection):
   for _,_,x,y in list(must)+list(selected):vec[0]+=x;vec[1]+=y
  out.add(tuple(vec))
 return sorted(out)
base=[(0,10,10,2,0),(0,11,10,0,2),(0,12,3,9,9),
      (1,20,12,1,1),(1,21,10,3,0),(1,22,10,0,3)]
def with_quotas(rows):
 return [allowed([r for r in rows if r[0]==g],k)[0] for g,k in [(0,1),(1,2)]]
parts=with_quotas(base);points=full(parts)
assert points==[(1,6),(3,4),(4,3),(6,1)]
assert (2,5) not in points # Inside the convex hull, but no shared witness.
with sqlite3.connect(':memory:') as d:
 d.execute('create table t(g integer,id integer primary key,s integer,x integer,y integer)')
 d.executemany('insert into t values(?,?,?,?,?)',base)
 d.execute('create index ia on t(g,s desc,id asc)')
 d.execute('create index ib on t(g,s desc,id desc)')
 def native(index,deterministic):
  # SQLite each selection listed as a durable receipt in the fixture.
  order='s desc,id asc' if deterministic else 's desc'
  q=f'select g,id,x,y from (select *,row_number() over(partition by g order by {order}) as n from t indexed by {index}) where n<=g+1 order by g,id'
  z=d.execute(q).fetchall()
  return [[g,i] for g,i,_,_ in z],tuple(sum(r[j] for r in z) for j in (2,3))
 a,b=(native(i,False) for i in ('ia','ib'))
 ae,be=(native(i,True) for i in ('ia','ib'))
 assert (a[1],b[1])==((6,1),(1,6)) and ae==be==a
 # Stable ID receipts selected under one policy are shared between downstream consumers.
 d.execute('create temp table shared(id integer primary key)')
 d.executemany('insert into shared values(?)',((i,) for _,i in a[0]))
 both=d.execute('select sum(x),sum(y) from t join shared using(id)').fetchone()
 assert both==a[1]
 impossible=(a[1][0],b[1][1])
 assert impossible not in points
rng=random.Random(120);checks=0
for _ in range(144):
 rows=[(g,g*10+i,rng.randrange(4),rng.randrange(-4,6),rng.randrange(-4,6)) for g in (0,1) for i in range(5)]
 p=with_quotas(rows);vals=full(p)
 for alpha,beta in it.product((-2,-1,0,1,2),repeat=2):
  scores=[alpha*x+beta*y for x,y in vals]
  assert range_only(p,alpha,beta)==(min(scores),max(scores));checks+=1
print(json.dumps({'sqlite':sqlite3.sqlite_version,'native_plan_a':a,'native_plan_b':b,'explicit_tie_breaker':ae,
 'shared_receipt_totals':both,'unshared_impossible_totals':impossible,'valid_exact_points':points,
 'linear_extrema_checks':checks},sort_keys=True,indent=2))
