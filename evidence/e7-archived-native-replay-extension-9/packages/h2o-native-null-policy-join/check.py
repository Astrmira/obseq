from collections import Counter,defaultdict
from pathlib import Path
import csv,hashlib,json,sys,itertools
from decimal import Decimal
import duckdb
src=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/workspace/shared/eab-h2o-join-single-lane-guarded/J1_1e7_NA_5_0.csv')
with src.open('rb') as f:
    assert hashlib.file_digest(f,'sha256').hexdigest()=='29205553b85cee0eb36a52b0d16ed1a8067ba066ac28d7c2a995a5db371f7061'
SMALL=5000
modes=['ordinary','nullsafe','key_complete','global_complete']
H=[defaultdict(lambda:[0,0,0,0,0,0]),defaultdict(lambda:[0,0,0,0,0,0])]
M=[defaultdict(lambda:[0,0,0,0,0,0]),defaultdict(lambda:[0,0,0,0,0,0])]
prefix=[]
excluded_v1_null=0
# Hist fields: total, id3-NULL, complete(all 7) per L and R.
with src.open(newline='') as f:
    r=csv.reader(f)
    assert next(r)==['id1','id2','id3','id4','id5','id6','v1']
    for i,raw in enumerate(r):
        a,b,c,x,y,z,p=raw
        v=lambda s:int(s) if s else None
        k=(v(a),v(b))
        if i<SMALL:prefix.append(tuple(None if a=='' else a for a in raw))
        if not p:
            excluded_v1_null+=1
            continue
        # v1 producer stores nonnegative 6-place dollars-like decimal;
        # integer leading part is enough for its exact 50 split.
        whole,_,tail=p.partition('.')
        if whole.isdigit() and (not tail or tail.isdigit()) and len(tail)<=6:
            side=int(int(whole)>=50)
        else:
            vv=Decimal(p)
            assert vv.is_finite() and vv*10**6==int(vv*10**6)
            side=int(vv>=50)
        pos=3*side
        full=all(raw)
        for HH in ([H[side],M[side]] if i<SMALL else [H[side]]):
            h=HH[k]
            h[pos]+=1
            h[pos+1]+=not c
            h[pos+2]+=full
    assert i+1==10_000_000
def mask(k): return int(k[0] is None)+2*int(k[1] is None)
def calc(h,mode):
    l,r=h
    out=Counter(dict(l_rows=0,r_rows=0,l_matched=0,l_unmatched=0,pairs=0,pairs_with_id3_null=0,mask0=0,mask1=0,mask2=0,mask3=0))
    def admit(k): return mode!='key_complete' or mask(k)==0
    out['r_rows']=sum(t[5 if mode=='global_complete' else 3] for k,t in r.items() if admit(k))
    for k,t in l.items():
        if not admit(k):continue
        null=mask(k)
        s=r.get(k,(0,0,0,0,0,0))
        a,an=(t[2],0) if mode=='global_complete' else (t[0],t[1])
        b,bn=(s[5],0) if mode=='global_complete' else (s[3],s[4])
        if mode=='ordinary' and null: b=bn=0
        out['l_rows']+=a
        out['l_matched' if b else 'l_unmatched']+=a
        out['pairs']+=a*b
        out[f'mask{null}']+=a*b
        out['pairs_with_id3_null']+=an*b+(a-an)*bn
    return dict(out)
db=duckdb.connect(config={'threads':'1','memory_limit':'512MB','max_temp_directory_size':'0B'})
scan="""read_csv(?, header=true, columns={'id1':'INTEGER','id2':'INTEGER','id3':'INTEGER',
'id4':'VARCHAR','id5':'VARCHAR','id6':'VARCHAR','v1':'DECIMAL(16,6)'},strict_mode=true,nullstr='')"""
coll="""
SELECT id1,id2,(v1>=50)::INTEGER AS side,count(*) AS n,count(*) FILTER(id3 IS NULL) AS miss,
       count(*) FILTER(id1 IS NOT NULL AND id2 IS NOT NULL AND id3 IS NOT NULL AND id4 IS NOT NULL
                       AND id5 IS NOT NULL AND id6 IS NOT NULL AND v1 IS NOT NULL) AS complete
FROM %s WHERE v1 IS NOT NULL GROUP BY id1,id2,side"""
native=[{},{}]
db.execute('CREATE TABLE hist AS '+coll%scan,[str(src)])
for a,b,c,n,nnull,nfull in db.execute('SELECT * FROM hist').fetchall():
    assert c in (0,1)
    assert (n,nnull,nfull)==tuple(H[c][a,b][3*c:3*c+3])
    native[c][a,b]=(n,nnull,nfull)
