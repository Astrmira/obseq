from pathlib import Path
import sqlite3,sys,tempfile,hashlib,json,re,csv,importlib.util
from collections import defaultdict,Counter
P=Path(__file__).resolve().parent
for line in (P/'ADAPTER.lock').read_text().splitlines():
 h,f=line.split();assert hashlib.sha256((P/f).read_bytes()).hexdigest()==h
sys.path.insert(0,str((P/'../e1/input/duck143').resolve()))
import duckdb
E={'sqlite':sqlite3.sqlite_version,'duckdb':duckdb.__version__}
spec=importlib.util.spec_from_file_location('locked_checker',P/'../e7-scored/check.py')
oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
def connect(e,f):
 if e=='sqlite':return sqlite3.connect(f,isolation_level=None)
 return duckdb.connect(str(f))

def scan(c,q,p=()):return c.execute(q,p).fetchall()
def f3(c,e,path,r,control):
 x=r['inputs']; s=r['contract']; log=[]
 def execute(q,p=()):
  log.append(dict(sql=q,args=p));return scan(c,q,p)
 def put(q,rows):
  for row in rows:execute(q,row)
 if 'history' in x:
  execute('CREATE TABLE q(commit_id BIGINT, payload VARCHAR)')
  put('INSERT INTO q VALUES (?,?)',x['history'])
  got=execute('SELECT payload FROM q WHERE commit_id<=?'+(' AND payload IS NOT NULL' if control else '')+' ORDER BY commit_id DESC LIMIT 1',(x['s'],))
  return {'present':bool(got and got[0][0] is not None)},log
 if 'revisions' in x:
  execute('CREATE TABLE q(commit_id BIGINT, balance BIGINT)')
  put('INSERT INTO q VALUES (?,?)',x['revisions'])
  got=execute('SELECT balance FROM q'+('' if control else ' WHERE commit_id<=?')+' ORDER BY commit_id DESC LIMIT 1',() if control else (x['s'],))
  return {'balance':got[0][0]},log
 if 'events' in x:
  execute('CREATE TABLE q(commit_id BIGINT, id VARCHAR, op VARCHAR)')
  put('INSERT INTO q VALUES (?,?,?)',x['events'])
  q="SELECT COUNT(*) FROM (SELECT op, ROW_NUMBER() OVER (PARTITION BY id ORDER BY commit_id DESC) AS rn FROM q WHERE commit_id"+('<' if control else '<=')+"?) t WHERE rn=1 AND op='insert'"
  return {'active':execute(q,(int(re.search(r'commit (\d+)',s)[1]),))[0][0]},log
 if 'versions' in x:
  execute('CREATE TABLE q(commit_id BIGINT, debit BIGINT, credit BIGINT)')
  put('INSERT INTO q VALUES (?,?,?)',[(k,v['debit'],v['credit']) for k,v in x['versions']])
  q='SELECT debit,credit FROM q WHERE commit_id<=? ORDER BY commit_id DESC LIMIT 1'
  d,cr=execute(q,(x['s'],))[0]
  if control:cr=execute('SELECT credit FROM q ORDER BY commit_id DESC LIMIT 1')[0][0]
  return {'debit':d,'credit':cr},log
 if 'writes' in x:
  q='SELECT val FROM q WHERE commit_id<=? ORDER BY '+('event_date DESC, commit_id DESC' if control else 'commit_id DESC')+' LIMIT 1'
  # SQLite DATE cast stores year only; ISO date order instead uses lossless text in both engines.
  execute('CREATE TABLE q(commit_id BIGINT, event_date VARCHAR, val VARCHAR)')
  put('INSERT INTO q VALUES (?,?,?)',[(w['commit'],w['event'],w['v']) for w in x['writes']])
  return {'value':execute(q,(x['s'],))[0][0]},log
 if 'commits' in x:
  execute('CREATE TABLE q(commit_id BIGINT, val VARCHAR)')
  commits=sorted(x['commits']);times=x['readTimes'];start=x['start']
  p=0
  def write_until(t,writer):
   nonlocal p
   batch=[]
   while p<len(commits) and commits[p][0]<=t:
    batch.append(commits[p]);p+=1
   if not batch:return
   scan(writer,'BEGIN')
   try:
    for k,v in batch:
     scan(writer,'INSERT INTO q VALUES (?,?)',(k,v))
     log.append(dict(connection='writer',sql='INSERT INTO q VALUES (?,?)',args=(k,v)))
    scan(writer,'COMMIT');log.append(dict(connection='writer',sql='COMMIT'))
   except Exception:
    scan(writer,'ROLLBACK');raise
  writer=connect(e,path)
  try:
   write_until(start,writer)
   if not control:execute('BEGIN')
   # Pin the reader snapshot at transaction start by a real read.
   if not control:execute('SELECT COUNT(*) FROM q')
   got=[]
   for t in times:
    write_until(t,writer)
    got.append(execute('SELECT val FROM q ORDER BY commit_id DESC LIMIT 1')[0][0])
   if not control:execute('COMMIT')
  finally:writer.close()
  return {'values':got},log
 raise NotImplementedError('snapshot schema')

