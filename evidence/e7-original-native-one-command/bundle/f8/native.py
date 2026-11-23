import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
import pyarrow as pa
import pyarrow.compute as ac
import polars as pl

src=Path(sys.argv[1])
read=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert read(src)=='8e86163e65e0deaa46f3450f7600aa03361141f9406e73b235e0c648a5804831'
assert pa.__version__=='26.0.1' and pl.__version__=='2.1.0'
fmt='%Y-%m-%dT%H:%M:%S'
def out(s):
    return {'utc':dt.datetime.fromtimestamp(s,dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
def offs(s):
    a=re.fullmatch(r'([+-])(\d\d):(\d\d)',s)
    assert a
    sign,h,m=a.groups()
    return (-1 if sign=='-' else 1)*(int(h)*3600+int(m)*60)
class Arrow:
    name='PyArrow'
    def parse(self,s):return ac.strptime(pa.array([s]),fmt,'s')
    def num(self,x):return ac.cast(x,pa.int64())[0].as_py()
    def named(self,x,z,amb):return ac.assume_timezone(x,z,ambiguous=amb,nonexistent='raise')
    def shifted(self,x,jump,after):
        return ac.subtract(ac.add(x,pa.scalar(jump,pa.duration('s'))),pa.scalar(after,pa.duration('s')))
    def present(self,s,options):return ac.is_in(pa.array([s]),value_set=pa.array(options))[0].as_py()
    def gap(self,x,start,end):
        return ac.and_(ac.greater_equal(x,start),ac.less(x,end))[0].as_py()
class Polars:
    name='Polars'
    def parse(self,s):return pl.Series([s]).str.strptime(pl.Datetime('us'),format=fmt)
    def num(self,x):
        n=x.cast(pl.Int64).item()
        assert n%1000000==0
        return n//1000000
    def named(self,x,z,amb):return x.dt.replace_time_zone(z,ambiguous=amb,non_existent='raise')
    def shifted(self,x,jump,after):return x+dt.timedelta(seconds=jump)-dt.timedelta(seconds=after)
    def present(self,s,options):return pl.Series([s]).is_in(options).item()
    def gap(self,x,start,end):return ((x>=start)&(x<end)).item()
def named(a,x):
    w=a.parse(x['local']);where=x['zone']
    old=a.num(w)
    if x.get('offset') is not None:
        allvals={a.num(a.named(w,where,fold)) for fold in ('earliest','latest')}
        found=[v for v in sorted(allvals) if old-v==offs(x['offset'])]
        return (out(found[0]) if found else {'error':'invalid_offset'}),{
            'possible_utc_and_offset_seconds':[[out(v)['utc'],old-v] for v in sorted(allvals)],
            'named_policy':'select_explicit_offset'}
    mode={'later':'latest','earlier':'earliest',None:'raise'}[x.get('occurrence')]
    try:
        return out(a.num(a.named(w,where,mode))),{'named_policy':mode}
    except (pa.ArrowInvalid,pl.exceptions.ComputeError) as err:
        message=str(err)
        if ' is ambiguous in time' in message or 'Timestamp is ambiguous' in message:
            cat='ambiguous'
        elif 'non-existent' in message or "doesn't exist in timezone" in message:
            cat='nonexistent'
        else:raise
        return {'error':cat},{'named_policy':mode,'native_error_family':type(err).__name__}
def synthetic(a,x):
    w=a.parse(x['local'])
    if 'validOffsets' in x:
        found=a.present(x['claimedOffset'],x['validOffsets'])
        got=(out(a.num(a.shifted(w,0,offs(x['claimedOffset']))))
            if found else {'error':'invalid_offset'})
        return got,{'authored_policy':'offset_set_membership','native_member':bool(found)}
    pat=r'Synthetic zone: at local (\d\d:\d\d) clock advances to (\d\d:\d\d), from ([+-]\d\d:\d\d) to ([+-]\d\d:\d\d)\.'
    early,late,before,after=re.fullmatch(pat,x['timeline']).groups()
    day=x['local'].split('T')[0]
    t=lambda s:a.parse(day+'T'+s+':00')
    start,end=t(early),t(late)
    jump=a.num(end)-a.num(start); assert jump==offs(after)-offs(before)>0
    assert a.gap(w,start,end)
    return out(a.num(a.shifted(w,jump,offs(after)))),{'authored_policy':'add_forward_gap_then_use_new_offset','gap_seconds':jump}
rows=[]
for fixture in json.loads(src.read_bytes()):
    if fixture['class']!='F8':continue
    x=fixture['inputs']
    for adapter in (Arrow(),Polars()):
        val,detail=named(adapter,x) if 'zone' in x else synthetic(adapter,x)
        rows.append(dict(case_id=fixture['case_id'],adapter=adapter.name,
            scope='native_named_timezone' if 'zone' in x else 'native_primitive_with_declared_contract_policy',
            output=val,detail=detail))
assert len(rows)==12 and len({(r['case_id'],r['adapter']) for r in rows})==12
tz=Path('/usr/share/zoneinfo/tzdata.zi')
assert tz.is_file()
print(json.dumps(dict(rows=rows,pyarrow=pa.__version__,polars=pl.__version__,
    host_tzdata_header=tz.read_text().splitlines()[0],host_tzdata_sha256=read(tz)),sort_keys=True,indent=2))
