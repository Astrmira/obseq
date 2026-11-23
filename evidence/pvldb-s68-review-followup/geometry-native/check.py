import collections,csv,hashlib,json,statistics,sys,struct
from fractions import Fraction as Q
from pathlib import Path
N=100_000_000; W=243727
D=Path(__file__).parent
rows=list(csv.DictReader((D/'RAW.csv').open()))
arms={int(m):[r for r in rows if int(r['mode'])==m] for m in range(3)}
assert len(rows)==15
expected=tuple(map(int,[arms[1][0][k] for k in ('negative','zero','positive')]))
assert sum(expected)==N
for mode,rs in arms.items():
 assert {int(r['rep']) for r in rs}==set(range(5))
 assert all(int(r['n'])==N and not int(r['mismatches']) for r in rs)
 assert all(tuple(int(r[k]) for k in ('negative','zero','positive'))==(expected if mode else (0,0,0)) for r in rs)
 assert len({(r['fallback'],r['producer_token']) for r in rs})==1
if len(sys.argv)>1:
 raw=Path(sys.argv[1]).read_bytes()
 assert hashlib.sha256(raw).hexdigest()=='45d8fd37248476e4f83f0ba6314d49514e308329697e38b763f18e03c7243f19'
 wedge=list(struct.iter_unpack('<6d',raw))
 labels=bytearray()
 unsigned=struct.iter_unpack('<6Q',raw)
 s=[0,0];x=[0,0];y=[0,0]; f=[0,0]
 for i,(r,bits) in enumerate(zip(wedge,unsigned)):
  a,b,c,d,e,g=map(Q,r)
  z=(c-a)*(g-b)-(d-b)*(e-a)
  labels.append(1+(z>0)-(z<0))
  p,q=(r[0]-r[4])*(r[3]-r[5]),(r[1]-r[5])*(r[2]-r[4])
  for j in range(1+(i<N%W)):
   s[j]+=sum(bits)
   x[j]+=sum(z!=0 for z in r[::2])
   y[j]+=sum(z!=0 for z in r[1::2])
   f[j]+=not abs(p-q)>(3+16*2.**-53)*2.**-53*(abs(p)+abs(q))
 assert hashlib.sha256(labels).hexdigest()=='ec28fa8322b34953da30154b344344606f2b6aef75973c7ff58ce8e0bf40ffb5'
 if len(sys.argv)>2:Path(sys.argv[2]).write_bytes(labels)
 allc,partial=collections.Counter(labels),collections.Counter(labels[:N%W])
 assert expected==tuple((N//W)*allc[i]+partial[i] for i in range(3))
 assert int(arms[2][0]['fallback'])==N//W*f[0]+f[1]
 token=sum(s[k==N//W]+(1<<52)*((k%21-10)*x[k==N//W]+(k//21-10)*y[k==N//W]) for k in range(N//W+1))%(1<<64)
 assert token==int(arms[0][0]['producer_token'])
stats={}
for k,rs in arms.items():
 x=[int(r['ns']) for r in rs]
 q=statistics.quantiles(x,n=4,method='inclusive')
 stats[k]=dict(samples_ns=x,median_ns=statistics.median(x),inclusive_iqr_ns=q[2]-q[0],quartiles_ns=q,rss_kib=[int(r['rss_kib']) for r in rs],fallback=int(rs[0]['fallback']))
print(json.dumps(dict(n=N,native=W,full_variants=N//W,partial_seeds=N%W,sign_counts=expected,producer_token=int(arms[0][0]['producer_token']),stats=stats),indent=2))
