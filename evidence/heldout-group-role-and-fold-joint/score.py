"""Only scoring opens the separately hashed oracle labels."""
from pathlib import Path
import json
from collections import Counter
R=Path(__file__).resolve().parent
def row(x):return json.dumps(x,separators=(',',':'))
def bags(x):return {tuple(sorted(map(row,z))) for z in x}
def rows(x):return set(map(row,x))
C=json.loads((R/'PREDICTIONS.json').read_text())
L=json.loads((R/'labels.json').read_text())
assert len(C)==len(L)==len({x['id'] for x in C}) and set(L)=={x['id'] for x in C}
z=[]
for p in C:
 i=p['id'];truth=L[i]
 if p['family']=='group':
  ok=(bags(p['full'])==bags(truth['role_bags']) and
      bags(p['projected'])==bags(truth['projected_bags']))
  z.append(dict(id=i,family=p['family'],candidate_complete_family_correct=ok,
    naive_nullness_family_correct=bags(p['rendered_null_mask_full'])==bags(truth['role_bags']),
    provenance_ambiguous_after_projection=len(bags(p['full']))>len(bags(p['projected']))))
 else:
  fields=(('start','start_utc'),('end','end_utc'),('joint','joint'),('durations','durations'),
          ('observed_matches','matching_observation'))
  ok=all(rows(p[a])==rows(truth[b]) for a,b in fields)
  z.append(dict(id=i,family=p['family'],candidate_complete_family_correct=ok,
    earliest_default_joint_complete=rows(p['earliest_only'])==rows(truth['joint']),
    observed_duration_multiple_instant_pairs=len(rows(truth['matching_observation']))>1,
    physical_pairs=len(rows(truth['joint']))))
summ={'sealed_cases':len(z),'exact_candidate_matches':sum(r['candidate_complete_family_correct'] for r in z),
      'nullness_shortcut_exact_family_matches':sum(r.get('naive_nullness_family_correct',False) for r in z),
      'group_cases':sum(r['family']=='group' for r in z),
      'marginal_earliest_exact_joint_family_matches':sum(r.get('earliest_default_joint_complete',False) for r in z),
      'paired_time_cases':sum(r['family']=='paired_civil' for r in z),
      'projection_has_fewer_legal_bags':sum(r.get('provenance_ambiguous_after_projection',False) for r in z),
      'duration_fiber_multiple_instant_pairs':sum(r.get('observed_duration_multiple_instant_pairs',False) for r in z)}
print(json.dumps({'cases':z,'summary':summ},indent=2,sort_keys=True))
