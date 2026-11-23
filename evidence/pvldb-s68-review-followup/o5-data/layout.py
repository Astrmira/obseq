import hashlib,io,json,os,pathlib,subprocess,sys,threading,time
import pyarrow as pa
import pyarrow.csv as csv
import pyarrow.dataset as ds
import pyarrow.parquet as pq

root=pathlib.Path(__file__).resolve().parent
N=int(sys.argv[1]); stage=pathlib.Path(sys.argv[2]).resolve(); target=pathlib.Path(sys.argv[3]).resolve()
assert not target.exists() and N in (100000,100000000)
rl=pathlib.Path(os.environ['R_HOME']).resolve()
env=os.environ|dict(R_HOME=str(rl),LD_LIBRARY_PATH=str(rl/'lib'),R_LIBS_SITE=str(rl/'site-library'),TMPDIR=str(root),OMP_THREAD_LIMIT='1',OMP_NUM_THREADS='1')
dig=hashlib.sha256(); total=0; start=time.monotonic(); low=1<<63
base=pa.schema([(f'id{i}',pa.string() if i<=3 else pa.int32()) for i in range(1,7)]+[(f'v{i}',pa.int32() if i<=2 else pa.decimal128(12,6)) for i in range(1,4)])
schema=base.append(pa.field('ordinal',pa.uint32()))
def space():
 u=os.statvfs(root);return u.f_frsize*u.f_bavail
class HashPipe(io.RawIOBase):
 def __init__(self,s):self.s=s
 def readable(self):return True
 def readinto(self,b):
  n=self.s.readinto(b)
  if n:dig.update(memoryview(b)[:n])
  return n
with (root/(f'render-{N}.log')).open('w') as err:
 p=subprocess.Popen([os.environ['OBSEQ_R_LAUNCHER'],'--vanilla','--slave','-f',str(root/'render-stdout.R'),'--args',str(N),'100','250000',str(stage),'stdout'],env=env,stdout=subprocess.PIPE,stderr=err)
 try:
  table=csv.open_csv(io.BufferedReader(HashPipe(p.stdout)),read_options=csv.ReadOptions(block_size=4<<20,use_threads=False),convert_options=csv.ConvertOptions(column_types=base))
  assert table.schema==base
  def stream():
   global total,low
   for b in table:
    low=min(low,space())
    if low<330_000_000:raise RuntimeError('shared workspace floor')
    assert sum(c.null_count for c in b.columns)==0
    n=b.num_rows
    ordinal=pa.array(range(total,total+n),type=pa.uint32())
    total+=n
    if total//5000000!=(total-n)//5000000:print(f'parsed {total} of {N}; free {low}',file=sys.stderr,flush=True)
    yield pa.RecordBatch.from_arrays([*b.columns,ordinal],schema=schema)
  fmt=ds.ParquetFileFormat()
  ds.write_dataset(pa.RecordBatchReader.from_batches(schema,stream()),str(target),format=fmt,
    file_options=fmt.make_write_options(compression='zstd',use_dictionary=['id2','id4','id5','v1','v2']),
    partitioning=ds.partitioning(pa.schema([('id1',pa.string())]),flavor='hive'),
    use_threads=False,max_open_files=110,min_rows_per_group=8000,max_rows_per_group=50000,
    existing_data_behavior='error')
  assert p.wait(timeout=10)==0 and total==N
 finally:
  if p.poll() is None:p.terminate();p.wait()
metadata={}
for f in sorted(target.rglob('*.parquet')):
 m=pq.ParquetFile(f)
 assert m.schema_arrow==pa.schema([a for a in schema if a.name!='id1'])
 k=f.parent.name
 metadata[k]=metadata.get(k,0)+m.metadata.num_rows
assert len(metadata)==100 and sum(metadata.values())==N
print(json.dumps(dict(csv_sha256=dig.hexdigest(),total=total,buckets=metadata,low_free_bytes=low,arrow=pa.__version__,wall_seconds=round(time.monotonic()-start,3)),sort_keys=True))
