"""Capture only verified Parquet footer and two named column chunks into sparse scratch."""
from urllib.request import Request,urlopen
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,io,json,re,struct,sys,time
import pyarrow.parquet as pq
base='https://datasets.clickhouse.com/hits_compatible/athena_partitioned'
spec=Path(sys.argv[1]);dest=Path(sys.argv[2]); records=json.loads(spec.read_text())
assert len(sys.argv)==4 and int(sys.argv[3])==1
sel=[r for r in records if r["part"]==1]
assert len(sel)==1
cols=('AdvEngineID','ResolutionWidth')
def get(url,lo,hi,total,etag):
    assert 4_000_000>=hi-lo+1>0
    for turn in range(3):
        try:
            with urlopen(Request(url,headers={'Range':f'bytes={lo}-{hi}','If-Match':etag,'User-Agent':'ClickBench-two-column-audit/1'}),timeout=12) as r:
                assert r.status==206
                assert r.headers['ETag']==etag
                assert r.headers['Content-Range']==f'bytes {lo}-{hi}/{total}'
                b=r.read(hi-lo+2)
                assert len(b)==hi-lo+1
                return b
        except Exception as e:
            if turn==2:raise RuntimeError(url,lo,hi,str(e)) from None
            time.sleep(.5*(turn+1))
def part(r):
    i,T,e=r['part'],r['object_bytes'],r['etag']
    url=f'{base}/hits_{i}.parquet'
    m=r['footer_payload_bytes']
    tail=get(url,T-65536,T-1,T,e)
    footer=tail[-m-8:]
    assert hashlib.sha256(footer).hexdigest()==r['footer_sha256']
    p=pq.read_metadata(io.BytesIO(b'PAR1'+footer))
    assert p.num_rows==r['rows']
    names=[p.schema.column(k).name for k in range(p.num_columns)]
    spans=[]
    for j in range(p.num_row_groups):
        for k in [names.index(n) for n in cols]:
            col=p.row_group(j).column(k)
            first=col.data_page_offset
            if col.dictionary_page_offset is not None:first=min(first,col.dictionary_page_offset)
            n=col.total_compressed_size
            assert 4<=first<=first+n<=T-8-m
            spans.append((first,n))
    out=dest/f'hits_{i}.parquet'
    with (out.with_suffix('.partial')).open('wb') as f:
        f.write(b'PAR1');f.truncate(T)
        for first,n in spans:
            f.seek(first)
            f.write(get(url,first,first+n-1,T,e))
        f.seek(T-m-8);f.write(footer)
    out.with_suffix('.partial').replace(out)
    mf=pq.ParquetFile(out)
    assert mf.metadata.num_rows==r['rows']
    a=mf.read(columns=list(cols))
    assert a.num_rows==r['rows']
    receipt=dict(part=i,object_bytes=T,rows=r['rows'],projected_compressed_bytes=sum(n for i,n in spans),
                 pages=spans,footer_sha256=r['footer_sha256'],etag=e)
    (dest/f'hits_{i}.json').write_text(json.dumps(receipt,sort_keys=True)+'\n')
    return receipt
with ThreadPoolExecutor(max_workers=6) as pool:
    results=list(pool.map(part,sel))
print(json.dumps(results,sort_keys=True))
