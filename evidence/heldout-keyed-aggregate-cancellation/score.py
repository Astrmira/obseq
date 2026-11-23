from pathlib import Path
from collections import Counter,defaultdict
import json
ob=json.loads(Path('OBSERVED.json').read_text())
labels={r['id']:r['legal'] for r in json.loads(Path('SEALED_LABELS.json').read_text())}
assert set(labels)==set(ob['cases']) and Counter(labels.values())=={True:12,False:12}
out=defaultdict(lambda:defaultdict(Counter))
for i,cs in ob['cases'].items():
    for db,methods in cs.items():
        for name,got in methods.items():
            out[db][name]['TP' if labels[i] and got else 'TN' if not labels[i] and not got else 'FP' if got else 'FN']+=1
print(json.dumps(out,sort_keys=True,indent=2))
