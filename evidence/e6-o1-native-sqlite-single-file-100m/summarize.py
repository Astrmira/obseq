import json,statistics as s,sys
from collections import defaultdict
obs=defaultdict(list)
for r in [json.loads(x) for x in open(sys.argv[1])]:
 assert r['n']==100000000 and r['valid'];r['hwm_delta_kib']=max(0,r['hwm_kib']-r['setup_hwm_kib']);obs[r['method']].append(r)
def S(a):
 q=s.quantiles(a,n=4,method='inclusive')
 return dict(median=s.median(a),q1=q[0],q3=q[2])
result={}
for m,ls in obs.items():
 reps=sorted(r['repeat'] for r in ls)
 assert len(reps)==len(set(reps))
 result[m]=dict(reps=reps)
 if len(ls)>=2:
  result[m].update({k:S([r[k] for r in ls]) for k in ('wall_ns','cpu_ns','hwm_kib','hwm_delta_kib')})
print(json.dumps(dict(cells=result,complete_five_each=len(result)==4 and all(x['reps']==list(range(5)) for x in result.values())),indent=2,sort_keys=True))