assert all(set(x)==set(y) for x,y in zip(H,native))
base_filter='TRUE'
directN=[]
for mode in modes:
    join=('l.id1=r.id1 AND l.id2=r.id2' if mode=='ordinary' else
          'l.id1 IS NOT DISTINCT FROM r.id1 AND l.id2 IS NOT DISTINCT FROM r.id2')
    fil='id1 IS NOT NULL AND id2 IS NOT NULL' if mode=='key_complete' else base_filter
    n='complete' if mode=='global_complete' else 'n'
    m='0' if mode=='global_complete' else 'miss'
    sql=f'''WITH l AS (SELECT id1,id2,{n} n,{m} miss FROM hist WHERE side=0 AND ({fil}) AND {n}>0),
        r AS (SELECT id1,id2,{n} n,{m} miss FROM hist WHERE side=1 AND ({fil}) AND {n}>0)
SELECT SUM(l.n), (SELECT SUM(n) FROM r),
  COALESCE(SUM(l.n) FILTER (r.n IS NOT NULL),0),
  COALESCE(SUM(l.n) FILTER (r.n IS NULL),0),
  SUM(l.n*COALESCE(r.n,0)),
  SUM(l.miss*COALESCE(r.n,0)+(l.n-l.miss)*COALESCE(r.miss,0)),
  {','.join(f'COALESCE(SUM(l.n*r.n) FILTER((l.id1 IS NULL)::INT+2*(l.id2 IS NULL)::INT={i}),0)' for i in range(4))}
FROM l LEFT JOIN r ON {join}'''
    observed=dict(zip(('l_rows','r_rows','l_matched','l_unmatched','pairs','pairs_with_id3_null','mask0','mask1','mask2','mask3'),db.execute(sql).fetchone()))
    assert observed==calc(H,mode)
    directN.append(observed)
db.execute(f'CREATE TABLE sample AS SELECT * FROM {scan} LIMIT {SMALL}',[str(src)])
def normalize(row):
    return tuple((int(a) if p in (0,1,2) else Decimal(a) if p==6 else a) if a is not None else None for p,a in enumerate(row))
assert db.execute('SELECT * FROM sample ORDER BY rowid').fetchall()==list(map(normalize,prefix))
directSmall=[]
for mode in modes:
    fil=('id1 IS NOT NULL AND id2 IS NOT NULL' if mode=='key_complete' else
        ' AND '.join(f'{a} IS NOT NULL' for a in ('id1','id2','id3','id4','id5','id6','v1')) if mode=='global_complete' else 'TRUE')
    join=('l.id1=r.id1 AND l.id2=r.id2' if mode=='ordinary' else
          'l.id1 IS NOT DISTINCT FROM r.id1 AND l.id2 IS NOT DISTINCT FROM r.id2')
    q=f'''WITH l AS (SELECT * FROM sample WHERE v1<50 AND ({fil})), r AS (SELECT * FROM sample WHERE v1>=50 AND ({fil}))
          SELECT count(*),count(*) FILTER(l.id3 IS NULL OR r.id3 IS NULL) FROM l JOIN r ON {join}'''
    sample=calc(M,mode)
    assert db.execute(q).fetchone()==(sample['pairs'],sample['pairs_with_id3_null'])
    directSmall.append(sample)
print(json.dumps(dict(duckdb=duckdb.__version__,full_rows=i+1,excluded_null_split=excluded_v1_null,direct_sample_rows=SMALL,full_scope='factorized exact pair counts only',
                      distinct_key_histograms=[len(x) for x in native],full=dict(zip(modes,directN)),
                      native_literal_sample=dict(zip(modes,directSmall))),sort_keys=True,indent=2))
