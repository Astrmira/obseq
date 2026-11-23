"""Complete maximum forced quota for a pooled projected candidate."""
from collections import Counter,defaultdict
from datetime import datetime,timedelta
from pathlib import Path
import json,sys
import pyarrow.parquet as pq
from check import gate

def max_force(A,B,K):
    # Keep one exact feasible pooled bag maximizing the number forced into A.
    dp={0:(0,[])}
    labels=sorted((A+B).keys(),key=lambda x:(x is not None,x))
    for k in labels:
        post={}
        for n,(f,counts) in dp.items():
            for x in range(min(A[k]+B[k],K-n)+1):
                val=f+max(0,x-B[k]); tot=n+x
                if tot not in post or val>post[tot][0]: post[tot]=(val,counts+[x])
        dp=post
    v,c=dp[K]
    C=+Counter(dict(zip(labels,c)))
    assert C.total()==K and not C-(A+B)
    assert sum(max(0,n-B[k]) for k,n in C.items())==v
    return v,C

def run(p,receipt):
    rows=[]
    for x in receipt['cells']:
        start=datetime(2025,11,x['day'],x['hour']); end=start+timedelta(hours=1)
        t='tpep_pickup_datetime'; v='DOLocationID'
        ar=pq.read_table(p,columns=[t,v],filters=[(t,'>=',start),(t,'<',end)])
        by=defaultdict(Counter)
        for ts,y in zip(ar[t].to_pylist(),ar[v].to_pylist()): by[ts.replace(second=0,microsecond=0)][y]+=1
        bins=sorted(by)
        i,j=x['band_indices']
        A,B=by[bins[i]],by[bins[j]]
        M=sum((by[t] for t in bins[i+1:j]),Counter())
        l,r=x['left_take'],x['right_take']
        a,L=max_force(A,B,l+r)
        b,R=max_force(B,A,l+r)
        assert all(not (C-(A+B)) for C in (L,R))
        assert gate(A,B,M,L+M,l,r)==(a<=l)
        assert gate(A,B,M,R+M,l,r)==(b<=r)
        rows.append(dict(day=x['day'],hour=x['hour'],bands=[i,j],
            max_force_first=a,first_quota=l,max_force_last=b,last_quota=r,
            bad_first=a>l,bad_last=b>r))
    return dict(cells=rows,pooled_admissible_extreme_controls=2*len(rows),
        observable_rejections=sum(x['bad_first']+x['bad_last'] for x in rows))

if __name__=='__main__':
    print(json.dumps(run(Path(sys.argv[1]),json.loads(Path('RESULT.json').read_text())),sort_keys=True,indent=2))
