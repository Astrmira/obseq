from collections import defaultdict
from decimal import Decimal,localcontext
from fractions import Fraction
from pathlib import Path
import sys,json,math,struct,gzip,hashlib
E,W=map(Path,sys.argv[1:3]);sys.path.insert(0,str(E/'input/duck143'));import duckdb
db=duckdb.connect(str(W/'tpcds.duckdb'),read_only=True,config={'memory_limit':'1300MB','threads':'2','max_temp_directory_size':'800MB','temp_directory':str(W/'spill-q39')})
date_all={id:(yr,mo) for id,yr,mo in db.execute('select d_date_sk,d_year,d_moy from date_dim').fetchall()}
date={id:mo for id,(yr,mo) in date_all.items() if yr==2001 and mo in (1,2)}
item={x[0] for x in db.execute('select i_item_sk from item').fetchall()};wh={x[0] for x in db.execute('select w_warehouse_sk from warehouse').fetchall()}
assert len(date)==59
stat=defaultdict(lambda:[0,0,0]); cur=db.execute('select inv_date_sk,inv_item_sk,inv_warehouse_sk,inv_quantity_on_hand from inventory where inv_date_sk between ? and ?', [min(date),max(date)])
scanned=0; rows=0
while C:=cur.fetchmany(50000):
 scanned+=len(C)
 for d,i,w,v in C:
  if d in date and i in item and w in wh and v is not None:
   assert v>=0
   rows+=1;g=stat[w,i,date[d]];g[0]+=1;g[1]+=v;g[2]+=v*v
G={}; equal=0; min_pos=None
for k,(n,s,sq) in stat.items():
 if n<=1 or not s:continue
 cv2=Fraction(n*(n*sq-s*s),(n-1)*s*s)
 equal+=cv2==1
 if cv2!=1:
  dist=abs(cv2-1); min_pos=dist if min_pos is None else min(min_pos,dist)
 if cv2>1:G[k]=(Fraction(s,n),cv2)
refs={k[:2]:(v,G[k[:2]+(2,)]) for k,v in G.items() if k[2]==1 and k[:2]+(2,) in G}
def closest_sqrt(q):
 with localcontext() as c:
  c.prec=80
  a=float((Decimal(q.numerator)/Decimal(q.denominator)).sqrt())
 low,high=(Fraction.from_float(math.nextafter(a,side))+Fraction.from_float(a) for side in (-math.inf,math.inf))
 assert (low/2)**2<q<(high/2)**2, ('exact midpoint or misround',q)
 return a
def bits(t):return struct.unpack('>Q',struct.pack('>d',t))[0]
ext=E/'input/ext143/tpcds.duckdb_extension'
assert hashlib.sha256(ext.read_bytes()).hexdigest()=="0dc0c8fcdc401257a3dceeffc1675111beb6358913ab50ffd46bc24fb581ca02"
db.execute("LOAD '"+str(ext.absolute()).replace("'","''")+"'")
q,=db.execute("SELECT query FROM tpcds_queries() WHERE query_nr=39").fetchone()
assert hashlib.sha256(q.encode()).hexdigest()=="a8b5c4867a595122e52f3823ceb116729c8ea4ad80cb446bab230982e96bd6be"
strong={k:[float(a),closest_sqrt(b),float(c),closest_sqrt(d)] for k,((a,b),(c,d)) in refs.items()}
receipt={}; v={}
for th in (1,4):
 db.execute(f'SET threads={th}')
 out=db.execute(q).fetchall()
 assert len(out)==len(refs)
 result={}
 for w,i,m,mean,cv,w2,i2,m2,mean2,cv2 in out:
  assert m==1 and m2==2 and (w,i)==(w2,i2) and (w,i) not in result and (w,i) in refs
  result[w,i]=(mean,cv,mean2,cv2)
 v[th]=result
 threshold_q=q.split("\nSELECT inv1.",1)[0]+"\nSELECT w_warehouse_sk,i_item_sk,d_moy FROM inv WHERE d_moy IN (1,2)"
 admitted=set(db.execute(threshold_q).fetchall())
 malformed_threshold={'extra':len(admitted-set(G)),'missing':len(set(G)-admitted)}
 receipt[th]={'month_predicate_binary64_vs_exact_mismatch':malformed_threshold,'max_ulp':max(abs(bits(x)-bits(y)) for k,l in result.items() for x,y in zip(l,strong[k])),
              'exact_binary64_disagreements':sum(x!=y for k,l in result.items() for x,y in zip(l,strong[k]))}
with gzip.GzipFile(filename='',mode='wb',fileobj=(W/'q39-raw.jsonl.gz').open('wb'),mtime=0) as raw:
 for k in sorted(refs):
  line={'key':k,'fractions':[str(x) for vals in refs[k] for x in vals],'t1':[x.hex() for x in v[1][k]],'t4':[x.hex() for x in v[4][k]]}
  raw.write(json.dumps(line,separators=(',',':'),sort_keys=True).encode()+b'\n')
print(json.dumps({'binary64_row_changes':sum(v[1][k]!=v[4][k] for k in refs),'engine':duckdb.__version__,'enumerated_nonnull_source_rows':rows,'inventory_date_range_rows':scanned,'tested_jan_feb_groups':len(stat),'exact_equal_threshold_groups':equal,'min_nonzero_abs_cv2_gap_to_threshold':str(min_pos),'output_groups':len(refs),'native':receipt,'query_sha256':hashlib.sha256(q.encode()).hexdigest()},indent=2,sort_keys=True))
