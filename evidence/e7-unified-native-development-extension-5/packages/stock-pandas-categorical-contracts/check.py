from pathlib import Path
import hashlib,json,sys
import pandas as pd, numpy as np, pyarrow as pa, pyarrow.parquet as pq, pyarrow.compute as pc
from pandas.testing import assert_frame_equal
source=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/pvl-eab-submission/e4/inputs/2025-11.parquet')
with source.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()=='2cf2f3127f96d4d5dea30f8afe05119cf8e4ba57bd9e60b789d3f296fc8459ab'
assert pd.__version__=='3.1.1' and pa.__version__=='26.0.1'
load=pq.read_table(source,columns=['PULocationID']).column(0).combine_chunks()
assert load.type==pa.int32() and len(load)==4181444
unique=pc.unique(load).to_pylist()
fifo=[x for x in unique if x is not None]; ordered=sorted(fifo)
assert fifo!=ordered
# Independently generate a dictionary rank array from exact ints.
flat=pc.fill_null(load,pa.scalar(-1,type=pa.int32())).to_numpy()
assert -1 not in ordered and min(ordered)>=0
def codes(order):
    indexes=np.full(max(order)+2,-1,dtype=np.int16)
    indexes[1+np.array(order)]=np.arange(len(order))
    out=indexes[flat+1];assert np.count_nonzero(out<0)==load.null_count
    return out
def frame(order,mode):
    values=pd.arrays.IntegerArray(flat.copy(),flat==-1)
    return pd.DataFrame({'z':pd.Categorical(values,categories=np.array(order,dtype=np.int32),ordered=mode)})
def accepted(a,b,**kw):
    try:assert_frame_equal(a,b,**kw)
    except AssertionError:return False
    return True
def pair(mode):
    A,B=frame(ordered,mode),frame(fifo,mode)
    ca,cb=(x['z'].cat.codes.to_numpy() for x in (A,B))
    aa,bb=codes(ordered),codes(fifo)
    assert np.array_equal(ca,aa) and np.array_equal(cb,bb)
    # Hold semantic row order, type and mask fixed while testing layout.
    ar=[pa.DictionaryArray.from_arrays(pa.array(c,mask=c<0,type=pa.int16()),pa.array(order,type=pa.int32()),ordered=mode)
        for c,order in ((ca,ordered),(cb,fifo))]
    assert all(x.dictionary_decode().equals(load) for x in ar)
    unchanged=accepted(A,A.copy(deep=True)) and A.equals(A.copy(deep=True))
    assert unchanged
    q=dict(equals=A.equals(B),default=accepted(A,B),dtype_false_only=accepted(A,B,check_dtype=False),
          exact_default_categories=accepted(A,B,check_exact=True),
          categorical_false_only=accepted(A,B,check_categorical=False),
          dtype_and_categorical_false=accepted(A,B,check_dtype=False,check_categorical=False),
          raw_arrow_dictionary_equal=ar[0].equals(ar[1]),arrow_decoded_equal=True)
    miss=(ca!=cb)
    wrong=np.zeros(len(flat),dtype=bool)
    support=cb>=0
    wrong[support]=np.array(ordered)[cb[support]]!=flat[support]
    assert np.array_equal(miss,wrong)
    lookup={label:i for i,label in enumerate(ordered)}
    permutation=np.array([lookup[label] for label in fifo],dtype=np.int16)
    assert np.array_equal(permutation[cb[support]],ca[support])
    q['rows_recoded']=int(miss.sum())
    q['old_codebook_misdecodes_new_rows']=int(wrong.sum())
    q['category_rank_diff']=sum(a!=b for a,b in zip(ordered,fifo))
    if mode:q['native_ordered_min_diff']=bool(A['z'].min()!=B['z'].min())
    return q
u,o=pair(False),pair(True)
assert u['equals'] and not u['default'] and u['categorical_false_only']
assert not o['equals'] and not o['default'] and o['categorical_false_only'] and o['native_ordered_min_diff']
assert o['dtype_and_categorical_false'] and not u['raw_arrow_dictionary_equal'] and not o['raw_arrow_dictionary_equal']
assert u['rows_recoded']==o['rows_recoded']>0
print(json.dumps(dict(pandas=pd.__version__,arrow=pa.__version__,rows=len(load),
    observed_zone_ids=len(ordered),missing_zone=len(load)-sum(flat!=-1).item(),
    unordered=u,ordered=o),sort_keys=True,indent=2))
