"""Check the frozen measured matrix and an independent exact authored stress summary."""
from collections import Counter
from fractions import Fraction
from pathlib import Path
import json,statistics
def s(x):return (x>0)-(x<0)
native_fail=Counter()
for i in range(300):
    t=float(10**8-i%999)
    a,b,c,d,e,f=[t,t-1.,t-1.,t-2.,0.,0.] if i%3==0 else [t-1.,t-2.,t,t-1.,0.,0.] if i%3==1 else [t,t,t-1.,t-1.,0.,0.]
    u,v,w,x,y,z=map(Fraction,(a,b,c,d,e,f))
    k=s((w-u)*(z-v)-(x-v)*(y-u))
    assert k==(-1,1,0)[i%3]
    if k!=s((a-e)*(d-f)-(b-f)*(c-e)):native_fail[k]+=1
output={}
for n in (1000,100000,243727,1000000):
    r=json.loads(Path(f'{n}.json').read_text())
    assert r['n']==n and r['ring_pool']==243727 and r['gdal']=='3.10.3'
    assert r['hard_control_geos_mismatch']==0
    output[n]={}
    for mode,obs in r['measurements'].items():
        assert sum(obs['label_counts'].values())==n
        assert obs['fallback_count']>=0 and len(obs['exact_labels_sha'])==64
        assert all(len(v)==3 and min(v)>0 for v in obs['samples'].values())
        assert obs['median_ns']=={k:statistics.median(v) for k,v in obs['samples'].items()}
        output[n][mode]={k:obs[k] for k in ('fallback_count','median_ns')}
    if n==243727:
        panel=r['ring_native_comparison']
        assert sum(v['n'] for v in panel.values())==243727
        assert sum(v['candidate_uncertified'] for v in panel.values())==53
        assert all(v['geos_sign_mismatch']==v['float_sign_mismatch']==0 for v in panel.values())
print(json.dumps(dict(no_filter_float_hard_mismatch=sum(native_fail.values()),frozen_measurements=output),
                 sort_keys=True,indent=2))
