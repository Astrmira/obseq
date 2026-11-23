from collections import defaultdict
from pathlib import Path
from statistics import median
import csv,json
rows=list(csv.DictReader(open('RAW.csv')))
assert len(rows)==16
assert Path('LABELS.sha256').read_text().strip()=='ec28fa8322b34953da30154b344344606f2b6aef75973c7ff58ce8e0bf40ffb5'
groups=defaultdict(list)
cdf={}
for r in rows:
    k,m=r['workload'],r['method']
    assert k in ('native_tiled','pressure') and m in ('fixedpoint','filtered') and int(r['n'])==100_000_000
    b=tuple(int(r[x]) for x in ['negative','zero','positive'])
    assert sum(b)==100_000_000
    assert b==cdf.setdefault(k,b)
    assert int(r['fallback'])==(0 if m=='fixedpoint' else {'native_tiled':21744,'pressure':1583907}[k])
    groups[k,m].append(int(r['nanos']))
summary={k:{m:int(median(groups[k,m])) for m in ('fixedpoint','filtered')}
         for k in ('native_tiled','pressure')}
print(json.dumps(dict(medians_ns=summary,original_wedge_labels=243727,labels_sha256=Path('LABELS.sha256').read_text().strip(),
    native_tiled_label_counts=cdf['native_tiled'],pressure_label_counts=cdf['pressure'],RSS=Path('RESOURCE.txt').read_text().strip()),sort_keys=True,indent=2))
