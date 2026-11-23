"""Unmodified shared contract functions copied from the reference harness."""
import hashlib,json,itertools

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
