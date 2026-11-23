import hashlib,json,logging,os,sys,subprocess
from pathlib import Path
os.environ['GX_ANALYTICS_ENABLED']='false'
import great_expectations as gx, pandas as pd, numpy as np
logging.disable(logging.CRITICAL)
assert gx.__version__=='1.25.0'
root=Path(__file__).resolve().parent
p=sys.argv[1:] or ['/tmp/r98-goes.nc','/tmp/r94-20250102.nc']
cxt=gx.get_context(mode='ephemeral')
src=cxt.data_sources.add_pandas('study')
asset=src.add_dataframe_asset('values')
definition=asset.add_batch_definition_whole_dataframe('whole')
def validate(batch,exp):
    result=batch.validate(exp)
    assert not result.exception_info.get('raised_exception',False),result.exception_info
    d=result.result
    return dict(success=result.success,n=int(d['element_count']),
                unexpected=int(d['unexpected_count']),missing=int(d['missing_count']) if 'missing_count' in d else None)
def suite(data,m):
    batch=definition.get_batch(batch_parameters={'dataframe':pd.DataFrame({'packed':data})})
    typ=gx.expectations
    cfg={'column':'packed','result_format':{'result_format':'SUMMARY','partial_unexpected_count':0}}
    return dict(nonnull=validate(batch,typ.ExpectColumnValuesToNotBeNull(**cfg)),
       in_range=validate(batch,typ.ExpectColumnValuesToBeBetween(min_value=m['lo'],max_value=m['hi'],**cfg)))
source_hash=[s.split()[0] for s in (root/'SOURCES.sha256').read_text().splitlines()]
assert len(p)==len(source_hash)==2
out={}
for f,v,sha in zip(p,('BCM','sst'),source_hash):
    with open(f,'rb') as file:assert hashlib.file_digest(file,'sha256').hexdigest()==sha
    binary=subprocess.check_output(['/usr/bin/python3','-IB',str(root/'extract.py'),f,v])
    meta,_,buff=binary.partition(b'\n')
    m=json.loads(meta); a=np.frombuffer(buff,dtype='<i2')
    assert a.size==m['n']
    s=pd.Series(a,dtype='Int16')
    mask=(a==m['fill'])
    assert np.count_nonzero(mask)==m['missing'] and m['missing']>0
    assert not m['observed_range_invalid']
    raw=suite(s,m)
    normalized=s.mask(mask)
    assert np.array_equal(normalized.isna(),mask) and normalized[~mask].equals(s[~mask])
    adapted=suite(normalized,m)
    n,mcount=m['n'],m['missing']
    for r in (raw,adapted):
        assert all(x['n']==n for x in r.values())
    assert raw['nonnull']['success'] and raw['nonnull']['unexpected']==0
    assert not adapted['nonnull']['success'] and adapted['nonnull']['unexpected']==mcount
    assert not raw['in_range']['success'] and raw['in_range']['unexpected']==mcount and raw['in_range']['missing']==0
    assert adapted['in_range']['success'] and adapted['in_range']['unexpected']==0 and adapted['in_range']['missing']==mcount
    out[v]=dict(native_meta=m,raw=raw,source_support_nullable=adapted,strict_complete_scientific_grid=False,
        observed_numeric_domain_valid=True,observed_support=[n-mcount,n])
print(json.dumps(dict(gx=gx.__version__,pandas=pd.__version__,reports=out),sort_keys=True,indent=2))
