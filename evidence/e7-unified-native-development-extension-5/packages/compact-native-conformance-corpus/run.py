from os import environ
import collections,hashlib,itertools,json,pathlib,subprocess,sys,tempfile
HERE=pathlib.Path(__file__).resolve().parent
def compact(x):return json.dumps(x,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(compact(x).encode()).hexdigest()
def grid(r):
 x,y,w,h=r
 assert x<w and y<h and all(type(i)==int for i in r)
 return {(i,j) for i in range(x,w) for j in range(y,h)}
def oracle(case):
 inputs=case['inputs'];assert len({r[0] for r in inputs})==len(inputs)
 assert inputs==sorted(inputs)
 if case['route']=='gpkg_overlap':
  R=grid(case['region'])
  scores=[[i,len(grid(r)&R)] for i,r in inputs]
  outputs={tuple(i for i,k in scores if k>=case['threshold'])}
 else:
  values={i:b+case['epoch']*s for i,g,b,s in inputs}
  scores=sorted(map(list,values.items()));families=[]
  groups=collections.defaultdict(list)
  for i,g,b,s in inputs:groups[str(g)].append(i)
  assert set(groups)==set(case['quotas'])
  for g,ids in sorted(groups.items()):
   k=case['quotas'][g];assert 0<=k<=len(ids)
   cutoff_scores=sorted((values[i] for i in ids),reverse=True)[:k]
   families.append([ss for ss in itertools.combinations(ids,k)
       if sorted((values[i] for i in ss),reverse=True)==cutoff_scores])
  outputs={tuple(sorted(itertools.chain.from_iterable(a))) for a in itertools.product(*families)}
 return scores,outputs
def native(case,mode):
 geo=case['route']=='gpkg_overlap'
 exe=environ.get('OBSEQ_SYSTEM_PYTHON', '/usr/bin/python3') if geo else sys.executable
 script=HERE/('spatial.py' if geo else 'rank.py')
 return json.loads(subprocess.check_output([exe,'-IB',str(script)],input=compact([case,mode]),text=True))
def audit(case,mode):
 expected,allowed=oracle(case);obs=native(case,mode)
 return {'case':case['id'],'mode':mode,'contract_hash':digest(case),'source_hash':digest(obs['input']),
   'versions':obs['versions'],'gates':{'artifact':obs['input']==case['inputs'],
     'derived':obs['scores']==expected,'output':tuple(sorted(obs['ids'])) in allowed},
   'selected':sorted(obs['ids']),'scores':obs['scores']}

def publish(receipts,path):
 # Retain failure evidence but do not replace the prior acceptance of the batch.
 if not all(all(r['gates'].values()) for r in receipts):return False
 staged=path.with_suffix('.tmp');staged.write_text(compact(receipts));staged.replace(path);return True
def main():
 manifest=json.loads((HERE/'manifest.json').read_text());assert manifest['schema']=='eab-compact/v1'
 dev=manifest['splits']['development'];hold=manifest['splits']['held_out']
 assert {v['id'] for v in dev}.isdisjoint(v['id'] for v in hold)
 calibration=[audit(c,'correct') for c in dev]
 assert all(all(r['gates'].values()) for r in calibration)
 with tempfile.TemporaryDirectory() as d:
  path=pathlib.Path(d)/'accepted.json';path.write_bytes(b'prior receipt')
  mix=[audit(c,'default' if c['route']=='xlsx_rank' else 'correct') for c in hold]
  assert not publish(mix,path) and path.read_bytes()==b'prior receipt'
  all_current=[audit(c,'correct') for c in hold]
  assert publish(all_current,path)
  assert json.loads(path.read_text())==all_current
  defaults=[audit(c,'default') for c in hold]
  assert all(not r['gates']['derived'] for r in defaults)
  print(json.dumps({'manifest_hash':digest(manifest),'development':calibration,'held_out':{
    'all_current':all_current,'all_default':defaults,'mixed':mix},
    'publication':{'mixed_preserved_prior':True,'all_current_committed':True}},indent=2,sort_keys=True))
if __name__=='__main__':main()
