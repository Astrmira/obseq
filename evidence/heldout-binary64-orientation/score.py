from pathlib import Path
from collections import Counter
import hashlib,json
def read(name,h):
    b=Path(name).read_bytes();assert hashlib.sha256(b).hexdigest()==h
    return json.loads(b)
cases=read("CASES.json","15517292a5562e086582ba6f6433e9c8d2f6e8238cf55057c7caeac6d183f476")
pred=read("PREDICTIONS.json","e09edaaef315a14642464f8d9786515615f5e2dc4e54773012432f92b9246f54")
truth={c['id']:c['sign'] for c in read("SEALED_LABELS.json","0a0fa5fbc60dbe16869fb1ba0f283dc4cdc90762de7470f5306775cab3bed3e2")}
assert len(cases)==len(truth)==len(pred['predictions'])==24
assert set(truth)=={c['id'] for c in cases}=={c['id'] for c in pred['predictions']}
assert all(type(v) is int and v in (-1,0,1) for v in truth.values())
diff={}
for alg in ("certified","stock_geos","plain_float","decimal_contract"):
    diff[alg]=[r['id'] for r in pred['predictions'] if r[alg]!=truth[r['id']]]
assert not diff['certified'],diff
print(json.dumps(dict(panel=len(cases),truth_signs=Counter(truth.values()),mismatch_ids=diff,
    fallback=sum(r['fallback'] for r in pred['predictions']),geos=pred['geos']),sort_keys=True,indent=2))
