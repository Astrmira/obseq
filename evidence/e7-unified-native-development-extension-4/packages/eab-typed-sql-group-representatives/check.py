import json,sqlite3,random
from fractions import Fraction
def kind(v):
 return {type(None):'null',bytes:'blob',str:'text',int:'integer',float:'real'}[type(v)]
def group(v):
 k=kind(v)
 return ('number',Fraction(v)) if k in ('integer','real') else (k,v)
def wire(v):return v.hex() if isinstance(v,bytes) else v
def test(vals):
 expected={};counts={}
 for i,v in enumerate(vals,1):
  expected.setdefault(group(v),(i,kind(v),v))
  counts[group(v)]=counts.get(group(v),0)+1
 outcomes={}
 with sqlite3.connect(':memory:') as d:
  d.execute('create table t(seq integer primary key,x any) strict')
  d.executemany('insert into t values(?,?)',enumerate(vals,1))
  assert d.execute('select seq,typeof(x),x from t order by seq').fetchall()==[(i,kind(v),v) for i,v in enumerate(vals,1)]
  for mode,index in [('forward','ia'),('reverse','ib')]:
   flag='asc' if mode=='forward' else 'desc'
   d.execute(f'create index {index} on t(seq {flag},x)')
   rows=d.execute(f'select x,typeof(x),n from (select x,count(*) as n from t indexed by {index} group by x)').fetchall()
   assert {group(v):n for v,ty,n in rows}==counts
   assert len(rows)==len(counts) and all(kind(v)==ty for v,ty,n in rows)
   dist=d.execute(f'select x,typeof(x) from (select distinct x from t indexed by {index})').fetchall()
   assert len(dist)==len(counts) and {group(v) for v,_ in dist}==counts.keys()
   assert all(any(group(v)==group(a) and vt==kind(a) for a in vals) for v,vt in dist)
   q=f'select seq,typeof(x),x from (select *,row_number() over (partition by x order by seq) n from t indexed by {index}) where n=1 order by seq'
   can=d.execute(q).fetchall()
   assert can==sorted(expected.values())
   # STRICT ANY checks actual downstream physical representation; no affinity recast.
   d.execute('create temp table dest(k any) strict')
   d.executemany('insert into dest values(?)',((v,) for v,_ in dist))
   physical=d.execute("select typeof(k),count(*) from dest group by typeof(k) order by 1").fetchall()
   d.execute('drop table dest')
   outcomes[mode]={'dist':[[wire(v),t] for v,t in dist],'storage_class_counts':physical,
                   'canonical_ids':[i for i,_,_ in can]}
 return outcomes
base=test([1,1.0,'1',b'1',None,None,1.0])
assert base['forward']['storage_class_counts']!=base['reverse']['storage_class_counts']
assert base['forward']['canonical_ids']==base['reverse']['canonical_ids']==[1,3,4,5]
rng=random.Random(121)
pool=[None,0,0.,1,1.,-1,-1.,2**53,2**53+1,float(2**53),'1','1.0',b'1',b'1.0','',b'']
changed=0
for i in range(96):
 got=test(rng.choices(pool,k=rng.randrange(6,24)))
 changed+=got['forward']['storage_class_counts']!=got['reverse']['storage_class_counts']
print(json.dumps({'sqlite':sqlite3.sqlite_version,'matched_base':base,'seeded_native_cases':96,
 'different_valid_class_histograms':changed},indent=2,sort_keys=True))
