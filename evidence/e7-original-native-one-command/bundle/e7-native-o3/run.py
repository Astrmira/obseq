import sys,sqlite3,json,hashlib,csv,importlib.util
from collections import Counter,defaultdict
from pathlib import Path
P=Path(__file__).resolve().parent
for l in (P/'ADAPTER.lock').read_text().splitlines():
 h,n=l.split()
 assert hashlib.sha256((P/n).read_bytes()).hexdigest()==h,n
for d in ('../e1/input/more','../e1/input/duck143'):sys.path.insert(0,str((P/d).resolve()))
import duckdb, polars as pl, datafusion,pyarrow as pa
E={'sqlite':sqlite3.sqlite_version,'duckdb':duckdb.__version__,'polars':pl.__version__,'datafusion':datafusion.__version__}
spec=importlib.util.spec_from_file_location('locked_checker', P/'../e7-scored/check.py')
checker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

def sql(e,cols,rows,query):
    typ=[next((type(r[i]) for r in rows if r[i] is not None),str) for i in range(len(cols))]
    if e=='datafusion':
        ctx=datafusion.SessionContext()
        sch=pa.schema([(k,pa.int64() if t is int else pa.string()) for k,t in zip(cols,typ)])
        b=pa.RecordBatch.from_pylist([dict(zip(cols,r)) for r in rows],schema=sch)
        ctx.register_record_batches('q',[[b]])
        return [tuple(r.values()) for b in ctx.sql(query).collect() for r in b.to_pylist()]
    if e=='polars':
        q=pl.DataFrame(rows,schema=[(k,pl.Int64 if t is int else pl.String) for k,t in zip(cols,typ)],orient='row')
        with pl.SQLContext(q=q,eager=True) as ctx: return ctx.execute(query).rows()
    c=sqlite3.connect(':memory:') if e=='sqlite' else duckdb.connect()
    try:
        c.execute('CREATE TABLE q ('+','.join(k+(' BIGINT' if t is int else ' VARCHAR') for k,t in zip(cols,typ))+')')
        c.executemany('INSERT INTO q VALUES ('+','.join('?' for _ in cols)+')',rows)
        return c.execute(query).fetchall()
    finally:c.close()

def ids(R):return {'ids':[r[0] for r in R]}
def nums(R):
    d=dict(R)
    if len(d)!=len(R):raise ValueError('row number output repeated an ID')
    return {'numbers':d}
def groups(R):return {'groups':[list(r) for r in R]}
def twice(R,cols):
    assert len(R)==1
    return dict(zip(cols,R[0]))
