"""Reusable stage receipt validator + native SQLite adapter + independent authored oracle."""
from pathlib import Path
import json,sqlite3,tempfile,hashlib,itertools

def digest(x):
 return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def oracle(m):
 rows=m['artifact']['rows'];e=m['derivation']['required_runtime_epoch']; quotas=m['output']['quota_by_group']
 assert m['schema']=='scoped-replay/v1'
 assert len({r[0] for r in rows})==len(rows)
 assert m['artifact']['rows']==sorted(m['artifact']['rows'])
 assert all(str(g) in quotas for _,g,_,_,on in rows if on)
 assert m['derivation']['rule']=='base + epoch * sensitivity'
 scores={i:b+e*s for i,g,b,s,on in rows if on}
 allowed=set()
 per_group=[]
 for g,k in sorted((int(g),k) for g,k in quotas.items()):
  eligible=[i for i,h,b,s,on in rows if on and g==h]
  assert 0<=k<=len(eligible)
  floor=sorted((scores[i] for i in eligible),reverse=True)[:k]
  per_group.append([ids for ids in itertools.combinations(eligible,k)
                    if sorted((scores[i] for i in ids),reverse=True)==floor])
 for c in itertools.product(*per_group):allowed.add(tuple(sorted(itertools.chain.from_iterable(c))))
 return scores,allowed
def check(m,r):
 scores,legal=oracle(m)
 return {
   'artifact':r['manifest_hash']==digest(m) and r['logical_rows_hash']==digest(m['artifact']['rows']),
   'derived':r['runtime_epoch']==m['derivation']['required_runtime_epoch'] and r['scores']==[[i,v] for i,v in sorted(scores.items())],
   'output':tuple(sorted(r['ids'])) in legal,
 }
def attach(path,epoch):
 d=sqlite3.connect(path)
 d.create_function('rank_score',2,lambda a,b:a+epoch*b,deterministic=True)
 return d
def run(m):
 out={}
 with tempfile.TemporaryDirectory() as tmp:
  p=Path(tmp)/'artifact.sqlite'
  d=attach(p,m['derivation']['materialization_epoch'])
  d.execute('create table t(id integer primary key,g integer,b integer,s integer,yes integer,stored integer generated always as (rank_score(b,s)) stored)')
  d.executemany('insert into t(id,g,b,s,yes) values(?,?,?,?,?)',m['artifact']['rows'])
  d.commit();d.close()
  old_bytes=p.read_bytes()
  e=m['derivation']['required_runtime_epoch']
  d=attach(p,e)
  logical=[list(r) for r in d.execute('select id,g,b,s,yes from t order by id')]
  for label,expr,tie in [('current-forward','rank_score(b,s)','asc'),
     ('current-reverse','rank_score(b,s)','desc'),('stale','stored','asc'),
     ('stale-but-allowed','case when g=0 then stored else rank_score(b,s) end','asc')]:
   quotas=m['output']['quota_by_group']
   d.execute('create temp table q(g integer primary key,k integer)')
   d.executemany('insert into q values(?,?)',((int(g),k) for g,k in quotas.items()))
   q=f'select id from (select id,g,row_number() over(partition by g order by ({expr}) desc,id {tie}) as n from t where yes=1) join q using(g) where n<=k'
   ids=[i for i, in d.execute(q)]
   scores=[list(r) for r in d.execute(f'select id,({expr}) from t where yes=1 order by id')]
   d.execute('drop table q')
   out[label]={'manifest_hash':digest(m),'logical_rows_hash':digest(logical),'runtime_epoch':e,'scores':scores,'ids':ids}
  assert p.read_bytes()==old_bytes
  d.close()
 return out
def main():
 m=json.load(open('manifest.json')); native=json.loads(json.dumps(run(m)))
 # Explicit schema authority intervention without changing native data: stale receipt provenance.
 entire=dict(native,**{'wrong-binding':dict(native['current-forward'],manifest_hash='different-contract'),
     'eligibility-mutant':dict(native['current-forward'],ids=[13,21])})
 verdicts={label:check(m,r) for label,r in entire.items()}
 assert verdicts=={
   'current-forward':dict(artifact=True,derived=True,output=True),
   'current-reverse':dict(artifact=True,derived=True,output=True),
   'stale':dict(artifact=True,derived=False,output=False),
   'stale-but-allowed':dict(artifact=True,derived=False,output=True),
   'wrong-binding':dict(artifact=False,derived=True,output=True),
   'eligibility-mutant':dict(artifact=True,derived=True,output=False)}
 assert native['current-forward']['ids']!=native['current-reverse']['ids']
 _,allowed=oracle(m)
 print(json.dumps({'sqlite':sqlite3.sqlite_version,'manifest_hash':digest(m),
   'allowed':sorted(allowed),
   'native_receipts':native,'verdicts':verdicts},indent=2,sort_keys=True))
if __name__=='__main__':main()
