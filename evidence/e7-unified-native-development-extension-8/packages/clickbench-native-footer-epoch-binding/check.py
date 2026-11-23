import hashlib,json,sys,tempfile
from pathlib import Path
import duckdb,pyarrow as pa,pyarrow.dataset as ds,pyarrow.parquet as pq
p=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/workspace/shared/eab-job-authority/hits_0.parquet')
scratch=Path(sys.argv[2]) if len(sys.argv)>2 else Path('/workspace/shared')
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert digest(p)=='fa134fe101e68324e0de851146fda69624f5cbb707d387141d1c2a88a219a16d'
assert pa.__version__=='26.0.1' and duckdb.__version__=='1.4.3'
pf=pq.ParquetFile(p)
N=32_768
old=[];new=[]
for b in pf.iter_batches(columns=['AdvEngineID'],batch_size=16384):
    a=b.column(0); assert a.type==pa.int16() and a.null_count==0
    rows=a.to_pylist()
    new.extend(rows[:N-len(new)])
    old.extend([r for r in rows if r==0][:N-len(old)])
    if len(old)==len(new)==N:break
pf.close()
assert len(old)==len(new)==N and not any(old)
want=[e for e in new if e>0]
assert want and len(want)<N
db=duckdb.connect(config={'threads':'1'})
expected_pred=ds.field('AdvEngineID')>0
def read_d(X,**kw):
    return X.to_table(columns=['AdvEngineID'],**kw).column(0).to_pylist()
def stats(P):
    rows=[]
    for i in range(P.num_row_groups):
        g=P.row_group(i); c=g.column(0)
        assert c.statistics.has_min_max and c.statistics.has_null_count and c.statistics.null_count==0
        rows.append(dict(rows=g.num_rows,minimum=c.statistics.min,maximum=c.statistics.max,
                         offset=c.data_page_offset,bytes=c.total_compressed_size))
    return rows
with tempfile.TemporaryDirectory(prefix='eab-f3-parquet-',dir=scratch) as td:
    root=Path(td); A=root/'a.parquet';B=root/'b.parquet';pname=root/'current.parquet'
    for dst,vals in [(A,old),(B,new)]:
        pq.write_table(pa.table({'AdvEngineID':pa.array(vals,type=pa.int16())}),
                       dst,use_dictionary=False,compression='NONE',row_group_size=4096)
        assert db.execute('SELECT count(*),count(*) FILTER(AdvEngineID>0) FROM read_parquet(?)',[str(dst)]).fetchone()==(N,sum(v>0 for v in vals))
    files={key:dict(sha256=digest(f),bytes=f.stat().st_size,row_groups=stats(pq.read_metadata(f))) for key,f in [('a',A),('b',B)]}
    def dims(j):return [(x['rows'],x['offset'],x['bytes']) for x in j['row_groups']]
    assert files['a']['sha256']!=files['b']['sha256']
    assert dims(files['a'])==dims(files['b'])
    assert files['a']['bytes']==files['b']['bytes']
    pname.symlink_to(A)
    held=pq.ParquetFile(pname)
    same=ds.dataset(str(pname),format='parquet')
    frag=list(same.get_fragments())[0]
    assert stats(frag.metadata)==files['a']['row_groups']
    assert same.count_rows()==N and same.count_rows(filter=expected_pred)==0 and read_d(same,filter=expected_pred)==[]
    pending=root/'next.parquet'; pending.symlink_to(B); pending.replace(pname)
    assert digest(pname)==files['b']['sha256']
    warm_filtered=read_d(same,filter=expected_pred)
    warm_no_cache=read_d(same,filter=expected_pred,cache_metadata=False)
    warm_unfiltered=read_d(same)
    assert warm_filtered==warm_no_cache==[] and warm_unfiltered==new
    assert same.count_rows(filter=expected_pred)==0
    assert same.count_rows(filter=expected_pred,cache_metadata=False)==0
    observed_metadata=stats(frag.metadata)
    assert observed_metadata==files['b']['row_groups']
    assert same.count_rows(filter=expected_pred)==len(read_d(same,filter=expected_pred))==0
    other=ds.dataset(str(pname),format='parquet')
    assert other.schema==same.schema and other.count_rows()==same.count_rows()==N
    assert stats(list(other.get_fragments())[0].metadata)==files['b']['row_groups']
    assert other.count_rows(filter=expected_pred)==len(want)
    assert read_d(other)==new and read_d(other,filter=expected_pred)==want
    assert held.schema_arrow==same.schema and held.read(columns=['AdvEngineID']).column(0).to_pylist()==old
    assert stats(held.metadata)==files['a']['row_groups']
    assert db.execute('SELECT count(*),count(*) FILTER(AdvEngineID>0) FROM read_parquet(?)',[str(pname)]).fetchone()==(N,len(want))
    # Distinct path with explicit A identity independently preserves old data;
    # it is not an incorrect result when the caller deliberately requests A.
    assert read_d(ds.dataset(str(A),format='parquet'))==old
    result=dict(rows=N,known_positive_new=len(want),cached_predicate=len(warm_filtered),
        cached_predicate_cache_metadata_false=len(warm_no_cache),
        later_fragment_metadata_matches_b=True,predicate_after_inspecting_b_metadata=0,
        unfiltered_warm_positive=sum(v>0 for v in warm_unfiltered),fresh_predicate=len(want),
        held_current_positive=0,row_schema_same=True,physical_layout_same=True,files=files,
        pyarrow=pa.__version__,duckdb=duckdb.__version__)
print(json.dumps(result,sort_keys=True,indent=2))
