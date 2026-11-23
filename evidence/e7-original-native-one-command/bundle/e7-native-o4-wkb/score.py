from pathlib import Path
import json,csv,hashlib
from collections import defaultdict,Counter
P=Path(__file__).resolve().parent
for line in (P/'../e7-scored/PREDICTIONS.lock').read_text().splitlines():
 h,name=line.split()
 assert hashlib.sha256((P/'../e7-scored'/name).read_bytes()).hexdigest()==h
read=lambda p:json.loads((P/p).read_text())
pred={r['case_id']:r['predicted_legal'] for r in read('../e7-scored/PREDICTIONS.json') if r['subtype']=='equivalent WKB'}
raw=read('MEASURED.json')
assert set(pred)=={r['case_id'] for r in raw['rows']}
methods=['gdal_typed','geos_typed','byte_equality','gdal_typeblind_unordered','geos_topology']
tot=defaultdict(Counter);out=[]
for r in raw['rows']:
 e=pred[r['case_id']]
 for k in methods:
  y=r[k]
  v='no_predicate' if y is None else 'correct' if y==e else 'false_accept' if y else 'false_reject'
  tot[k][v]+=1
  out.append(dict(case_id=r['case_id'],method=k,legal=e,value=y,status=v))
with open('SCORES.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
print(json.dumps(dict(engines=raw['engines'],totals=tot,scores=out),indent=2))
