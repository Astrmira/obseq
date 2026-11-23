import sys,hashlib,json,os,tempfile,struct
from pathlib import Path
from itertools import combinations
from collections import Counter
P=Path('/tmp/pvl-eab-submission/e1/input')
sys.path[:0]=[str(P/'duck143'),str(P/'more')]
import duckdb,pyarrow as pa,pyarrow.parquet as pq,pyarrow.dataset as ds,polars as pl
H=Path(__file__).parent
w='cbd_congestion_fee'
def sha(f):
 with Path(f).open('rb') as a:return hashlib.file_digest(a,'sha256').hexdigest()
def data(root):
 J=[]
 for i,row in enumerate((H/'INPUTS.sha256').read_text().splitlines()):
  h,f=row.split();p=Path(root)/f;assert sha(p)==h
  F=pq.ParquetFile(p);present=w in F.schema.names
  q=next(F.iter_batches(batch_size=2048,columns=[w] if present else [F.schema.names[0]]))
  assert q.num_rows==2048
  J.append((i,f,present,q.column(0).to_pylist() if present else [None]*q.num_rows))
 assert J[0][2]==False and J[1][2]==True
 return J
def main(root):
 D=duckdb.connect();src=data(root)
 T=pa.schema([('k',pa.int64()),('v',pa.float64())])
 raw={}
 with tempfile.TemporaryDirectory() as tmp:
  d=Path(tmp); files=[];expect=[];manifest={}
  for i,name,present,vals in src:
   ks=list(range(i*2048,(i+1)*2048));cols={'k':pa.array(ks,type=pa.int64())}
   if present:cols['v']=pa.array(vals,type=pa.float64())
   f=d/f'{i}.parquet';pq.write_table(pa.table(cols),f);files.append(str(f))
   manifest[f.name]=(sha(f),'v' in pq.ParquetFile(f).schema.names)
   assert manifest[f.name][1]==present
   expect.extend((k,v,present) for k,v in zip(ks,vals))
  def canonical(rows):return [(int(k),v) for k,v in sorted(rows)]
  Pairs=canonical((k,v) for k,v,p in expect)
  X=D.execute('select k,v,filename from read_parquet(?, union_by_name=true, filename=true) order by k',[files]).fetchall()
  out={
   'DuckDB union_by_name':canonical((k,v) for k,v,f in X),
   'Arrow explicit schema':canonical(zip(*[c.to_pylist() for c in ds.dataset(files,format='parquet',schema=T).to_table().columns])),
   'Polars missing_columns=insert':canonical(pl.scan_parquet(files,schema={'k':pl.Int64,'v':pl.Float64},missing_columns='insert').collect().rows())}
  assert all(r==Pairs for r in out.values())
  for k,v,f in X:assert manifest[Path(f).name][0]==sha(f)
  tagged=[(k,v,manifest[Path(f).name][1]) for k,v,f in X]
  assert tagged==expect
  keyfields={k:('KEEP' if not p else 'CLEAR' if v is None else 'WRITE') for k,v,p in tagged}
  def merge(rows,strategy):
   D.execute('DROP TABLE IF EXISTS target');D.execute('DROP TABLE IF EXISTS incoming')
   D.execute('CREATE TABLE target(k BIGINT PRIMARY KEY,v DOUBLE)');D.execute('CREATE TABLE incoming(k BIGINT,v DOUBLE,present BOOLEAN)')
   D.executemany('INSERT INTO target VALUES (?,777)',[(i,) for i,_,_ in rows]);D.executemany('INSERT INTO incoming VALUES (?,?,?)',rows)
   extra={'always':'','skip-null':' AND src.v IS NOT NULL','presence':' AND src.present'}[strategy]
   D.execute(f'MERGE INTO target t USING incoming src USING(k) WHEN MATCHED{extra} THEN UPDATE SET v=src.v')
   return D.execute('SELECT k,v FROM target ORDER BY k').fetchall()
  app=[(k,v if p else 777.) for k,v,p in expect]
  assert merge(tagged,'presence')==app
  real={key:sum(a!=b for a,b in zip(app,merge(tagged,key))) for key in ('always','skip-null','presence')}
  # Same path and scalar values, different actual footer intent; digest gate
  # refuses to attach a stale bit to a replacement object under its old path.
  f=Path(files[0]);h=manifest[f.name][0]
  pq.write_table(pa.table({'k':pa.array(range(2048),type=pa.int64()),'v':pa.nulls(2048,type=pa.float64())}),f)
  assert f.name in manifest and sha(f)!=h
  stale_path_read_all_null=D.execute('select count(v),count(*) from read_parquet(?)',[str(f)]).fetchone()
  assert stale_path_read_all_null==(0,2048)
  raw=dict(real_presence={f'{i}/{name}':dict(present=present,nonnull=sum(x is not None for x in v),null_after_union=sum(x is None for x in v)) for i,name,present,v in src},
           stock_engine_count=len(out),real_patch_intents=Counter(keyfields.values()),authored_policy_effect_mismatch_on_real_values=real,stale_path_rebinding_rejected_by_hash=True)
  # Six-row mixed intent across each physical single file; all 20 have
  # exactly the same payload after scalar projection but different effects.
  receipts={};raw_sha=set();effects=set();packed_sha=set()
  for chosen in combinations(range(6),3):
   src_rows=[dict(k=i,**({'v':None} if i in chosen else {})) for i in range(6)]
   j=d/'source.jsonl';j.write_text(''.join(json.dumps(r)+'\n' for r in src_rows))
   # Native JSON predicate on each whole JSON object, before field projection.
   rows=D.execute("SELECT i, json_extract_string(obj, '$.v')::DOUBLE v, json_exists(obj, '$.v') p FROM unnest(?) WITH ORDINALITY j(obj,ord) CROSS JOIN LATERAL (SELECT ord - 1 i) s ORDER BY i",[[json.dumps(r) for r in src_rows]]).fetchall()
   assert rows==[(i,None,i in chosen) for i in range(6)]
   x=d/'collapsed.parquet';z=d/'preserved.parquet'
   kvec=pa.array([r[0] for r in rows],type=pa.int64());vvec=pa.array([r[1] for r in rows],type=pa.float64())
   pq.write_table(pa.table({'k':kvec,'v':vvec}),x);raw_sha.add(sha(x))
   pq.write_table(pa.table({'k':kvec,'v':vvec,'present':[r[2] for r in rows]}),z);packed_sha.add(sha(z))
   R=D.execute('SELECT k,v,present FROM read_parquet(?) ORDER BY k',[str(z)]).fetchall()
   A=merge(R,'presence');assert A==[(i,None if i in chosen else 777.) for i in range(6)]
   effects.add(tuple(A));receipts[','.join(map(str,chosen))]=A
  assert len(raw_sha)==1 and len(effects)==len(packed_sha)==20
 print(json.dumps(dict(versions=[duckdb.__version__,pa.__version__,pl.__version__],**raw,
    authored_mixed=dict(controls=20,distinct_value_only_native_parquet_files_by_hash=len(raw_sha),distinct_presence_native_parquet_files_by_hash=len(packed_sha),distinct_verified_merge_effects=len(effects),minimum_boolean_receipt_bits=(len(effects)-1).bit_length(),raw_digest=next(iter(raw_sha)),effects=receipts)),indent=2,sort_keys=True))
if __name__=='__main__':main(sys.argv[1])
