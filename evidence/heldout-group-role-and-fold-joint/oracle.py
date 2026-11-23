"""Independent stdlib finite specification, not a SQL implementation."""
import itertools as it
import json
from pathlib import Path
from collections import defaultdict

def canon(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'))

def group(c):
    # Distinguish real NULL and rolled-away NULL by retaining mask 0,1,3.
    groups=defaultdict(int)
    for a,b,v in c["rows"]:
        for key in ((a,b,0),(a,None,1),(None,None,3)):
            groups[key]+=v
    by_value=defaultdict(list)
    for (a,b,m),v in groups.items():
        by_value[v].append((a,b,v,m))
    peers=[by_value[v] for v in sorted(by_value,reverse=True)]
    out={}
    # Enumerate every peer linearization. Return bags; tie orders are not observed.
    for p in it.product(*(it.permutations(tier) for tier in peers)):
        all_rows=list(it.chain.from_iterable(p))
        k=c["k"]
        if c["selection"]=="limit":
            o=c["offset"]
            selected=all_rows[o:o+k]
        else:
            selected=[]
            for i,tier in enumerate(p):
                r=1+(i if c["selection"]=="dense_rank" else sum(map(len,p[:i])))
                if r<=k:
                    selected.extend(tier)
        full=sorted(selected,key=canon)
        out[canon(full)]=full
    detailed=list(out[key] for key in sorted(out))
    views={canon(sorted((r[:3] for r in bag),key=canon)) for bag in detailed}
    return dict(role_bags=detailed,projected_bags=[json.loads(x) for x in sorted(views)])

def civil(c):
    tr,old,new=[c[k] for k in ("transition_utc","offset_before","offset_after")]
    assert old>new
    def candidates(x):
        # All integer UTC minutes with that local reading, not a resolver's default fold.
        return [u for u in range(x-old,x-new+1) if x==u+(old if u<tr else new)]
    a,b=map(candidates,(c["start_local"],c["end_local"]))
    pairs=[[u,v,v-u] for u,v in it.product(a,b) if v>=u]
    return dict(start_utc=a,end_utc=b,joint=pairs,durations=sorted({r[2] for r in pairs}),
                matching_observation=[r for r in pairs if r[2]==c["observed_duration"]])
def compute(inputs):
    assert len({c["id"] for c in inputs})==len(inputs)
    return {c["id"]:(group if c["family"]=="group" else civil)(c) for c in inputs}
if __name__=="__main__":
    print(json.dumps(compute(json.loads((Path(__file__).parent/"inputs.json").read_text())),indent=2))
