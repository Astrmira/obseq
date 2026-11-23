import hashlib,contextlib,io,csv,json,sys,re,tempfile, pathlib
from collections import Counter,defaultdict
from pathlib import Path
P=Path(__file__).resolve().parent
U,site=map(Path,sys.argv[1:])
for file,root in [('ADAPTER.lock',P),('NATIVE-INPUT.lock',U)]:
 for row in (P/file).read_text().splitlines():
  code,name=row.split()
  assert hashlib.sha256((root/name).read_bytes()).hexdigest()==code,name
sys.path[:0]=[str(x.resolve()) for x in (site,U/'upstream',U/'.slt-deps')]
from duckdb_sqllogictest import SQLLogicParser
from duckdb_sqllogictest.result import ExecuteResult, SQLLogicContext, SQLLogicDatabase, SQLLogicRunner, TestException
import duckdb,_duckdb,importlib.metadata as M
assert hashlib.sha256(Path(_duckdb.__file__).read_bytes()).hexdigest()==(U/'DUCKDB-SO.sha256').read_text().strip()
assert M.version('termcolor')=='3.1.0' and duckdb.__version__=='1.4.3'
for row in (U/'UPSTREAM-FILES.sha256').read_text().splitlines():
 code,name=row.split();assert hashlib.sha256((U/name).read_bytes()).hexdigest()==code
class HostRunner(SQLLogicRunner):
 def get_test_directory(self):return self.default_test_dir

def native(blob,save=None):
 if save is not None:save.write_text(blob)
 with tempfile.TemporaryDirectory(prefix='e5-slt-') as td:
  path=pathlib.Path(td)/'fixture.test';path.write_text(blob)
  out=io.StringIO()
  with contextlib.redirect_stdout(out),contextlib.redirect_stderr(out):
   try:
    test=SQLLogicParser().parse(str(path))
    runner=HostRunner(default_test_dir=td);runner.test=test
    runner.original_sqlite_test=test.is_sqlite_test()
    db=SQLLogicDatabase(':memory:',None,additional_config={'allow_unsigned_extensions':False,'threads':1})
    runner.database=db
    pool=db.connect()
    def once(_):yield None
    ctx=SQLLogicContext(pool,runner,test.statements,{'__TEST_DIR__':td,'__WORKING_DIRECTORY__':td},once)
    pool.initialize_connection(ctx,pool.get_connection())
    ctx.is_loop=False
    ctx.verify_statements()
    ret=ctx.execute()
    status='accept' if ret.type==ExecuteResult.Type.SUCCESS else 'error'
    detail=str(ret.type)
   except TestException as e:
    content=out.getvalue()
    mismatch=any(t in content for t in ['Wrong result in query','Wrong row count in query','Wrong column count in query','Wrong result hash when comparing'])
    status='reject' if mismatch else 'error'
    detail=(str(e)+'\n'+content).replace(td,'<scratch>').strip()
   except Exception as e:
    status='error';detail=(type(e).__name__+': '+str(e)+'\n'+out.getvalue()).replace(td,'<scratch>').strip()
  return status,detail,out.getvalue().replace(td,'<scratch>')

def canonical_cell(v,t):
 if v is None:return 'NULL'
 if t=='I':
  assert isinstance(v,int)
  return str(v)
 if t=='R':return f'{v:.3f}'
 assert type(v) is str and all(ord(c)<128 for c in v)
 return ''.join(c if 32<=ord(c)<=126 else '@' for c in v) if v else '(empty)'

def stock_expected(v,t):
 if v is None:return 'NULL'
 if t=='T':return v or '(empty)'
 return str(v)

def mode_rows(R,T,md,c_fn):
 G=[tuple(c_fn(v,t) for v,t in zip(row,T)) for row in R]
 if md=='valuesort':return sorted(x for r in G for x in r)
 if md=='rowsort':G.sort()
 return [x for r in G for x in r]

