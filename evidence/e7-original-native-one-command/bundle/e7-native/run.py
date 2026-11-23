import csv, json, os, sys, sqlite3, math, re
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
import hashlib
P=Path(__file__).resolve().parent
for line in (P/'ADAPTER.lock').read_text().splitlines():
 h,f=line.split()
 assert hashlib.sha256((P/f).read_bytes()).hexdigest()==h, f
for pa in (P/'../e1/input/more',P/'../e1/input/duck143'):sys.path.insert(0,str(pa.resolve()))
import duckdb, polars as pl, datafusion, pyarrow as pa
ENG={'sqlite':sqlite3.sqlite_version,'duckdb':duckdb.__version__,'polars':pl.__version__,'datafusion':datafusion.__version__}

def schema_types(r,i):
 u={type(k[i]) for k in r if k[i] is not None}
 assert len(u)<=1
 return next(iter(u),str)
def _sql(e,tab,q):
 if e=='datafusion':
  ctx=datafusion.SessionContext()
  for name,(cols,rows,types) in tab.items():
   sch=pa.schema([(c,pa.int64() if t is int else pa.string()) for c,t in zip(cols,types)])
   batch=pa.RecordBatch.from_pylist([dict(zip(cols,r)) for r in rows],schema=sch)
   ctx.register_record_batches(name,[[batch]])
  return [tuple(d.values()) for b in ctx.sql(q).collect() for d in b.to_pylist()]
 c=sqlite3.connect(':memory:') if e=='sqlite' else duckdb.connect()
 try:
  for name,(cols,rows,types) in tab.items():
   c.execute(f'CREATE TABLE {name} ('+','.join(c0+(' BIGINT' if t is int else ' VARCHAR') for c0,t in zip(cols,types))+')')
   c.executemany(f'INSERT INTO {name} VALUES ('+','.join('?' for _ in cols)+')',rows)
  return c.execute(q).fetchall()
 finally:c.close()
def frame(cols,rows,types):
 return pl.DataFrame(rows,schema=[(c,pl.Int64 if t is int else pl.String) for c,t in zip(cols,types)],orient='row')
def f1_setup(r):
 x,c=r['inputs'],r['candidate']
 keys={
  'match':(['left','right'],lambda z:tuple(z[k] for k in ('left','right')),lambda a,b:int(a)==int(b)),
  'value':(['R'],lambda z:(z['R'],),lambda a:int(a)),
  'groups':(['tokens'],lambda z:z['tokens'],lambda *a:len(set(map(int,a)))),
  'integer':(['token'],lambda z:(z['token'],),lambda a:int(a)),
  'max':(['keys'],lambda z:z['keys'],lambda *a:max(map(int,a))),
  'difference':(['end','start'],lambda z:(z['end'],z['start']),lambda a,b:int(a)-int(b)),
 }
 op=next(iter(c)); _,get,expected=keys[op]; v=get(x)
 if op in ('match','difference'):return op,['a','b'],[tuple(v)],expected(*v)
 return op,['a'],[(t,) for t in v],expected(*v)
def f1(r,e,control):
 op,cols,rows,expected=f1_setup(r)
 plop={'match':lambda a,b:a==b,'value':lambda a,b:a,'groups':lambda a,b:a.n_unique(),'integer':lambda a,b:a,'max':lambda a,b:a.max(),'difference':lambda a,b:a-b}
 if e=='polars':
  typ=pl.Float64 if control else pl.Int64
  a=pl.col('a').cast(typ);b=pl.col('b').cast(typ)
  expr=plop[op](a,b)
  got=frame(cols,rows,[str]*len(cols)).select(expr.alias('actual')).item()
  operation=str(expr)
 else:
  typ='DOUBLE' if control else 'BIGINT'
  a,b=[f'CAST({k} AS {typ})' for k in ('a','b')]
  txt={'match':f'{a} = {b}','value':a,'groups':f'COUNT(DISTINCT {a})','integer':a,'max':f'MAX({a})','difference':f'{a} - {b}'}[op]
  operation=f'SELECT {txt} AS actual FROM t'
  got=_sql(e,{'t':(cols,rows,[str]*len(cols))},operation)[0][0]
 if type(expected) is bool:
  # SQLite reports native BOOLEAN result as 0/1 integer.
  valid=(type(got) in (bool,int) and got in (0,1) and bool(got)==expected)
 elif type(got) in (int,float) and (type(got) is int or math.isfinite(got)):valid=Fraction(got)==expected
 else:valid=False
 return operation,got,expected,valid
