from pathlib import Path
from collections import Counter
r=Path(__file__).resolve().parent
def read(n):return [tuple(x.split('\t')) for x in (r/n).read_text().splitlines()]
base,delta,result=map(read,('PRIOR-REPLAY.tsv','NEW-REPLAY.tsv','REPLAY.tsv'))
assert base+delta==result and len({x[0] for x in result})==95
assert Counter(x[1] for x in delta)=={'native_authored_development':2,'native_external_transfer':6}
assert Counter(x[1] for x in result).get('native_authored_development')==57
assert Counter(x[1] for x in result).get('native_external_transfer')==37
assert all(x[2]=='PASS' for x in delta)
print('E7: 94 actual archived replays; 1 prior receipt-only')
