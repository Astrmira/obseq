import csv,hashlib,logging,os,pathlib,sqlite3,sys,tempfile,json
from collections import Counter
H=pathlib.Path(__file__).parent;D=pathlib.Path(sys.argv[1]);S=pathlib.Path(sys.argv[2])
sys.path.insert(0,str(S/'deps')); os.environ['GX_ANALYTICS_ENABLED']='false'
import great_expectations as gx
import pandas as pd
import sqlalchemy
logging.disable(logging.CRITICAL)
assert gx.__version__=='1.25.0'
medium=D/'J1_1e7_1e4_5_0.csv'
assert hashlib.sha256(medium.read_bytes()).hexdigest()=='f2e8ce2fd70647d1930a6401b3ca4786f361f85b7456ff7ddcee90a5e721fce1'
with medium.open() as fi:
 vv=csv.DictReader(fi); rows=[next(vv) for i in range(12)]
source=[(f'r{i}',x['id5'],int(x['id1'])) for i,x in enumerate(rows)]
assert len({x[1] for x in source})==12
extra=[(f'a{i}',t.upper(),g) for i,(r,t,g) in enumerate(source[:4])]
plain=source+extra
typed=plain+[(f'u{i}',a,50) for i,a in enumerate(('Ä','ä','ß','SS'))]+[('n0',None,70),('n1',None,70),('n2',None,None),('n3',None,None)]
exactcase=source+[('duplicate_'+r,t,g) for r,t,g in source[:2]]
forms={'source':source,'case_edits':plain,'case_and_null_controls':typed,'literal_dupes':exactcase}
fold=lambda a:a.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')) if a is not None else None
forms['explicit_ascii_folded']=[(i,fold(t),g) for i,t,g in typed]
def ref(items,policy,skip):
 subset=[(i,(fold(t) if policy=='nocase' else t,g)) for i,t,g in items if (not(skip=='any_value_is_missing' and (t is None or g is None)) and not(skip=='all_values_are_missing' and t is None and g is None))]
 C=Counter(k for i,k in subset)
 return sorted(i for i,k in subset if C[k]>1)
def run(b,skip):
 e=b.validate(gx.expectations.ExpectCompoundColumnsToBeUnique(column_list=['token','grp'],ignore_row_if=skip,
         result_format={'result_format':'COMPLETE','unexpected_index_column_names':['rid'],'return_unexpected_index_query':False}))
 assert not e.exception_info.get('raised_exception',False),e.exception_info
 d=e.result
 co=lambda x:None if pd.isna(x) else x
 vals=[(co(v['token']),co(v['grp'])) for v in d['partial_unexpected_list']]
 assert len(vals)==d['unexpected_count']
 ids=sorted(v['rid'] for v in d.get('unexpected_index_list',[])) if 'unexpected_index_list' in d else None
 return vals,ids,dict(unexpected_count=d['unexpected_count'],native_index_ids_returned=ids is not None,success=e.success,element_count=d['element_count'])
out=[]
with tempfile.TemporaryDirectory(dir=S) as tmp:
 p=pathlib.Path(tmp)/'gx.db'
 ctx=gx.get_context(mode='ephemeral')
 pd0=ctx.data_sources.add_pandas('pd')
 sq=ctx.data_sources.add_sqlite(name='sq',connection_string=f'sqlite:///{p}')
 for tag,rs in forms.items():
  P=pd0.add_dataframe_asset('pd'+tag).add_batch_definition_whole_dataframe('whole')
  frames=pd.DataFrame({'rid':[i for i,t,g in rs],'token':pd.Series([t for i,t,g in rs],dtype=object),'grp':pd.Series([g for i,t,g in rs],dtype='Int64')})
  b0=P.get_batch(batch_parameters={'dataframe':frames})
  bd={}
  with sqlite3.connect(p) as c:
   for col in ('BINARY','NOCASE'):
    name=tag+'_'+col
    c.execute(f'CREATE TABLE {name}(rid TEXT NOT NULL,token TEXT COLLATE {col},grp INTEGER)')
    c.executemany(f'INSERT INTO {name} VALUES (?,?,?)',rs)
    assert c.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall()==rs
    c.commit()
    bd[col]=sq.add_table_asset(name=name,table_name=name).add_batch_definition_whole_table('whole')
  for skip in ('never','all_values_are_missing','any_value_is_missing'):
   for side,b,q in [('pandas',b0,'binary'),('sqlite_binary',bd['BINARY'].get_batch(),'binary'),('sqlite_nocase',bd['NOCASE'].get_batch(),'nocase')]:
    vv,ids,z=run(b,skip); target=ref(rs,q,skip)
    assert Counter(vv)==Counter((t,g) for i,t,g in rs if i in target),(tag,side,skip,z,target)
    if ids is not None: assert ids==target
    out.append(dict(dataset=tag,backend=side,ignore=skip,binary_oracle=len(ref(rs,'binary',skip)),nocase_oracle=len(ref(rs,'nocase',skip)),**z))
print(json.dumps(dict(gx=gx.__version__,sqlite=sqlite3.sqlite_version,pandas=pd.__version__,sqlalchemy=sqlalchemy.__version__,outcomes=out),indent=2,sort_keys=True))