def sql(R,T):
 def item(v,t):
  typ={'I':'BIGINT','T':'VARCHAR','R':'DOUBLE'}[t]
  if v is None:s='NULL'
  elif t=='T':
   assert all(ord(x)<128 for x in v)
   s=repr(v) if '\t' not in v and '\n' not in v else '||'.join(f'CHR({ord(x)})' for x in v)
  else:s=str(v)
  return f'CAST({s} AS {typ})'
 cols=[f'c{i}' for i in range(len(T))]
 values=', '.join('('+', '.join([str(i),*(item(v,t) for v,t in zip(row,T))])+')' for i,row in enumerate(R))
 return f'SELECT {", ".join(cols)} FROM (VALUES {values}) AS fixture(ordinal,{", ".join(cols)}) ORDER BY ordinal'

def testtext(q,T,mode,expected,head=''):
 return head+f'query {T} {mode}\n{q}\n----\n{expected}\n\n'

def digest(q,T,mode):
 b=testtext(q,T,mode,'ignored in output_hash mode','mode output_hash\n\n')
 status,detail,out=native(b)
 found=re.findall(r'^\d+ values hashing to [a-f0-9]{32}$',out,re.M)
 assert status=='accept' and len(found)==1,(status,detail,out)
 return found[0]

rows=[];summary=defaultdict(Counter)
with duckdb.connect(':memory:',config={'enable_external_access':False,'threads':1}) as db:
 for t in json.loads((P/'FIXTURES.json').read_text()):
  case=t['case'];G,C,T=t['gold'],t['candidate'],t['types']
  assert (G==C)==t['legal']
  qg,qc=sql(G,T),sql(C,T)
  for q,R in ((qg,G),(qc,C)):
   val=db.execute(q).fetchall()
   sig=lambda Z:[[(type(v).__name__,v) for v in row] for row in Z]
   assert sig(val)==sig(R)
  for mode in ('nosort','rowsort','valuesort'):
   canonical_l=mode_rows(G,T,mode,canonical_cell)
   canonical_r=mode_rows(C,T,mode,canonical_cell)
   Gd,Cd=digest(qg,T,mode),digest(qc,T,mode)
   status,detail,_=native(testtext(qc,T,mode,Gd))
   assert status in ('accept','reject')
   assert (Gd==Cd)==(status=='accept')
   wants=mode_rows(G,T,mode,stock_expected)
   if any(c in v for v in wants for c in '\n\t\r'):
    plain='NA';pd='embedded delimiter not admitted in plaintext gold'
   else:plain,pd,_=native(testtext(qc,T,mode,'\n'.join(wants)))
   for cmp_,s in [('documented_ascii_model','accept' if canonical_l==canonical_r else 'reject'),
                  ('duckdb_python_slt_plain',plain),('duckdb_python_slt_explicit_hash',status)]:
    summary[cmp_][s]+=1
    if s in ('accept','reject'):
     if ((s=='accept')!=t['legal']):summary[cmp_]['false_accept' if s=='accept' else 'false_reject']+=1
   rows.append(dict(case=case,mode=mode,expected_typed_legal=t['legal'],query_gold=qg,query_candidate=qc,
       documented_ascii_gold=canonical_l,documented_ascii_candidate=canonical_r,
       documented_ascii_equal=canonical_l==canonical_r,
       native_stock_plain=plain,native_plain_detail=pd,native_stock_hash=status,native_hash_detail=detail,
       gold_native_hash=Gd,candidate_native_hash=Cd))
by=lambda c:[r for r in rows if r['case']==c]
for case in ('null-sentinel','empty-sentinel'):
 assert all(r['documented_ascii_equal'] and r['native_stock_plain']=='accept' and r['native_stock_hash']=='accept' for r in by(case))
pre=next(r for r in rows if r['case']=='native-newline-shift')
p1=b'a\nb\nc\n'
assert all(not r['documented_ascii_equal'] and r['native_stock_plain']=='NA' and r['native_stock_hash']=='accept' for r in by('native-newline-shift'))
assert all(r['gold_native_hash']==f'2 values hashing to {hashlib.md5(p1).hexdigest()}' for r in by('native-newline-shift'))
assert all(r['native_stock_plain']=='accept' and r['native_stock_hash']=='reject' for r in by('native-real-tolerance'))
with (P/'SCORES.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]))
 w.writeheader()
 for x in rows:w.writerow({k:json.dumps(v) if isinstance(v,list) else v for k,v in x.items()})
print(json.dumps(dict(summary=summary,rows=rows),indent=2))
