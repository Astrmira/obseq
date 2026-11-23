from pathlib import Path
from collections import Counter
import hashlib, json
r=Path(__file__).resolve().parent
def rec(name):return [tuple(x.split('\t')) for x in (r/name).read_text().splitlines()]
base,delta,merged=map(rec,['PRIOR-REPLAY.tsv','NEW-REPLAY.tsv','REPLAY.tsv'])
assert base+delta==merged and len(merged)==len(set(x[0] for x in merged))==101
assert Counter((k,s) for _,k,s in merged)=={
 ('native_authored_development','PASS'):58,('native_external_transfer','PASS'):40,
 ('native_external_transfer','PASS_stable'):2,('receipt_only','PASS'):1}
assert Counter(s for _,_,s in delta)=={'PASS':4,'PASS_stable':2}
pin=json.loads((r/'BASE-PINS.json').read_text())['roots']
byid={}
for a in range(5,10):
 raw=(r/f'BASE-{a}.json').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==pin[f'extension-{a}']['manifest_sha256']
 for x in json.loads(raw)['cases']:
  assert x['case_id'] not in byid
  byid[x['case_id']]=x
for x in json.loads((r/'MANIFEST.json').read_text())['cases']:
 assert x['case_id'] not in byid
 byid[x['case_id']]=x
 for n,d in x['blobs'].items():
  assert hashlib.sha256((r/'packages'/x['case_id']/n).read_bytes()).hexdigest()==d['sha256']
assert set(byid)=={x[0] for x in merged}
print('E7: 100 actual (98 byte-exact, 2 deterministic semantic); 1 historical receipt-only')
