"""Replay scored sources, keeping development, transfer, and blinded splits distinct."""
import argparse, hashlib,json, pathlib,re,subprocess,sys
p=argparse.ArgumentParser()
for name in ['six_root','pg_bin','compact','wkb','old_cases']:p.add_argument(name,type=pathlib.Path)
a=p.parse_args()
here=pathlib.Path(__file__).resolve().parent
pins=json.loads((here/'SOURCE-PINS.json').read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def protect(path,expected):
 if not path.is_file() or path.is_symlink() or sha(path)!=expected:raise ValueError(f'pin mismatch: {path}')
def replay(folder,exe,args,expected=None):
 out=subprocess.check_output([exe,'-IB',*map(str,args)],cwd=folder,timeout=480)
 if expected is not None and out!=(folder/expected).read_bytes():raise ValueError(f'replay mismatch: {expected}')
 return out
for key,expected in pins.items():
 if key.startswith('compact:'):protect(a.compact/key.split(':')[1],expected)
manifest=a.wkb/'SHA256SUMS';protect(manifest,pins['wkb-manifest'])
for line in manifest.read_text().splitlines():
 match=re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)',line)
 if not match:raise ValueError('malformed manifest')
 h,n=match.groups();protect(a.wkb/n,h)
old=a.wkb.resolve().parent/'e7-scored'
protect(old/'SHA256SUMS',pins['old-manifest'])
for line in (old/'SHA256SUMS').read_text().splitlines():
 h,n=line.split('  ');protect(old/n,h)
protect(a.old_cases,pins['old-cases'])
replay(old,sys.executable,['check.py','BLIND.json'],'PREDICTIONS.json')
# This scorer also writes an identical CSV; work on a disposable copy.
import shutil,tempfile
with tempfile.TemporaryDirectory() as t:
 copy=pathlib.Path(t)/'e7-scored';shutil.copytree(old,copy)
 replay(copy,sys.executable,['score.py',a.old_cases.resolve()],'SCORES.json')
scores=json.loads((old/'SCORES.json').read_bytes())
strata={k:v for k,v in scores['strata'].items() if k.startswith('F') and '/' not in k or k.startswith(('O3/','O4/'))}
assert len(strata)==18 and all(v['cases']>=5 and v['match']==v['cases'] for v in strata.values())
six=replay(here,sys.executable,['six.py',a.six_root.resolve(),a.pg_bin.resolve()])
assert hashlib.sha256(six).hexdigest()==pins['six']
replay(a.wkb,'/usr/bin/python3',['parser.py'],'MEASURED.json')
replay(a.wkb,sys.executable,['score.py'],'SCORES.json')
compact=json.loads(replay(a.compact,sys.executable,['run.py'],'result.json'))
# These support counts are conservative at the level of the frozen contract.
# Ambiguous cross-labels stay out; counts within overlapping rows do not add.
coverage={
 'F1':(0,'No int64 loss contract'), 'F2':(0,'JSON absence is not null join semantics'),
 'F3':(0,'No independently sealed stale snapshot'), 'F4':(0,'Cache controls in transfer only'),
 'F5':(24,'ordered writes: explicit KEEP/CLEAR/WRITE contract'),
 'F6':(8,'group role/fold: finite peer-band membership with producer role'),
 'F7':(24,'keyed aggregate cancellation'), 'F8':(10,'group role/fold: finite paired fold contract'),
 'F9':(0,'Tuple representative is not SQL storage-type drift'),
 'F10':(0,'Orientation is not invalid repair or precision-grid mutation'),
 'O3 LIMIT/top-k ties':(0,'upper bound: group-role cohort has mixed LIMIT, RANK and DENSE_RANK'),
 'O3 ROW_NUMBER ties':(0,'No exact ROW_NUMBER-labeled panel'),
 'O3 coupled choices':(24,'coherent group tuples; overlaps representatives'),
 'O3 GROUP BY representatives':(24,'coherent group tuples'),
 'O4 WKB union order':(0,'Scored binary WKB envelope is not a union-order panel'),
 'O4 numeric text':(0,'Orientation decimal-vs-binary is not tested as numerical spelling equivalence'),
 'O4 Excel serial':(0,'Original-reader E4 observed data, not an independently sealed E7 panel'),
 'O4 geometry point-set equality':(0,'WKB has narrow typed 2D shape/span, not general point-set equivalence'),
}
print(json.dumps(dict(interface='E7-pinned-integration-1', independent_six=json.loads(six),
 narrow_independent_WKB={'cases':6,'case_channels':12,'expected':'SCORES.json','neutral_scope':'WKB wire encoding and typed shape/span; existing published scored labels'},
 compact_author_transfer_receipts={k:len(v) for k,v in compact.items() if isinstance(v,list)},
 original_independent_interpreter={'overall':scores['overall'],'coverage':strata},
 newer_six_panel_only_taxonomy={k:dict(eligible_cases=n,meets_five=n>=5,scope=s) for k,(n,s) in coverage.items()},
 ),indent=2,sort_keys=True))
