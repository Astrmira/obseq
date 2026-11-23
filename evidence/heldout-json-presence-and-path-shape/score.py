"""Score the already sealed native predictions; never train or revise them."""
from pathlib import Path
from collections import Counter
import hashlib, json

def read(name,expected=None):
    raw=Path(name).read_bytes()
    if expected: assert hashlib.sha256(raw).hexdigest()==expected
    return json.loads(raw)
cases=read("CASES.json","f3c4d8f0edc537fd9f3922fb4bc2b1a2f7507e52a4579ac1215d0bac3ef14f28")
pred=read("PREDICTIONS.json","85fa6837186ead44713191e34dba10031f485163f1e1a21020e6d7507d849d0d")
labels=read("SEALED_LABELS.json","9f619901162dfb3e79bb788aa36b5041e6ea7c2c8136753ca0a1d690d68802af")
lookup={r["id"]:r for r in labels}
assert len(lookup)==len(cases)==len(pred["predictions"])==24
assert {r["id"] for r in cases}==set(lookup)=={r["id"] for r in pred["predictions"]}
engines=("sqlite","duckdb","postgres")
ok=Counter();truth_counts=Counter();fail=[]
for p in pred["predictions"]:
    a=lookup[p["id"]]
    t=dict(status=a["status"],step=a.get("failure_step"))
    if t["status"]=="value":t["value"]=a["value"]
    if t["status"]=="explicit-null":assert a["value"] is None
    truth_counts[t["status"]]+=1
    for engine in engines:
        match=json.dumps(p[engine],sort_keys=True)==json.dumps(t,sort_keys=True)
        if match:ok[engine]+=1
        else:fail.append((p["id"],engine))
assert not fail,fail
non_values=sum(v for k,v in truth_counts.items() if k!="value")
print(json.dumps(dict(versions=pred["versions"],panel=24,exact_engine_matches=ok,truth_status_counts=truth_counts,
    collapsed_nonvalue_cases=non_values,distinct_collapsed_nonvalue_classes=len(truth_counts)-1,
    maximum_label_only_recall_among_collapsed_cases=max(v for k,v in truth_counts.items() if k!="value"),failures=fail),sort_keys=True,indent=2))