def f4(c,r,control):
 x,s=r['inputs'],r['contract'];log=[]
 def execute(q,p=()):
  log.append(dict(sql=q,args=p));return scan(c,q,p)
 if 'changes' in x:
  execute('CREATE TABLE q(units BIGINT, price BIGINT)')
  g=x['prior'];execute('INSERT INTO q VALUES (?,?)',(g['units'],g['price']))
  q='SELECT units*price FROM q'; patch=[('UPDATE q SET units=?',(x['changes']['units'],))]; project=lambda R:{'subtotal':R[0][0]}
 elif 'delete' in x:
  execute('CREATE TABLE q(id VARCHAR, v BIGINT)')
  for t in x['prior']:execute('INSERT INTO q VALUES (?,?)',t)
  patch=[('DELETE FROM q WHERE id=?',(x['delete'],))]
  # Contract oracle consumes JSON numeric and this fixture's native arithmetic is exact (33/2).
  q='SELECT AVG(v) FROM q'; project=lambda R:{'mean':R[0][0]}
 elif 'rename' in x:
  execute('CREATE TABLE q(id VARCHAR, v VARCHAR)')
  for t in x['prior']:execute('INSERT INTO q VALUES (?,?)',t)
  key=x['lookup'];assert re.fullmatch('[a-z]+',key)
  q=f"SELECT id FROM q WHERE LOWER(v)='{key}'"
  i,v=x['rename']; patch=[('UPDATE q SET v=? WHERE id=?',(v,i))]; project=lambda R:{'ids':[i[0] for i in R]}
 elif 'patch' in x:
  execute('CREATE TABLE q(qty BIGINT, price BIGINT, ship BIGINT)')
  g=x['before'];execute('INSERT INTO q VALUES (?,?,?)',(g['quantity'],g['unitPrice'],g['shipping']))
  q='SELECT qty*price+ship FROM q'; patch=[('UPDATE q SET price=?',(x['patch']['unitPrice'],))]; project=lambda R:{'grandTotal':R[0][0]}
 elif 'move' in x:
  execute('CREATE TABLE q(id VARCHAR, bucket VARCHAR, v BIGINT)')
  for t in x['before']:execute('INSERT INTO q VALUES (?,?,?)',t)
  q='SELECT bucket,MAX(v) FROM q GROUP BY bucket'
  i,b=x['move'];patch=[('UPDATE q SET bucket=? WHERE id=?',(b,i))];project=dict
 else:
  execute('CREATE TABLE q(lo BIGINT, hi BIGINT)')
  execute('INSERT INTO q VALUES (?,?)',(x['old']['lo'],x['old']['hi']))
  q='SELECT hi-lo FROM q';patch=[('UPDATE q SET lo=?,hi=?',(x['new']['lo'],x['new']['hi']))];project=lambda R:{'width':R[0][0]}
 execute('CREATE TABLE cache AS '+q)
 execute('BEGIN')
 for stmt,p in patch:execute(stmt,p)
 execute('COMMIT')
 return project(execute('SELECT * FROM cache' if control else q)),log
R=[r for r in json.loads((P/'../e7-scored/BLIND.json').read_text()) if r['class'] in ('F3','F4')]
assert Counter(r['class'] for r in R)==Counter(F3=6,F4=6)
allrows=[]; totals=defaultdict(Counter)
for e,v in E.items():
 for r in R:
  for arm in ('exact','control'):
   out=dict(engine=e,version=v,case_id=r['case_id'],class_=r['class'],arm=arm)
   with tempfile.TemporaryDirectory(prefix='e7-f34-') as d:
    path=Path(d)/'db'
    c=connect(e,path)
    try:
     if e=='sqlite':assert scan(c,'PRAGMA journal_mode=WAL')[0][0]=='wal'
     z,log=f3(c,e,path,r,arm=='control') if r['class']=='F3' else f4(c,r,arm=='control')
     # Reopen database, ensuring calls were against persisted state rather than Python payloads.
     c.close();c=None
     reopen=connect(e,path)
     try:
      persisted_rows=scan(reopen,'SELECT COUNT(*) FROM q')[0][0]
     finally:reopen.close()
     out.update(candidate=z,sql_trace=log,reopen_source_row_count=persisted_rows,
                status='valid' if oracle.legal(dict(r,candidate=z)) else 'invalid')
    except Exception as exc:out.update(status='unsupported_or_error',error=f'{type(exc).__name__}: {exc}')
    finally:
     if c is not None:c.close()
   allrows.append(out)
   for k in (arm,arm+'|'+e,arm+'|'+r['class']):totals[k][out['status']]+=1
with (P/'MEASURED.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=('engine','version','case_id','class_','arm','status','candidate','sql_trace','reopen_source_row_count','error'))
 writer.writeheader()
 for r in allrows:writer.writerow({k:json.dumps(v) if k in ('candidate','sql_trace') else v for k,v in r.items()})
print(json.dumps(dict(engine_versions=E,totals=totals,rows=allrows),indent=2))
