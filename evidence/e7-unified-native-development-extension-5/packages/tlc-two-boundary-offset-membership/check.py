from collections import Counter, defaultdict
from datetime import datetime,timedelta
from itertools import combinations,product
from pathlib import Path
import hashlib,json,sys,random
import duckdb
import pyarrow as pa,pyarrow.parquet as pq

def gate(A,B,M,N,l,r):
    # A and B are projected source pools for the first/last partially held bands.
    if M-N or N.total()!=M.total()+l+r: return False
    X=N-M
    if X-(A+B): return False
    return sum(max(0,n-B[k]) for k,n in X.items())<=l<=sum(min(n,A[k]) for k,n in X.items())

def tiny():
    rng=random.Random(243)
    tested=0
    for _ in range(85):
        a=[rng.randrange(4) for _ in range(rng.randint(1,6))]
        b=[rng.randrange(4) for _ in range(rng.randint(1,6))]
        m=[rng.randrange(4) for _ in range(rng.randint(0,3))]
        l=rng.randrange(len(a)+1); r=rng.randrange(len(b)+1)
        admiss={(tuple(sorted(m+list(u)+list(v)))) for u in combinations(a,l) for v in combinations(b,r)}
        for x in product(*(range(Counter(a+b+m)[j]+1) for j in range(4))):
            if sum(x)!=len(m)+l+r: continue
            cand=tuple(j for j,n in enumerate(x) for _ in range(n))
            assert gate(Counter(a),Counter(b),Counter(m),Counter(cand),l,r)==(cand in admiss)
            tested+=1
    return tested

def run(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    db=duckdb.connect(config={'threads':1,'memory_limit':'128MB'})
    db.read_parquet(str(p),file_row_number=True).create_view('source')
    assert db.execute("select count(*) from source").fetchone()==(4181444,)
    cells=[]
    for day,hour in product((3,10,17,24),(17,18)):
        start=datetime(2025,11,day,hour); end=start+timedelta(hours=1)
        cols=['tpep_pickup_datetime','DOLocationID']
        exact=defaultdict(list)
        ar=pq.read_table(p,columns=cols,filters=[(cols[0],'>=',start),(cols[0],'<',end)])
        for t,y in zip(*(ar[k].to_pylist() for k in cols)):
            exact[t.replace(second=0,microsecond=0)].append(y)
        buckets=sorted(exact)
        assert len(buckets)>=6
        for left,right in ((2,3),(2,5)):
            a,b=exact[buckets[left]],exact[buckets[right]]
            assert min(len(a),len(b))>=4
            gone=(2*len(a))//3
            l=len(a)-gone; r=len(b)//3
            offset=sum(len(exact[t]) for t in buckets[:left])+gone
            mid=[x for t in buckets[left+1:right] for x in exact[t]]
            length=l+len(mid)+r
            base="SELECT DOLocationID FROM source WHERE tpep_pickup_datetime>=? AND tpep_pickup_datetime<? ORDER BY date_trunc('minute',tpep_pickup_datetime)"
            results=[]
            for suffix in ('',', file_row_number ASC',', file_row_number DESC'):
                results.append(Counter(x[0] for x in db.execute(base+suffix+f" LIMIT {length} OFFSET {offset}",[start,end]).fetchall()))
            A,B,M=map(Counter,(a,b,mid))
            assert all(gate(A,B,M,x,l,r) for x in results)
            assert all(x.total()==length for x in results)
            faults=[]
            # Take one extra occurrence from either physical boundary, never violate union capacities.
            for lp,rp in ((l+1,r-1),(l-1,r+1)):
                assert 0<=lp<=len(a) and 0<=rp<=len(b)
                for aa,bb in product((a,a[::-1]),(b,b[::-1])):
                    C=Counter(aa[:lp]+bb[:rp]+mid)
                    assert C.total()==length and not M-C and not (C-M)-(A+B)
                    faults.append(not gate(A,B,M,C,l,r))
            cells.append(dict(day=day,hour=hour,band_indices=[left,right],scope_rows=ar.num_rows,
                projected_value_overlap=len(A.keys()&B.keys()),offset=offset,limit=length,
                left_peers=len(a),right_peers=len(b),left_take=l,right_take=r,mandatory_middle=len(mid),
                stock_legal=True,opposite_id_refinement_changes_projection=results[1]!=results[2],
                wrong_physical_quota_controls=len(faults),observable_wrong_quota_detected=sum(faults)))
    return dict(source_sha256=h.hexdigest(),duckdb=duckdb.__version__,pyarrow=pa.__version__,cells=cells,
        tiny_literal_candidates=tiny(),admitted_native=sum(3 for _ in cells),
        cells_with_distinct_legal_projected_bags=sum(x['opposite_id_refinement_changes_projection'] for x in cells),
        controlled_quota_deviations=sum(x['wrong_physical_quota_controls'] for x in cells),
        observable_wrong_quota_detected=sum(x['observable_wrong_quota_detected'] for x in cells))

if __name__=='__main__':
    print(json.dumps(run(Path(sys.argv[1])),sort_keys=True,indent=2))
