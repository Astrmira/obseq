import argparse,hashlib,json,os,subprocess,sys,tempfile
from collections import Counter
from pathlib import Path
CASES='b7421e79d5488b7faa9dee89c606750e9471cebc687852ba7534872a3059fa0b'
LABELS='fe1f3be17999c0c4cc982d37ffe1b1a0288891331cd60721f8b2196ca5a0c96a'
def pin(p,h):
    b=p.read_bytes();assert hashlib.sha256(b).hexdigest()==h
    return json.loads(b)
def run(a):
    cases=pin(a.cases,CASES); labels={d['id']:d['legal'] for d in pin(a.labels,LABELS)}
    assert len(cases)==len(labels)==24
    decisions=[]
    with tempfile.TemporaryDirectory(prefix='eab-dvc-',dir=a.scratch) as name:
        d=Path(name);home=d/'home';home.mkdir()
        env=os.environ|{'PYTHONPATH':str(a.site.resolve()),'DVC_NO_ANALYTICS':'1','HOME':str(home),'XDG_CONFIG_HOME':str(home),'XDG_CACHE_HOME':str(home)}
        def dvc(*args):
            return subprocess.run([sys.executable,'-B','-m','dvc',*args],cwd=d,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                  text=True,check=True,timeout=30).stdout
        assert dvc('--version').strip()=='3.66.1'
        dvc('init','--no-scm')
        dvc('config','cache.type','copy')
        file=d/'payload.jsonl'
        def record(rows):
            data=''.join(json.dumps(row,separators=(',',':'),ensure_ascii=True)+'\n' for row in rows).encode()
            tmp=d/'next';tmp.write_bytes(data);tmp.replace(file)
            dvc('add','payload.jsonl')
            # Native DVC with pinned dependencies writes YAML pointer. Parse as YAML,
            # never substitute a reimplemented fingerprint for the native value.
            v=subprocess.run([sys.executable,'-B','-c',"""import json, yaml; print(json.dumps(yaml.safe_load(open('payload.jsonl.dvc'))['outs'][0]))"""],
                cwd=d,env=env,stdout=subprocess.PIPE,text=True,check=True).stdout
            h=json.loads(v)
            assert h['path']=='payload.jsonl' and h['hash']=='md5'
            assert h['size']==len(data) and h['md5']==hashlib.md5(data).hexdigest()
            return h['md5']
        for case in cases:
            i=case['id'];x=record(case['source']);y=record(case['candidate'])
            got=(x==y)
            decisions.append(dict(id=i,legal=labels[i],native_same_file_hash=got))
    count=Counter(('TP' if x['legal'] else 'FP') if x['native_same_file_hash'] else ('FN' if x['legal'] else 'TN') for x in decisions)
    return dict(tool='DVC 3.66.1',cases=len(decisions),scored=count,decision=decisions)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('cases','labels','site','scratch'):p.add_argument(k,type=Path)
    print(json.dumps(run(p.parse_args()),sort_keys=True,indent=2))
