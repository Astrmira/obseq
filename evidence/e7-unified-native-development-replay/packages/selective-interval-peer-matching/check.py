from bisect import bisect_left,bisect_right
from collections import defaultdict
from fractions import Fraction as F
import hashlib,itertools,json,random,sys
from pathlib import Path
import scipy
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching
D=Path(__file__).resolve().parent
S=(D/'PLAN.json').read_bytes()
assert hashlib.sha256(S).hexdigest()==(D/'PLAN.sha256').read_text().split()[0]
P=json.loads(S)

def bounds(x,t):
    a,r=t; assert a>=0 and 0<=r<1
    one=1-r
    if x>=0:
        l,h=x*one,x/one
    else:
        l,h=x/one,x*one
    return min(x-a,l),max(x+a,h)

def direct(x,y,t):
    a,r=t
    return abs(x-y)<=max(a,r*max(abs(x),abs(y)))

def scalar(ref,cand,t):
    p=0;R=sorted(ref)
    for x in sorted(cand):
        l,u=bounds(x,t)
        while p<len(R) and R[p]<l:p+=1
        if p==len(R) or R[p]>u:return False
        p+=1
    return True

def mx(n,m,edges):
    # Coords directed from each candidate row to possible source representatives.
    if n==0:return True
    ii,jj=zip(*edges) if edges else ([],[])
    g=coo_matrix(([1]*len(ii),(ii,jj)),shape=(n,m)).tocsr()
    a=maximum_bipartite_matching(g,perm_type='column')
    assert len(a)==n
    return all(j>=0 for j in a)

def dense(ref,cand,T):
    e=[(i,j) for i,(ka,a) in enumerate(cand) for j,(kb,b) in enumerate(ref)
       if ka==kb and all(direct(x,y,t) for x,y,t in zip(a,b,T))]
    return mx(len(cand),len(ref),e)

def compressed(ref,cand,T):
    # Choose most selective coordinate independently for each desired row.
    # Index nodes retain source slot identity, so repeated tuples stay distinct.
    d=len(T);assert d>0
    groups=defaultdict(list)
    for j,(k,r) in enumerate(ref):groups[k].append((r,j))
    columns={}
    for k,G in groups.items():
        A=[sorted((b[h],j) for b,j in G) for h in range(d)]
        columns[k]=[([v for v,j in a],[j for v,j in a]) for a in A]
    considered=0;globals_=[0]*d;E=[]
    for i,(k,a) in enumerate(cand):
        if k not in columns:continue
        ranges=[bounds(x,t) for x,t in zip(a,T)]
        counts=[]
        for h,((v,ix),(lower,upper)) in enumerate(zip(columns[k],ranges)):
            l,r=bisect_left(v,lower),bisect_right(v,upper)
            counts.append((r-l,h,l,r));globals_[h]+=r-l
        n,h,l,r=min(counts);considered+=n
        for j in columns[k][h][1][l:r]:
            _,b=ref[j]
            if all(lo<=y<=hi for y,(lo,hi) in zip(b,ranges)):
                E.append((i,j))
    return mx(len(cand),len(ref),E),dict(full_cross=len(cand)*len(ref),best_fixed_axis=min(globals_),row_adaptive=considered,real_graph_edges=len(E))

R=random.Random(P['generators']['seed'])
small=0;sc=0;perm=0;count_checks=0
for _ in range(P['generators']['small_trials']):
    d=R.randrange(1,5);n=R.randrange(1,9);m=R.randrange(0,9)
    T=[(F(R.randrange(4),3),F(R.randrange(4),8)) for i in range(d)]
    make=lambda n:[(str(R.randrange(1 if _%2 else 3)),tuple(F(R.randrange(-12,13),R.choice([1,2,3])) for h in range(d))) for i in range(n)]
    A=make(n);B=make(m)
    a=compressed(A,B,T)[0]
    assert a==dense(A,B,T)
    if _%11==0 and m<=min(4,n):
        p=any(all(B[i][0]==A[j][0] and all(direct(x,y,t) for x,y,t in zip(B[i][1],A[j][1],T)) for i,j in enumerate(I)) for I in itertools.permutations(range(n),m))
        assert p==a;perm+=1
    for h,t in enumerate(T):
        a0=[b[h] for k,b in A];b0=[b[h] for k,b in B]
        sorted_b=sorted(b0)
        intervals=[bounds(c,t) for c in sorted_b]
        assert intervals==sorted(intervals) and [v for l,v in intervals]==sorted(v for l,v in intervals)
        assert scalar(a0,b0,t)==mx(m,n,[(i,j) for i,x in enumerate(b0) for j,y in enumerate(a0) if direct(x,y,t)])
        for x,y in itertools.product(b0,a0):
            l,u=bounds(x,t); assert direct(x,y,t)==(l<=y<=u);count_checks+=1
        sc+=1
    small+=1
unit=(F(0),F(0))
r=[('k',(F(0),F(0))),('k',(F(2),F(2)))]
a=[('k',(F(0),F(2))),('k',(F(2),F(0)))]
assert all(scalar([x[1][h] for x in r],[x[1][h] for x in a],unit) for h in range(2))
assert not compressed(r,a,[unit,unit])[0]
h=P['generators']['scale_per_axis']
r=[('k',(F(i+1),F(0))) for i in range(h)]+[('k',(F(0),F(i+1))) for i in range(h)]
a=[('k',(x+F(1,64),y-F(1,64))) for k,(x,y) in reversed(r)]
t=[(F(1,32),F(0))]*2
got,K=compressed(r,a,t)
assert got and K==dict(full_cross=(2*h)**2,best_fixed_axis=h*h+h,row_adaptive=2*h,real_graph_edges=2*h)
print(json.dumps(dict(scipy=scipy.__version__,authored_dense_sparse_controls=small,scalar_controls=sc,literal_controls=perm,interval_predicate_checks=count_checks,
 separate_columns_accept_jointly_invalid=True,scale=dict(rows=len(r),**K,full_matching=got)),indent=2))
