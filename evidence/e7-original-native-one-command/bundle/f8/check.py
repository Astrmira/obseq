import hashlib
import importlib.util
import json
import sys
from pathlib import Path

base=Path(__file__).resolve().parent
data=Path(sys.argv[1])
p=data/'BLIND.json'; q=data/'check.py'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
assert sha(p)=='8e86163e65e0deaa46f3450f7600aa03361141f9406e73b235e0c648a5804831'
assert sha(q)=='f005d93a52f8a4b69f772ef5c81a1cdc469df4c93a695f2f8ac24b57292b1cb6'
native=base/'NATIVE.json'
assert sha(native)==(base/'NATIVE.lock').read_text().split()[0]
o=importlib.util.spec_from_file_location('holdout_oracle',q)
oracle=importlib.util.module_from_spec(o);o.loader.exec_module(oracle)
rows=json.loads(native.read_bytes())['rows']
by={r['case_id']:r for r in json.loads(p.read_bytes()) if r['class']=='F8'}
comps=[]
for n in rows:
    row=by[n['case_id']]
    expected=n['output']
    legal=oracle.legal(row)
    assert oracle.legal(dict(row,candidate=expected))
    observed=expected==row['candidate']
    assert observed==legal
    comps.append(dict(case_id=row['case_id'],adapter=n['adapter'],scope=n['scope'],
        native_expected=expected,historical_candidate=row['candidate'],
        native_candidate_accepted=observed,reference_candidate_accepted=legal))
assert len(comps)==12 and len({(r['case_id'],r['adapter']) for r in comps})==12
assert set(row['case_id'] for row in comps)==set(by) and len(by)==6
assert sum(r['native_candidate_accepted'] for r in comps)==6
assert sum(r['scope']=='native_named_timezone' for r in comps)==8
print(json.dumps(dict(native_decisions=comps,case_ids=len(by),decisions=len(comps),
   named_native=8,authored_policy_native_primitives=4,
   oracle_agreements=12,accept_count=6,reject_count=6),sort_keys=True,indent=2))
