import csv,hashlib,json,sys
from decimal import Decimal
from pathlib import Path
import duckdb
assert duckdb.__version__=="1.4.3"
from collections import Counter
p=Path(sys.argv[1]);R=json.loads((p/'MONITOR.json').read_text()); assert R['admitted_generator']
for fn,m in R['files'].items():
 with (p/fn).open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==m['sha256']
left=p/'J1_1e7_NA_5_0.csv';med=p/'J1_1e7_1e4_5_0.csv'
def t(s):return int(s) if s else None
def micros(s):
 if "e" in s.lower():
  v=Decimal(s)*1_000_000;assert int(v)==v;return int(v)
 y,d,tail=s.partition('.');assert len(tail)<=6
 return int(y)*1_000_000+int(tail.ljust(6,'0'))
with med.open(newline='') as f:
 q=csv.DictReader(f); M={}
 for r in q:
  k=t(r['id2']);assert k is not None and k not in M
  M[k]=micros(r['v2'])
assert len(M)==10_000
X=Counter();w={}
with left.open(newline='') as f:
 it=csv.reader(f);assert next(it)==['id1','id2','id3','id4','id5','id6','v1']
 for _,ki,ident,_,_,_,v1 in it:
  k=t(ki);X['rows']+=1
  if v1:X['v1_micros']+=micros(v1)
  if k in M:
   v2=M[k];X['matched']+=1;X['v2_micros']+=v2
   if ident and len(w)<2 and v2 not in w:w[v2]=int(ident)
  else:X['left_null' if k is None else 'left_nonnull_unmatched']+=1
assert X['rows']==10_000_000 and sum(X[k] for k in ('matched','left_null','left_nonnull_unmatched'))==X['rows']
con=duckdb.connect(config={'threads':1,'memory_limit':'560MB','max_temp_directory_size':'0B'})
L="read_csv(?, header=true, columns={'id1':'BIGINT','id2':'BIGINT','id3':'BIGINT','id4':'VARCHAR','id5':'VARCHAR','id6':'VARCHAR','v1':'DECIMAL(18,6)'})"
M0="read_csv(?, header=true, columns={'id1':'BIGINT','id2':'BIGINT','id4':'VARCHAR','id5':'VARCHAR','v2':'DECIMAL(18,6)'})"
col='count(*), count(m.id2), count(*) FILTER(WHERE l.id2 IS NULL), count(*) FILTER(WHERE l.id2 IS NOT NULL AND m.id2 IS NULL), sum(l.v1),sum(m.v2)'
expected=[X[k] for k in ('rows','matched','left_null','left_nonnull_unmatched','v1_micros','v2_micros')]
for op in ('=', 'IS NOT DISTINCT FROM'):
 s=con.execute(f'SELECT {col} FROM {L} l LEFT JOIN {M0} m ON l.id2 {op} m.id2',[str(left),str(med)]).fetchone()
 assert list(s[:4])+[int(v*1_000_000) for v in s[4:]]==expected
n0,n1=[con.execute(f'WITH l AS (SELECT NULL::BIGINT id2), m AS (SELECT NULL::BIGINT id2, 7 v2) SELECT sum(v2) FROM l LEFT JOIN m ON l.id2 {op} m.id2').fetchone()[0] for op in ('=','IS NOT DISTINCT FROM')]
assert (n0,n1)==(None,7)
[(v,a),(u,b)]=w.items()
assert a!=b and v!=u and {(a,v),(b,u)}!={(a,u),(b,v)} and v+u==u+v
Q=con.execute(f'SELECT l.id3,m.v2 FROM {L} l LEFT JOIN {M0} m ON l.id2=m.id2 WHERE l.id3 IN (?,?)',[str(left),str(med),a,b]).fetchall()
assert sorted((i,int(v*1_000_000)) for i,v in Q)==sorted([(a,v),(b,u)])
rawsum=con.execute(f"""SELECT sum(CAST(l.v1 AS DOUBLE)),
 sum(CAST(m.v2 AS DOUBLE)),sum(CAST(CASE WHEN l.id3=? THEN ? WHEN l.id3=? THEN ? ELSE m.v2 END AS DOUBLE))
 FROM {L} l LEFT JOIN {M0} m ON l.id2=m.id2""",[
 a,Decimal(u)/Decimal(1_000_000),b,Decimal(v)/Decimal(1_000_000),str(left),str(med)]).fetchone()
def print_chk(v):return str(round(v,3))
assert print_chk(rawsum[1])==print_chk(rawsum[2])
print(json.dumps(dict(duckdb=duckdb.__version__,q3_projection=X,join_literal_operator_and_nullsafe_equal_on_complete_source=True,authored_null_key_witness=dict(sql_eq=n0,nullsafe=n1),aggregate_q3_checksum_swap_keeps_defined_sum=True,double_three_decimal_sensitivity=dict(original=[print_chk(rawsum[0]),print_chk(rawsum[1])],swapped=[print_chk(rawsum[0]),print_chk(rawsum[2])]),
 swapped_distinct_payload_count=2,input_sha256={k:v['sha256'] for k,v in R['files'].items()}),sort_keys=True,indent=2))
