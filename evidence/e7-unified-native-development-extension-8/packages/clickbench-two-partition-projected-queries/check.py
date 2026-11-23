"""SQL only over two admitted source columns. No general sparse-Parquet access."""
from pathlib import Path
from fractions import Fraction
import hashlib, json, sys
import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

root,capture,sql,partzero=map(Path,sys.argv[1:5])
with partzero.open("rb") as f:
    assert hashlib.file_digest(f,"sha256").hexdigest()=="fa134fe101e68324e0de851146fda69624f5cbb707d387141d1c2a88a219a16d"
stock=sql.read_bytes()
assert hashlib.sha256(stock).hexdigest()=='274ffe1c4f83baad2fc177bbb6773bbdab0db779faeb2970de8cc531292a5dc6'
queries=[row.decode() for row in stock.splitlines() if row.strip()]
assert len(queries)==43
assert queries[:3]==['SELECT COUNT(*) FROM hits;', 'SELECT COUNT(*) FROM hits WHERE AdvEngineID <> 0;',
                    'SELECT SUM(AdvEngineID), COUNT(*), AVG(ResolutionWidth) FROM hits;']
records=json.loads(capture.read_text())
assert [r['part'] for r in records]==[1]
records.insert(0,dict(part=0,object_bytes=partzero.stat().st_size,rows=1000000,pages=[],projected_compressed_bytes=0))
cols=('AdvEngineID','ResolutionWidth')
N=S=W=NNZ=NW=0
allnames=[];receipts=[]
for rec in records:
    file=(root/f"hits_{rec['part']}.parquet").resolve() if rec["part"] else partzero.resolve()
    assert file.stat().st_size==rec['object_bytes']
    if rec['part']:assert rec==json.loads(file.with_suffix('.json').read_text())
    allnames.append(str(file))
    with file.open('rb') as f:
        f.seek(-8,2);z=f.read(8)
        assert z[4:]==b'PAR1'
        m=int.from_bytes(z[:4],'little')
        f.seek(-8-m,2)
        got=hashlib.sha256(f.read(m+8)).hexdigest()
        if rec['part']:assert got==rec['footer_sha256']
        bounded=hashlib.sha256()
        for start,size in rec['pages']:
            f.seek(start)
            chunk=f.read(size)
            assert len(chunk)==size
            bounded.update(start.to_bytes(8,'little'));bounded.update(size.to_bytes(8,'little'));bounded.update(chunk)
    v=pq.ParquetFile(file)
    assert v.metadata.num_rows==rec['rows']
    t=v.read(columns=list(cols))
    assert t.num_rows==rec['rows']
    a,b=(t[n] for n in cols)
    assert pa.types.is_integer(a.type) and pa.types.is_integer(b.type)
    nnz=pc.sum(pc.cast(pc.not_equal(a,0),pa.int64())).as_py()
    aa,bb=pc.sum(a).as_py(),pc.sum(b).as_py()
    N+=t.num_rows
    S+=aa; W+=bb
    NNZ+=nnz
    NW+=len(b)-b.null_count
    lo,hi=pc.min_max(a).as_py().values()
    lw,hw=pc.min_max(b).as_py().values()
    assert 0<=lo<=hi and 0<=lw<=hw
    receipts.append(dict(part=rec['part'],seal=bounded.hexdigest() if rec["part"] else "full-file-digest-in-checker",rows=t.num_rows,adv_nonzero=nnz,
        adv_total=aa,width_total=bb,width_nonnull=len(b)-b.null_count,adv_min=lo,adv_max=hi,width_min=lw,width_max=hw))
assert N==2_000_000 and NW>0 and W<2**53 and NW<2**53
db=duckdb.connect(config={'threads':1,'memory_limit':'512MB','max_temp_directory_size':'0B'})
def q(text):return "'"+text.replace("'","''")+"'"
files='['+','.join(q(s) for s in allnames)+']'
db.execute(f'CREATE VIEW hits AS SELECT AdvEngineID, ResolutionWidth FROM read_parquet({files})')
native=[db.execute(q).fetchone() for q in queries[:3]]
avg=Fraction(W,NW)
assert native==[(N,),(NNZ,),(S,N,float(avg))],native
print(json.dumps(dict(source_identity_records=receipts,rows=N,duckdb=duckdb.__version__,pyarrow=pa.__version__,
   physical_parquet_columns=cols,native_stock_queries_on_two_partitions=3,native=native,exact_avg_ratio=[avg.numerator,avg.denominator],
   width_nonnull=NW,width_integer_total=W,projected_compressed_bytes=sum(r['projected_compressed_bytes'] for r in records),
   accepted_part1_footer_suffix_bytes=65536,object_bytes=sum(r['object_bytes'] for r in records)),sort_keys=True,indent=2))
