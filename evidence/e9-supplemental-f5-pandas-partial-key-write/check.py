import sys,json
import pandas as pd,numpy as np
assert pd.__version__ == sys.argv[1] and np.__version__ == '2.3.5'
def data():
    return pd.DataFrame([0,1,2],columns=pd.MultiIndex.from_tuples([('A','B')]))
def observe(s):
    return [None if pd.isna(x) else float(x) for x in s.array]
def projection(f,key):
    return observe(f[key].iloc[:,0] if isinstance(f[key],pd.DataFrame) else f[key])
want=[None,.5,1.5]
f=data()
expected_rhs=f['A'].rolling(2).mean()
assert observe(expected_rhs.iloc[:,0]) == want
f['C']=expected_rhs
first=projection(f,'C')
f['C']=expected_rhs
repeat=projection(f,'C')
f[('C','')]=expected_rhs
qualified=projection(f,('C',''))
keep=projection(f,('A','B'))
assert first == qualified == want and keep == [0.,1.,2.]
assert f.columns.to_list() == [('A','B'),('C','')]
assert repeat == (want if pd.__version__ == '3.0.0' else [None,None,None])
print(json.dumps({'pandas':pd.__version__,'numpy':np.__version__,'rhs_value_contract':want,'first_assignment':first,
 'same_assignment_repeated':repeat,'qualified_tuple_control':qualified,'source_keep_control':keep,
 'output_column_keys':f.columns.to_list(),'off_frozen_roster':True},sort_keys=True))
