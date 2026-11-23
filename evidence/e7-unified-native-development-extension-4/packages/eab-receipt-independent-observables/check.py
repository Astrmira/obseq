"""Portable evidence contract. Native R98 receipt snapshots are bound at replay."""
import json,hashlib,re,sys
from pathlib import Path
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf8')
def read(p):return json.loads(Path(p).read_text())
def integer(v):
 assert isinstance(v,str) and re.fullmatch(r'0|-?[1-9][0-9]*',v)
 n=int(v);assert -(2**63)<=n<2**63
 return n
def key(v):return None if v is None else integer(v)
def index(records,k):
 out={}
 for r in records:
  i=k(r)
  if i in out:raise ValueError('duplicate identity')
  out[i]=tuple(r)
 return out
def diff(a,b):
 return {'missing':sorted(a.keys()-b.keys()),'extra':sorted(b.keys()-a.keys()),
 'changed':sorted(k for k in a.keys()&b.keys() if a[k]!=b[k])}
def expect(m):
 after={r[0]:list(r) for r in m['rows']}
 for i,op,k in m['patch']:
  if op!='KEEP':after[i][1]=k
 statuses=[[i,'ok'] for i,_,_ in m['patch']]
 pairs=[[mode,i,j] for mode in m['join_modes'] for i,k,_ in after.values()
        for j,v in m['right'] if key(k)==key(v) and (k is not None or mode=='null_safe')]
 return {'status':statuses,'rows':list(after.values()),'join':pairs}
def validate(contract,manifest,versions,receipt):
 if receipt['schema']!=contract['schema'] or receipt['versions']!=versions:
  raise ValueError('schema/version binding')
 if receipt['digest']!=hashlib.sha256(canon([contract,manifest])).hexdigest():
  raise ValueError('stale manifest binding')
 ops={'status':lambda r:integer(r[0]),'rows':lambda r:(key(r[1]),integer(r[2]),integer(r[0]))[-1],
      'join':lambda r:(r[0],integer(r[1]),integer(r[2]))}
 e=expect(manifest)
 return {stage:diff(index(e[stage],fn),index(receipt[stage],fn)) for stage,fn in ops.items()}
def main():
 contract=read('contract.json');m=read('manifest.json')
 native=read('native.json')
 versions=read('versions.json')
 assert native['versions']==versions
 arms={}
 e=expect(m)
 for name,evidence in native['records'].items():
  for mode in ('typed','default'):
   r=dict(e,**{k:native[k] for k in ("digest","schema","versions")})
   r['status']=evidence['status']
   r['rows']=evidence['rows']
   r['join']=evidence[mode]
   arms[f'{name}-{mode}']=r
 # Deliberately alter only a non-key field in a passing native receipt. This is a protocol test,
 # not a claim the native pipeline unexpectedly changed non-key values.
 good=arms['complete-typed']
 arms['injected-control-only']=dict(good,rows=[[i,k,str(int(c)+1) if i=='1' else c] for i,k,c in good['rows']])
 reports={arm:validate(contract,m,versions,r) for arm,r in arms.items()}
 failed=lambda arm:{s for s,d in reports[arm].items() if any(d.values())}
 assert not failed('complete-typed')
 assert failed('complete-default')=={'join'}
 assert failed('sparse-typed')=={'status'}
 assert failed('injected-control-only')=={'rows'}
 assert failed('normalize-all-typed')=={'rows','join'}
 for field in ('digest','versions'):
  try:validate(contract,m,versions,dict(good,**{field:None}))
  except ValueError:pass
  else:raise AssertionError(field)
 try:validate(contract,m,versions,dict(good,status=good['status']+good['status'][:1]))
 except ValueError:pass
 else:raise AssertionError('duplicate status')
 print(json.dumps(reports,sort_keys=True,indent=2))
if __name__=='__main__':main()
