import json,math
from pathlib import Path
from datetime import datetime
P=Path(__file__).parent
A=json.loads((P/'native-artifacts.json').read_text())
B=json.loads((P/'result.json').read_text())['fixtures']
D={}
for k,value in A.items():
 C=value['artifact'];statuses={}
 for v in C['results']:
  name=v['unique_id'].rsplit('.',1)[-1];statuses[name]=v['status']
  max_at=datetime.fromisoformat(v['max_loaded_at'])
  snapshot=datetime.fromisoformat(v['snapshotted_at'])
  seconds=(snapshot-max_at).total_seconds()
  assert math.isclose(seconds,v['max_loaded_at_time_ago_in_s'],rel_tol=1e-12,abs_tol=1e-6)
  assert ('error' if seconds>3600 else 'warn' if seconds>1800 else 'pass')==v['status']
  if name=='global_max':D[k]=v['max_loaded_at']
 assert statuses==B[k]['status']
 assert (value['returncode']==0)==all(s=='pass' for s in statuses.values())
prefix=['current_both_histogram','B_stalled_same_histogram','B_absent_same_histogram']
assert len({D[k] for k in prefix})==1
print('25 real native nodes and launch return codes verified')
