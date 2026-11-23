import json
import platform
import numpy as np
import pandas as pd

# Neutral four-row finite data; expected sums derived only from plain Python lists.
keys=[2,5,2,7]; values=[13,17,23,29]
def expected(seq):
    out={}
    for k,v in zip(seq,values,strict=True):out[k]=out.get(k,0)+v
    return sorted(out.items())

def run(mode):
    a=pd.Series(keys, dtype="int64", name="key")
    df=pd.DataFrame({"value":values})
    if mode=="alias": alias=a[:]
    if mode=="before":a.iloc[0]=11
    gb=df.groupby(a,sort=True)
    if mode in ("alias","after"):a.iloc[0]=11
    got=[(int(k),int(v)) for k,v in gb.value.sum().items()]
    if mode=="alias":assert alias.tolist()==keys
    direct=[(int(k),int(v)) for k,v in df.groupby(a,sort=True).value.sum().items()]
    assert direct==expected(a.tolist())
    want=expected(([11,*keys[1:]] if mode=="before" else keys))
    return {"got":got,"expected":want,"pass":got==want,"regroup_from_current":direct}

out={}
if pd.__version__.startswith("2."):
    with pd.option_context("mode.copy_on_write",True):
        for m in ("after","alias","before","none"):out[m]=run(m)
else:
    for m in ("after","alias","before","none"):out[m]=run(m)
for m in ("alias","before","none"):assert out[m]["pass"]
print(json.dumps({"pandas":pd.__version__,"numpy":np.__version__,"python":platform.python_version(),"cow":("enabled" if pd.__version__.startswith("2.") else "default"),"cases":out},sort_keys=True))
