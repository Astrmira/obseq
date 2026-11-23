import sqlite3,itertools as it,random,json
def oracle(rows,k):
 # Check independently from SQL: exact permitted subsets by sorted score multiset.
 out=set()
 benchmark=tuple(sorted((s for _,s in rows),reverse=True)[:k])
 for subset in it.combinations(rows,k):
  if tuple(sorted((s for _,s in subset),reverse=True))==benchmark:
   out.add(tuple(sorted(i for i,_ in subset)))
 return out
def guard(rows,k,s):
 scores=dict(rows)
 if len(s)!=k or len(set(s))!=k or any(i not in scores for i in s):return False
 if k==0:return True
 theta=sorted(scores.values(),reverse=True)[k-1]
 return {i for i,v in rows if v>theta}<=set(s)<={i for i,v in rows if v>=theta}
def native(rows,k):
 with sqlite3.connect(':memory:') as d:
  d.execute('create table t(id integer primary key, score integer not null)')
  d.executemany('insert into t values(?,?)',rows)
  d.execute('create index ia on t(score desc,id asc)')
  d.execute('create index ib on t(score desc,id desc)')
  outputs={}
  for index in ('ia','ib'):
   q=f'select id from (select id,row_number() over(order by score desc) as n from t indexed by {index}) where n<=? order by id'
   outputs[index]=tuple(i for i, in d.execute(q,(k,)))
 return outputs
base=[(10,100),(11,90),(12,90),(13,90),(14,80)]
baseout=native(base,3)
assert baseout['ia']!=baseout['ib']
assert set(baseout.values())<=oracle(base,3)
assert not guard(base,3,(10,11,15)) and not guard(base,3,(10,11,14))
# A score-only claimed receipt can be indistinguishable when identity or eligibility is wrong.
# 15 has a score but is excluded from the contract's eligible identity universe.
score_map=dict(base)|{15:90}
assert sorted(score_map[i] for i in (10,11,15))==sorted(score_map[i] for i in baseout['ia'])
tags={10:0,11:1,12:2,13:4,14:9}
legal_totals=sorted({sum(tags[i] for i in ids) for ids in oracle(base,3)})
assert legal_totals==[3,5,6]
assert [sum(tags[i] for i in ids) for ids in baseout.values()]==[3,6]
rng=random.Random(119);case_count=0;literal_tests=0;different=0
for n in range(1,10):
 for _ in range(12):
  rows=[(i,rng.randrange(-3,4)) for i in range(1,n+1)]
  k=rng.randrange(1,n+1)
  allowed=oracle(rows,k);out=native(rows,k)
  assert set(out.values())<=allowed
  for sel in it.combinations(range(1,n+1),k):
   assert guard(rows,k,sel)==(sel in allowed)
   literal_tests+=1
  case_count+=1;different+=out['ia']!=out['ib']
print(json.dumps({'sqlite':sqlite3.sqlite_version,'same_native_query_valid_witnesses':baseout,
 'valid_downstream_totals':legal_totals,'native_cases':case_count,'different_valid_native_results':different,'literal_allowed_set_checks':literal_tests},sort_keys=True,indent=2))
