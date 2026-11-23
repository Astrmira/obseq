"""Verify pinned inputs and rerun five fixed native evidence adapters."""
import argparse, hashlib, json, re, subprocess, sys, tempfile
from pathlib import Path
PANELS=(
 ('heldout-group-role-and-fold-joint','O3 group provenance / O2 civil time','inputs.json','PREDICTIONS.json','RESULT.json',18,('DuckDB',)),
 ('heldout-json-presence-and-path-shape','typed JSON presence and path','CASES.json','PREDICTIONS.json','RESULT.json',24,('DuckDB','PostgreSQL','SQLite')),
 ('heldout-coherent-group-representatives','O3 coherent representative','CASES.json','PREDICTIONS.json','RESULT.json',24,('DuckDB','PostgreSQL','SQLite')),
 ('heldout-binary64-orientation','O4 binary64 orientation','CASES.json','PREDICTIONS.json','RESULT.json',24,('GEOS and certified predicate',)),
 ('heldout-ordered-intervention-receipts','O5 committed ordered writes','CASES.json','OBSERVED.json','SCORES.json',24,('DuckDB','SQLite')),
 ('heldout-keyed-aggregate-cancellation','F7 keyed aggregate cancellation','CASES.json','OBSERVED.json','SCORES.json',24,('DuckDB','SQLite')),
)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def protect(path,hashsum):
    if path.is_symlink() or not path.is_file() or sha(path)!=hashsum:
        raise RuntimeError(f'integrity check: {path.parent.name}/{path.name}')
def replay(d,cmd,expected):
    got=subprocess.run([sys.executable,'-B',*map(str,cmd)],cwd=d,
        stdout=subprocess.PIPE,check=True,timeout=180).stdout
    if got!=(d/expected).read_bytes(): raise RuntimeError(f'sealed output mismatch: {d.name}/{expected}')
def main():
    p=argparse.ArgumentParser()
    p.add_argument('semantic_evidence',type=Path)
    p.add_argument('pg_bin',type=Path)
    args=p.parse_args()
    base=args.semantic_evidence.resolve(strict=True)
    pg=args.pg_bin.resolve(strict=True)
    if not all((pg/n).is_file() for n in ('postgres','initdb')): p.error('PostgreSQL initdb and postgres required')
    locks=json.loads(Path(__file__).with_name('SOURCE-MANIFESTS.json').read_text())
    assert set(locks)=={x[0] for x in PANELS}
    for slug,*_ in PANELS:
        d=base/slug
        if d.is_symlink(): raise RuntimeError(f'symlink: {slug}')
        manifest=d/'SHA256SUMS'
        protect(manifest,locks[slug])
        for line in manifest.read_text().splitlines():
            if not re.fullmatch(r'[0-9a-f]{64}  [A-Za-z0-9_.-]+',line): raise RuntimeError('invalid trusted manifest syntax')
            h,n=line.split('  ')
            protect(d/n,h)
    rows=[]
    with tempfile.TemporaryDirectory(prefix='eab-replay-') as scratch:
        for slug,scope,src,pred,scores,n,engines in PANELS:
            d=base/slug
            if len(engines)==3:
                replay(d,['run.py',src,pg,scratch],pred)
            elif slug.endswith('orientation'):
                replay(d,['run.py',src],pred)
            elif slug.endswith(('intervention-receipts','aggregate-cancellation')):
                replay(d,['check.py',src],pred)
            else:
                replay(d,['check.py'],pred)
                replay(d,['oracle.py'],'labels.json')
            replay(d,['score.py'],scores)
            rows.append(dict(panel=slug,scope=scope,authored_cases=n,channels=engines,case_channels=n*len(engines),
                input_sha256=sha(d/src),prediction_sha256=sha(d/pred),adjudication_sha256=sha(d/scores)))
    print(json.dumps(dict(interface='eab-independent-suite-2',panels=rows,authored_cases=sum(r['authored_cases'] for r in rows),
        case_channels=sum(r['case_channels'] for r in rows)),sort_keys=True,indent=2))
if __name__=='__main__': main()
