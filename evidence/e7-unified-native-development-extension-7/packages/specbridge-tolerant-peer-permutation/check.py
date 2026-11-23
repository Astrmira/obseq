import ast,csv,hashlib,itertools,json,math,sys
from pathlib import Path
import scipy
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching
D=Path(__file__).resolve().parent
def h(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
P=D/'PLAN.json';assert h(P)==(D/'PLAN.sha256').read_text().split()[0]
cfg=json.loads(P.read_text()); source, signed=sys.argv[1:3]
assert h(source)==cfg['sha256'] and h(signed)==cfg['e23_factor_sha256']
up=ast.parse(Path(source).read_text())
node,=(f for f in up.body if isinstance(f,ast.FunctionDef) and f.name=='grade')
assert not node.decorator_list and len(node.args.defaults)==2 and all(isinstance(x,ast.Constant) and x.value is None for x in node.args.defaults)
scope={}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),scope)
G=scope['grade']
def stock(ref,ans,cohort=True,pool=None):
 return G(dict(columns=len(ref[0]),tolerance=[None]*len(ref[0]),ordered=True,limit=len(ref)),
          ref,ans,tie_groups=[len(ref)] if cohort else [1]*len(ref),last_pool=pool)[0]
def qual(x,y):return math.isclose(x,y,rel_tol=1e-6,abs_tol=1e-9)
def oracle(ref,ans):
 m=[[int(qual(x,y)) for x in ref] for y in ans]
 n=len(ans)
 a=bool((maximum_bipartite_matching(csr_matrix(m),perm_type='column')>=0).sum()==n)
 b=any(all(m[j][k] for j,k in enumerate(per)) for per in itertools.permutations(range(len(ref)),n))
 assert a==b
 return a
def L(r):return [(v,) for v in r]
r=[1.0,1.0000014];a=[1.0000005,0.9999995]
assert oracle(r,a) and oracle(r,a[::-1])
assert (stock(L(r),L(a)),stock(L(r),L(a[::-1])))==(False,True)
assert (stock(L(r),L(a),pool=L(r+[2.0])),stock(L(r),L(a[::-1]),pool=L(r+[2.0])))==(False,True)
allrows=[]
N=[float(v) for v in cfg['fixed_relative_grid']]
for ref in itertools.combinations(N,2):
 # Use both output orders while the order of the reference pair stays pinned.
 for cand in itertools.combinations(N,2):
  expected=oracle(ref,cand)
  order=[stock(L(ref),L(cand)),stock(L(ref),L(cand[::-1]))]
  allrows.append(dict(ref=list(ref),answer=list(cand),membership=expected,stock_asc=order[0],stock_desc=order[1],order_changes=order[0]!=order[1]))
# True cutoff, with real SQLite/DataFusion/DuckDB/Polars outputs from the frozen experiment artifact.
measured=json.loads(Path(signed).read_text())
rows=[v for v in measured['observations'] if v['case']=='O3-top-k' and v['expected_legal']]
ranks=([[4,'b',90,'white'],[5,'b',90,'black']])
assert all(stock(v['gold_observation'],v['observation'],cohort=False,pool=ranks) for v in rows)
wide=2**53
n0=stock([(wide,'a')],[(wide+1,'a')]);n1=stock([(str(wide),'a')],[(str(wide+1),'a')])
assert (n0,n1)==(True,False)
if '--csv' in sys.argv:
 w=csv.DictWriter(sys.stdout,fieldnames=allrows[0].keys());w.writeheader();w.writerows(allrows)
else:
 print(json.dumps(dict(commit=cfg['commit'],stock_sha=h(source),scipy=scipy.__version__,e23_sql_legal_cutoff_accepted=len(rows),
  relative_fixture={'ref':r,'answer':a,'matching':True,'stock_original_order':False,'stock_permuted_order':True,'pair_edge_matrix':[[qual(x,y) for y in r] for x in a]},
  exhaustive=dict(groups=len(allrows),legal=sum(v['membership'] for v in allrows),all_candidate_orders=2*len(allrows),
   legal_orders_rejected=sum(v['membership'] and not v['stock_asc'] for v in allrows)+sum(v['membership'] and not v['stock_desc'] for v in allrows),
   illegal_orders_accepted=sum(not v['membership'] and (int(v['stock_asc'])+int(v['stock_desc'])) or 0 for v in allrows),
   groups_order_sensitive=sum(v['order_changes'] for v in allrows)),
  exact_identifier={'distinct_int_as_numeric_accepted':n0,'distinct_int_exact_text_accepted':n1}),indent=2))