def f2(r,e,control):
 x,c,s=r['inputs'],r['candidate'],r['contract']
 nullsafe='NULL-safe' in s
 safe=nullsafe!=control
 outer='outer join' in s
 op='IS NOT DISTINCT FROM' if safe else '='
 if 'equal' in c:
  a,b=x['left'],x['right']
  expected=a==b if nullsafe or (a is not None and b is not None) else False
  if e=='polars':
   d=frame(['a','b'],[(a,b)],[str,str]); expr=pl.col('a').eq_missing(pl.col('b')) if safe else pl.col('a')==pl.col('b')
   operation=str(expr)+'.fill_null(False)'
   got=d.select(expr.fill_null(False)).item()
  else:
   operation=f'SELECT COALESCE(a {op} b, FALSE) FROM t'
   got=_sql(e,{'t':(['a','b'],[(a,b)],[str,str])},operation)[0][0]
  return operation,got,expected,type(got) in (int,bool) and got in (0,1) and bool(got)==expected
 L,R=x['left'],x['right']; n=len(L[0])-1
 names=[f'k{i}' for i in range(n)]
 types=[str]+[schema_types(L+R,i+1) for i in range(n)]
 expected=[]
 for l,*u in L:
  matches=[(l,rr) for rr,*v in R if (nullsafe or None not in u+v) and u==v]
  expected.extend(matches or ([(l,None)] if outer else []))
 if e=='polars':
  how='left' if outer else 'inner'
  A=frame(['lid']+names,L,types); B=frame(['rid']+names,R,types)
  operation=f'join(on={names!r}, how={how!r}, nulls_equal={safe}).select(lid,rid)'
  got=A.join(B,on=names,how=how,nulls_equal=safe).select(['lid','rid']).rows()
 else:
  on=' AND '.join(f'(l.{n} {op} r.{n})' for n in names)
  operation=f'SELECT l.lid, r.rid FROM l {"LEFT" if outer else "INNER"} JOIN r ON {on}'
  got=_sql(e,{'l':(['lid']+names,L,types),'r':(['rid']+names,R,types)},operation)
 return operation,got,expected,Counter(got)==Counter(expected)

def main():
 all_rows=json.loads((P/'../e7-scored/BLIND.json').read_text())
 selected=[r for r in all_rows if r['class'] in ('F1','F2')]
 assert Counter(r['class'] for r in selected)==Counter(F1=6,F2=6)
 rows=[]; sums=defaultdict(Counter)
 for e in ENG:
  for r in selected:
   for iscontrol in (False,True):
    arm='control' if iscontrol else 'exact'
    row=dict(engine=e,version=ENG[e],case_id=r['case_id'],cls=r['class'],arm=arm)
    try:
     s,actual,expected,valid=(f1 if r['class']=='F1' else f2)(r,e,iscontrol)
     row.update(operation=s,actual=actual,expected=expected,status='valid' if valid else 'invalid')
    except Exception as er:
     row.update(status='unsupported_or_error',reason=f'{type(er).__name__}: {er}')
    rows.append(row)
    sums['total|'+arm][row['status']]+=1
    sums[e+'|'+r['class']+'|'+arm][row['status']]+=1
 with (P/'MEASURED.csv').open('w',newline='') as fo:
  fields=['engine','version','case_id','cls','arm','operation','actual','expected','status','reason']
  W=csv.DictWriter(fo,fieldnames=fields); W.writeheader()
  for row in rows:
   rr=dict(row)
   for k in ('actual','expected'):
    if k in rr:rr[k]=json.dumps(rr[k],sort_keys=True)
   W.writerow(rr)
 print(json.dumps(dict(engine_versions=ENG,scope='12 heldout F1/F2 cases only',totals=sums,rows=rows),indent=2))
if __name__=='__main__':main()
