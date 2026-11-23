import json
from pathlib import Path
from collections import Counter,defaultdict
observed=json.loads(Path('OBSERVED.json').read_text())
labs={x['id']:x['legal'] for x in json.loads(Path('SEALED_LABELS.json').read_text())}
assert len(labs)==24 and set(labs)==set(observed['cases'])
counts=defaultdict(lambda:defaultdict(Counter))
for id,c in observed['cases'].items():
    for engine,policy in c.items():
        for method,d in policy.items():
            counts[engine][method]['TP' if d and labs[id] else 'FP' if d else 'FN' if labs[id] else 'TN']+=1
print(json.dumps(counts,indent=2,sort_keys=True))
