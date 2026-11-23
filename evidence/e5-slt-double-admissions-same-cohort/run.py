import hashlib,contextlib,io,csv,json,sys,re,tempfile, pathlib
from collections import Counter,defaultdict
from pathlib import Path
P=Path(__file__).resolve().parent
U,site=map(Path,sys.argv[1:])
for file,root in [('NATIVE-INPUT.lock',U)]:
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

O=json.loads((P/'ORIGINAL.json').read_text())['observations'];assert len(O)==90
modes=('nosort','rowsort','valuesort')
out=[]; ctl=[]
def run(G,C,T,md):
 qg,qc=sql(G,T),sql(C,T)
 keys=mode_rows(G,T,md,stock_expected)
 a,detail,_=native(testtext(qc,T,md,'\n'.join(keys)))
 assert a in ('accept','reject'),(a,detail)
 if md=='rowsort':
  assert len(keys)>1
  h=digest(qg,T,md)
  b,detail,_=native(testtext(qc,T,md,h,'hash-threshold 1\n\n'))
  assert b in ('accept','reject'),(b,detail)
  assert (h==digest(qc,T,md))==(b=='accept')
 else:b=None
 return dict(literal=a,threshold1_explicit_native_hash=b)
with duckdb.connect(':memory:',config={'enable_external_access':False,'threads':1}) as d:
 for i,r in enumerate(O):
  G,C=r['gold_observation'],r['observation']
  types=[set(type(x) for x in xs if x is not None) for xs in zip(*(G+C))]
  if any(len(t)>1 for t in types):
   out.append(dict(id=i,case=r['case'],status='NA',reason='no joint fixed type without changing SQL typed tuples'))
   continue
  if not any(t=={float} for t in types):
   out.append(dict(id=i,case=r['case'],status='prior_published_I_T',reason='previous native package, not fresh runs'))
   continue
  assert all(t=={float} for t in types)
  T='R'*len(types)
  for rows in (G,C):
   rot=d.execute(sql(rows,T)).fetchall()
   assert rot==list(map(tuple,rows)) and all(type(x) is float for row in rot for x in row)
  ds={md:run(G,C,T,md) for md in modes}
  out.append(dict(id=i,case=r['case'],status='new_native_R',legal=r['expected_legal'],results=ds))
  # Positive and changed-value controls fixture legal for checks only.
  altered=[row[:] for row in G];altered[0][0]+=1.0
  ct=dict(unchanged=run(G,G,T,'rowsort'),changed=run(G,altered,T,'rowsort'))
  assert ct==dict(unchanged=dict(literal='accept',threshold1_explicit_native_hash='accept'),changed=dict(literal='reject',threshold1_explicit_native_hash='reject')),ct
  ctl.append(dict(id=i,**ct))
assert Counter(r['status'] for r in out)=={'prior_published_I_T':79,'NA':9,'new_native_R':2}
print(json.dumps(dict(port='66b0687fd7b21d22eb8c2216c5e26030dc6a3286',duckdb=duckdb.__version__,rows=out,controls=ctl),indent=2,sort_keys=True))
