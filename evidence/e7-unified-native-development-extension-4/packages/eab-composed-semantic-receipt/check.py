import json,sqlite3,sys
import pandas as pd
m=json.load(open('manifest.json')); got=json.load(sys.stdin)
assert m['schema']=='patch-join/v1' and m['key']=='signed-int64-nullable'
updates={i:(op,v) for i,op,v in m['patch']}
exp={i:(k if updates[i][0]=='KEEP' else updates[i][1],c) for i,k,c in m['rows']}
# Check manifest uniqueness, coverage and action well-formedness.
assert list(exp)==[i for i,_,_ in m['patch']] and len(exp)==len(m['rows'])
assert all(op in ('KEEP','CLEAR','WRITE') and ((v is not None)==(op=='WRITE')) for _,op,v in m['patch'])
rgt=m['right']
assert len({i for i,k in rgt})==len(rgt)
with sqlite3.connect(':memory:') as d:
 d.execute('create table l(id integer primary key,k integer)')
 d.execute('create table r(id integer primary key,k integer)')
 d.executemany('insert into l values(?,?)',((i,k) for i,(k,c) in exp.items()))
 d.executemany('insert into r values(?,?)',rgt)
 oracle={}
 for j in m['join_modes']:
  safe=j=='null_safe';op='IS NOT DISTINCT FROM' if safe else '='
  exact={(i,t) for i,(k,_) in exp.items() for t,u in rgt if k==u and (k is not None or safe)}
  assert exact==set(d.execute(f'select l.id,r.id from l join r on l.k {op} r.k'))
  oracle[j]=exact
def frame(rows,name,typed):
 ids,ks=zip(*rows)
 return pd.DataFrame({name:ids,'k':pd.array(pd.Series(ks,dtype=object),dtype='Int64') if typed else ks})
records={}
for arm,g in got.pop('writes').items():
 rows={i:(k,c) for i,k,c in g['rows']}
 status_errors=[i for i,e in g['statuses'] if e!=0]
 assert len(rows)==len(g['rows']) and [i for i,_ in g['statuses']]==list(exp)
 changed=sorted(i for i in rows.keys()|exp.keys() if rows.get(i)!=exp.get(i))
 joins={}
 for typed in (False,True):
  for mode in m['join_modes']:
   L=frame([(i,k) for i,(k,c) in rows.items()],'lid',typed);R=frame(rgt,'rid',typed)
   if mode=='eq':L=L[L.k.notna()];R=R[R.k.notna()]
   j=L.merge(R,on='k')
   pairs=set(zip(j.lid,j.rid));assert len(j)==len(pairs)
   delta=dict(extra=sorted(pairs-oracle[mode]),missing=sorted(oracle[mode]-pairs))
   joins[f'{mode}-'+('typed' if typed else 'default')]=delta
 records[arm]={'status_errors':status_errors,'changed_states':changed,'joins':joins}
assert not records['complete']['changed_states'] and not records['complete']['status_errors']
assert all(not z for k,v in records['complete']['joins'].items() if k.endswith('-typed') for z in v.values())
assert records['complete']['joins']['eq-default']['extra']
assert records['normalize-all']['changed_states']==[1]
assert records['normalize-all']['joins']['eq-typed']['missing']==[(1,21)]
assert records['normalize-all']['joins']['null_safe-typed']['extra']==[(1,23)]
assert records['sparse']['status_errors'] and not records['sparse']['changed_states']
print(json.dumps({'versions':dict(got,pandas=pd.__version__), 'oracle':{k:sorted(v) for k,v in oracle.items()},'records':records},indent=2,sort_keys=True))
