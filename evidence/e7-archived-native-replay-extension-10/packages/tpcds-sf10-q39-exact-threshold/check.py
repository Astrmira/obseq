import gzip,sys,json,struct,math
from fractions import Fraction
from decimal import Decimal,localcontext
from pathlib import Path
D=Path(sys.argv[1]); p=json.loads((D/'q39-result.json').read_text())
def closest(q):
 with localcontext() as c:
  c.prec=120
  a=float((Decimal(q.numerator)/Decimal(q.denominator)).sqrt())
 lo,hi=((Fraction.from_float(a)+Fraction.from_float(math.nextafter(a,side)))/2 for side in (-math.inf,math.inf))
 assert lo*lo<q<hi*hi
 return a
def bits(t):return struct.unpack('>Q',struct.pack('>d',t))[0]
seen=set(); changed=0
disagreements=[0,0]; max_error=[0,0]
def read_lines():
 paths=sorted(D.glob('q39-raw-part-*.jsonl'))
 if paths:
  for p in paths:
   with p.open() as f:yield from f
 else:
  with gzip.open(D/'q39-raw.jsonl.gz','rt') as f:yield from f
for line in read_lines():
  r=json.loads(line); k=tuple(r['key']); assert k not in seen;seen.add(k)
  f,g,h,i=map(Fraction,r['fractions']);assert min(f,h)>0 and min(g,i)>1
  expected=[float(f),closest(g),float(h),closest(i)]
  xs=[list(map(float.fromhex,r[t])) for t in ('t1','t4')]
  changed+=xs[0]!=xs[1]
  for j,x in enumerate(xs):
   delta=[abs(bits(a)-bits(b)) for a,b in zip(x,expected)]
   disagreements[j]+=sum(bool(e) for e in delta)
   max_error[j]=max(max_error[j],*delta)
assert len(seen)==p['output_groups'] and changed==p['binary64_row_changes']
for t,j in [(1,0),(4,1)]:
 assert disagreements[j]==p['native'][str(t)]['exact_binary64_disagreements']
 assert max_error[j]==p['native'][str(t)]['max_ulp']
print(f'verified {len(seen)} exact-rational keys and {changed} binary64-different rows')
