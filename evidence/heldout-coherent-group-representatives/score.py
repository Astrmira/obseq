from collections import Counter
from pathlib import Path
import hashlib,json
def read(name,expect):
    b=Path(name).read_bytes();assert hashlib.sha256(b).hexdigest()==expect
    return json.loads(b)
cases=read("CASES.json","4c1862db300aaa915957701225e7bc3fb692cf9c202f6db764c3fb61c1d158a2")
pred=read("PREDICTIONS.json","929c0c7601e4abf5d03b7fb3ee45e30fcdb0126104d68d787dd73649a63224c3")
truth={r['id']:r['accepted'] for r in read("SEALED_LABELS.json","bf950fdd516e48ade8824c7a276fcd39ce962b4b88aa6830ad238092d4bb7745")}
assert len(truth)==len(cases)==24 and set(truth)=={r['id'] for r in cases}
assert all(type(x) is bool for x in truth.values())
summ={}
for engine,methods in pred["predictions"].items():
    summ[engine]={}
    for m,verdict in methods.items():
        assert set(verdict)==set(truth)
        n=Counter(("true_" if b==truth[i] else "false_")+("accept" if b else "reject") for i,b in verdict.items())
        summ[engine][m]=dict(counts=n,false_accept=[i for i,b in verdict.items() if b and not truth[i]],
                                   false_reject=[i for i,b in verdict.items() if not b and truth[i]])
    assert not summ[engine]['coupled']['false_accept'] and not summ[engine]['coupled']['false_reject']
print(json.dumps(dict(scores=summ,source_accept=sum(truth.values()),source_reject=24-sum(truth.values()),
     versions=pred["engine_versions"]),sort_keys=True,indent=2))
