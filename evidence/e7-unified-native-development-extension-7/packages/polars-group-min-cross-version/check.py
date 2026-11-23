import json
from collections import defaultdict
values=['A','a','a','B']
groups=defaultdict(list)
for x in values:groups[x.lower()].append(x)
expected=sorted([min(a),len(a)] for a in groups.values())
assert expected==[['A',3],['B',1]]
for f,v in [('e5','1.31.0'),('e1','1.35.2'),('e4','2.1.0')]:
 d=json.load(open(f+'.json'));assert d['polars']==v
 r=d['results']
 for k in ('target','min_alias_only','count_alias_only','aggregate_alias','named_subquery'):assert r[k]['sqlite']==expected
 for k in ('min_alias_only','aggregate_alias','named_subquery'):assert r[k]['polars']==expected
 if v=='1.31.0':assert r['target']['polars']['error']=='SQLSyntaxError' and r['count_alias_only']['polars']['error']=='SQLSyntaxError'
 elif v=='1.35.2':
  assert r['target']['polars']==r['count_alias_only']['polars']==[['a',1],['a',3]]
  assert '[len()] BY' in r['target']['polars_plan'] and '.min().alias("lo")' in r['min_alias_only']['polars_plan']
 else:assert r['target']['polars']==r['count_alias_only']['polars']==expected
print('Independent ASCII exact oracle and three pinned observations verified.')
