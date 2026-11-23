import hashlib,sys,json
from pathlib import Path
from collections import Counter
import duckdb
root=Path(sys.argv[1]);H=Path(__file__).resolve().parent
xs=[]
for line in (H/'INPUTS.sha256').read_text().splitlines():
 h,name=line.split();data=(root/name).read_bytes();assert hashlib.sha256(data).hexdigest()==h
 xs.extend(map(int,data.splitlines()))
# Integer ties-even reference for all actual IDs, independently of DuckDB and Python float.
def narrowed(n):
 s=max(n.bit_length()-53,0);d,r=divmod(n,1<<s)
 return (d+(2*r>(1<<s) or (2*r==(1<<s) and d%2==1)))<<s
pairs={}
for x in set(xs):pairs.setdefault(narrowed(x),[]).append(x)
collision=[sorted(x) for x in pairs.values() if len(x)>1]
assert len(collision)==1
a,b=collision[0]
d=duckdb.connect(config={'threads':1})
d.execute('create table source(pos BIGINT,id BIGINT)')
# This cohort is small enough for native typed vector unnest without extending any underlying file.
d.execute('insert into source select generate_subscripts(xs,1)::BIGINT,unnest(xs) from (select ?::BIGINT[] xs)',[xs+[None]])
def diag(x,y,all_=True):
 o='ALL' if all_ else ''
 return [d.execute('select count(*) from (('+l+') EXCEPT '+o+' ('+r+'))').fetchone()[0] for l,r in ((x,y),(y,x))]
base='select pos,id from source';cast='select pos,id::DOUBLE as id from source';lift='select pos,id::DOUBLE::BIGINT as id from source'
assert d.execute('describe '+base).fetchall()[1][1]=='BIGINT'
assert d.execute('describe '+cast).fetchall()[1][1]=='DOUBLE'
assert d.execute('describe (('+base+') EXCEPT ALL ('+cast+'))').fetchall()[1][1]=='DOUBLE'
common=diag(base,cast); exact=diag(base,lift)
c=sum(x!=narrowed(x) for x in xs)
assert common==[0,0] and exact==[c,c] and c>0
# Same-width comparator remains a real bag guard after schema admission.
u=f'select * from (values ({a}::BIGINT),({b}::BIGINT),({a}::BIGINT)) t(id)'
v=f'select * from (values ({a}::BIGINT),({b}::BIGINT),({b}::BIGINT)) t(id)'
set_only=diag(u,v,False); bag=diag(u,v)
assert set_only==[0,0] and bag==[1,1]
# A matched numeric/common-type equivalence case may be intentionally desirable.
legal=diag('select 7::BIGINT id','select 7::DOUBLE id');assert legal==[0,0]
# A physical type name nested inside a STRUCT also changes; its pre-coercion
# receipt is not the same one as after combination casting widens both records.
l='select struct_pack(id := 41::BIGINT) AS key'
r='select struct_pack(id := 41::BIGINT, memo := NULL::VARCHAR) AS key'
nested=diag(l,r)
nestedtypes=[d.execute('describe '+q).fetchone()[1] for q in (l,r)]
assert nested==[0,0] and nestedtypes[0]!=nestedtypes[1]
print(json.dumps(dict(engine=duckdb.__version__,source_rows=len(xs),exclusive_null_control_rows=1,exact_integer_changed=c,domain_collision_classes=len(collision),mixed_native_except_all_directions=common,exact_int_reference_directions=exact,same_typed_bag_duplicate_directions=bag,same_typed_distinct_duplicate_directions=set_only,legal_declared_numeric_value_equal_directions=legal,nested_absent_vs_null_directions=nested,nested_types=nestedtypes),sort_keys=True,indent=2))
