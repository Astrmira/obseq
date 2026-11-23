"""Complement the fixed prefix SQLite arm with one first-KEEP source boundary."""
import json,sys
from pathlib import Path
import numpy as np,pyarrow.compute as pc,pyarrow.parquet as pq
from check import COL,S,metrics,native_sqlite
p=Path(sys.argv[1])
x=pc.fill_null(pq.read_table(p,columns=[COL]).column(0).combine_chunks(),S).to_numpy()
[first,*_]=np.flatnonzero(x==S)
assert first>4 and first+7<len(x) and x[first-1]!=S
a=x[first-5:first+7]; b=x[first-4:first+8]
z=metrics(b,a); assert z['keep'] and z['keep_prior_has_value']
assert all(z[k]==n for k,n in native_sqlite(a,b).items())
print(json.dumps(z,indent=2,sort_keys=True))