def plan(r):
    x,s=r['inputs'],r['contract']
    sub=r['subtype']
    if sub=='top-k tie':
        R=x['rows']
        if 'per supplied division' in s:
            return ['id','g','v'],R, 'SELECT id FROM (SELECT id, ROW_NUMBER() OVER(PARTITION BY g ORDER BY v DESC,id ASC) AS rn FROM q) t WHERE rn=1','SELECT id FROM q ORDER BY v DESC,id ASC LIMIT 1',ids
        if 'WITH TIES' in s:
            return ['id','v'],R,'SELECT id FROM (SELECT id, RANK() OVER(ORDER BY v ASC) AS rk FROM q) t WHERE rk<=2','SELECT id FROM q ORDER BY v ASC,id ASC LIMIT 2',ids
        if 'NULLS LAST' in s:
            return ['id','v'],R,'SELECT id FROM q ORDER BY v ASC NULLS LAST,id ASC LIMIT 3','SELECT id FROM q ORDER BY v ASC NULLS FIRST,id ASC LIMIT 3',ids
        order='id ASC' if 'ascending ID' in s else 'id DESC'
        n=3 if 'exactly 3' in s else 2
        exact=f'SELECT id FROM q ORDER BY v DESC,{order} LIMIT {n}'
        mutant=(f'SELECT id FROM q ORDER BY v DESC,id DESC LIMIT {n}'
                if 'ascending ID' in s else f'SELECT id FROM q ORDER BY v ASC,id ASC LIMIT {n}')
        return ['id','v'],R,exact,mutant,ids
    if sub=='ROW_NUMBER tie':
        R=x['rows']; cols=['id','v'];part='';order='v ASC';badorder='v DESC';where='';source='q'
        if 'per partition' in s:
            cols=['id','g','v'];part='PARTITION BY g '
        if 'NULLS FIRST' in s:
            order='v ASC NULLS FIRST';badorder='v ASC NULLS LAST'
        if 'stable ID ASC' in s:
            order='v DESC';badorder='v DESC'
        if 'filtering' in s:
            cols.append('keep');R=[[*a,int(b)] for *a,b in R]
            where=' WHERE keep=1'
            source='(SELECT * FROM q WHERE keep=1) f'
        extra=',keep' if where else ''
        exact=f'SELECT id,rn FROM (SELECT id{extra}, ROW_NUMBER() OVER({part}ORDER BY {order},id ASC) AS rn FROM q) t{where}'
        if 'without gaps' in s:
            mutant='SELECT id,DENSE_RANK() OVER(ORDER BY v ASC) AS rn FROM q'
        else:
            mutant=f'SELECT id,rn FROM (SELECT id{extra}, ROW_NUMBER() OVER(ORDER BY {badorder},id DESC) AS rn FROM {source}) t{where}'
        return cols,R,exact,mutant,nums
    if sub=='coupled choices':
        if 'offers' in x:
            return ['v','id','days'],x['offers'],'SELECT id,days FROM q ORDER BY v ASC,id ASC LIMIT 1','SELECT MIN(id),MAX(days) FROM q WHERE v=(SELECT MIN(v) FROM q)',lambda R:twice(R,['vendor','days'])
        if 'teams' in x:
            R=[(t,n,b) for t,vs in x['teams'].items() for n,b in vs]
            return ['g','id','b'],R,'SELECT g,id,b FROM (SELECT g,id,b,ROW_NUMBER() OVER(PARTITION BY g ORDER BY id ASC) AS rn FROM q) t WHERE rn=1','SELECT g,MIN(id),MAX(b) FROM q GROUP BY g',lambda R:{g:[i,b] for g,i,b in R}
        if 'first' in r['candidate']:
            return ['id','v'],x['rows'],'SELECT FIRST_VALUE(id) OVER(ORDER BY v ASC,id ASC) AS fst,FIRST_VALUE(id) OVER(ORDER BY v DESC,id DESC) AS lst FROM q LIMIT 1','SELECT FIRST_VALUE(id) OVER(ORDER BY v ASC,id ASC) AS fst,FIRST_VALUE(id) OVER(ORDER BY v DESC,id ASC) AS lst FROM q LIMIT 1',lambda R:twice(R,['first','last'])
        if 'edges' in x:
            return ['src','dst','v'],x['edges'],'SELECT src,dst FROM q ORDER BY v DESC,src ASC,dst ASC LIMIT 1','SELECT MIN(src),MAX(dst) FROM q WHERE v=(SELECT MAX(v) FROM q)',lambda R:twice(R,['from','to'])
        if 'sum' in r['candidate']:
            return ['id','v','cost'],x['rows'],'SELECT id,SUM(cost) OVER() AS total FROM (SELECT id,cost FROM q ORDER BY v DESC,id ASC LIMIT 2) t','SELECT id,SUM(cost) OVER() AS total FROM q ORDER BY v DESC,id ASC LIMIT 2',lambda R:{'ids':[v[0] for v in R],'sum':R[0][1]}
        return ['v'],[(v,) for v in x['peers']],'SELECT v,LOWER(v) FROM q ORDER BY v ASC LIMIT 1','SELECT LOWER(v),LOWER(v) FROM q ORDER BY v ASC LIMIT 1',lambda R:twice(R,['raw','normalized'])
    if sub=='GROUP BY representative':
        if 'department' in s:
            return ['g','v'],x['rows'],'SELECT g,MIN(v),COUNT(*) FROM q GROUP BY g,LOWER(v)','SELECT g,LOWER(v),COUNT(*) FROM q GROUP BY g,LOWER(v)',groups
        if 'earliest inserted' in s:
            return ['ord','v'],list(enumerate(x['inOrder'])),'SELECT v,n FROM (SELECT v,COUNT(*) OVER(PARTITION BY LOWER(v)) AS n,ROW_NUMBER() OVER(PARTITION BY LOWER(v) ORDER BY ord ASC) AS rn FROM q) t WHERE rn=1','SELECT MIN(v),COUNT(*) FROM q GROUP BY LOWER(v)',groups
        R=[(v,) for v in x['values']]
        if 'trailing ASCII' in s: group='RTRIM(v)';bad='RTRIM(v)'
        elif 'absolute integer' in s:group='ABS(v)';bad='ABS(v)'
        elif 'case-insensitively' in s:group='LOWER(v)';bad='LOWER(v)'
        else:group='v';bad="COALESCE(v,'NULL')"
        return ['v'],R,f'SELECT MIN(v),COUNT(*) FROM q GROUP BY {group}',f'SELECT {bad},COUNT(*) FROM q GROUP BY {bad}',groups
    raise NotImplementedError(sub)

R=[r for r in json.loads((P/'../e7-scored/BLIND.json').read_text()) if r['class']=='O3']
assert sorted(Counter(r['subtype'] for r in R).values())==[6]*4
out=[];totals=defaultdict(Counter)
for e,version in E.items():
 for r in R:
  cols,rows,ex,ct,project=plan(r)
  for arm,q in [('exact',ex),('control',ct)]:
   rec=dict(engine=e,version=version,case_id=r['case_id'],subtype=r['subtype'],arm=arm,query=q)
   try: raw=sql(e,cols,rows,q)
   except Exception as err:rec.update(status='unsupported_or_error',error=f'{type(err).__name__}: {err}')
   else:
    rec['native_rows']=raw
    try:
     result=project(raw)
     rec['candidate']=result
     rec['status']='valid' if checker.legal(dict(r,candidate=result)) else 'invalid'
    except (ValueError,AssertionError,IndexError,NotImplementedError,TypeError,KeyError) as err:rec.update(status='unadjudicated_or_malformed',error=f'{type(err).__name__}: {err}')
   out.append(rec)
   for k in (arm,e+'|'+arm,r['subtype']+'|'+arm):totals[k][rec['status']]+=1
cols=['engine','version','case_id','subtype','arm','query','native_rows','candidate','status','error']
with (P/'MEASURED.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
 for r in out:w.writerow({k:json.dumps(v) if k in ('native_rows','candidate') else v for k,v in r.items()})
print(json.dumps(dict(engine_versions=E,totals=totals,rows=out),indent=2))
