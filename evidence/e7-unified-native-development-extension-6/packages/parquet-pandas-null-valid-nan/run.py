"""Native controlled validity/NaN split on a pinned TLC Parquet field."""
from pathlib import Path
import hashlib,io,json,math,tempfile,sys
import duckdb,pandas as pd,polars as pl,pyarrow as pa,pyarrow.compute as pc,pyarrow.parquet as pq
from pandas.testing import assert_frame_equal as pdeq
from polars.testing import assert_frame_equal as pleq
src,scratch=map(Path,sys.argv[1:3]); D="2cf2f3127f96d4d5dea30f8afe05119cf8e4ba57bd9e60b789d3f296fc8459ab"
with src.open("rb") as f:assert hashlib.file_digest(f,"sha256").hexdigest()==D
field="Airport_fee"
obj=pq.ParquetFile(src)
assert obj.schema_arrow.field(field).type==pa.float64()
def tally(x):
    return [len(x),x.null_count,pc.sum(pc.cast(pc.is_nan(x),pa.int64())).as_py() or 0]
tot=[0,0,0]; selection=[]; start=None; defined=[]
for t in obj.iter_batches(columns=[field],batch_size=65536):
    x=t.column(0)
    if len(defined)<1024:
        native_needed=1024-len(defined)
        idx=pc.indices_nonzero(x.is_valid()).slice(0,native_needed).to_pylist()
        defined.extend((tot[0]+i,x[i].as_py()) for i in idx)
    if start is None and x.null_count:
        k=next(i for i,z in enumerate(x.is_null().to_pylist()) if z)
        start=tot[0]+k
        selection+=x.slice(k,2048).to_pylist()
    elif start is not None and len(selection)<2048:
        selection+=x.slice(0,2048-len(selection)).to_pylist()
    tot=[a+b for a,b in zip(tot,tally(x))]
assert tot[0]==4_181_444 and len(selection)==2048 and selection[0] is None
assert tot[1]>0 and tot[2]==0 and len(defined)==1024
def pack(v,p,ids=None):
    table=pa.table({"rid":pa.array(range(start,start+len(v)) if ids is None else ids,type=pa.int64()),
                    "amount":pa.array(v,type=pa.float64(),from_pandas=False)})
    pq.write_table(table,p)
    return table
def eq(f,a,b):
    try:f(a,b)
    except AssertionError:return False
    return True
with tempfile.TemporaryDirectory(prefix="tlc-null-nan-",dir=scratch) as t:
    w=Path(t); p0=w/'original.parquet';p1=w/'valid_nan.parquet'
    def observed(p):
        return pq.read_table(p).column('amount')
    py0=pack(selection,p0)
    py1=pack([float('nan')]+selection[1:],p1)
    a,b=map(observed,(p0,p1))
    assert len(a)==len(b)==2048 and a[0].as_py() is None and math.isnan(b[0].as_py())
    a0,b0=tally(a),tally(b)
    assert a0==[b0[0],b0[1]+1,0] and b0[2]==1
    db=duckdb.connect(config={'threads':1})
    n=[]
    for p in (p0,p1):
        n.append(list(db.execute('select count(*),count(*) filter(where amount is null),count(*) filter(where isnan(amount)) from read_parquet(?)',[str(p)]).fetchone()))
    assert n==[a0,b0]
    dto={}
    for label,kw in [('default_numpy',{}),('numpy_nullable',{'dtype_backend':'numpy_nullable'}),('arrow_backend',{'dtype_backend':'pyarrow'})]:
        x=pd.read_parquet(p0,engine='pyarrow',**kw);y=pd.read_parquet(p1,engine='pyarrow',**kw)
        assert eq(pdeq,x,x.copy(deep=True)) and eq(pdeq,y,y.copy(deep=True))
        dto[label]=dict(match=eq(pdeq,x,y),amount_dtype=str(x.amount.dtype),
                        null_marker_counts=[int(x.amount.isna().sum()),int(y.amount.isna().sum())])
    assert dto['default_numpy']['match'] and not dto['arrow_backend']['match']
    x,y=map(pl.read_parquet,(p0,p1))
    assert eq(pleq,x,x.clone()) and eq(pleq,y,y.clone())
    pr=dict(match=eq(pleq,x,y),nulls=[x["amount"].null_count(),y["amount"].null_count()],
            nans=[x["amount"].is_nan().sum(),y["amount"].is_nan().sum()])
    m0=w/'mixed-original.parquet';m1=w/'mixed-nan.parquet'
    vd=[z for _,z in defined]
    rid_m=[start+i for i in range(1024)]+[i for i,_ in defined]
    assert len(set(rid_m))==2048 and not any(z is not None for z in selection[:1024])
    pack(selection[:1024]+vd,m0,rid_m);pack([float('nan')]+selection[1:1024]+vd,m1,rid_m)
    mix_counts=[tally(observed(j)) for j in (m0,m1)]
    assert mix_counts==[[2048,1024,0],[2048,1023,1]]
    mixed_pd={}
    for label,kw in [('default_numpy',{}),('numpy_nullable',{'dtype_backend':'numpy_nullable'}),('arrow_backend',{'dtype_backend':'pyarrow'})]:
        x=pd.read_parquet(m0,engine='pyarrow',**kw);y=pd.read_parquet(m1,engine='pyarrow',**kw)
        mixed_pd[label]=eq(pdeq,x,y)
    assert mixed_pd==dict(default_numpy=True,numpy_nullable=False,arrow_backend=False)
    sql_out=[]
    for p in (m0,m1):
        count,total=db.execute('select count(amount),sum(amount) from read_parquet(?)',[str(p)]).fetchone()
        sql_out.append([count,'nan' if math.isnan(total) else 'finite'])
    assert sql_out==[[1024,'finite'],[1025,'nan']]
    assert pr==dict(match=False,nulls=[a0[1],b0[1]],nans=[0,1])
print(json.dumps(dict(original_native_panel=dict(rows=tot[0],nulls=tot[1],nans=tot[2],field=field,sha256=D),
 selected_rows=2048,arrow_counts=[a0,b0],duckdb_counts=n,pandas=dto,polars=pr,
 mixed_control=dict(arrow_counts=mix_counts,pandas_matches=mixed_pd,duckdb_count_and_sum_kind=sql_out),
 versions=dict(duckdb=duckdb.__version__,polars=pl.__version__,pandas=pd.__version__,arrow=pa.__version__)),sort_keys=True,indent=2))
