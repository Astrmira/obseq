"""Replay two independent ratings and optional third adjudication."""
import csv,hashlib,json,re
from fractions import Fraction as Q
from collections import Counter
from pathlib import Path
D=Path(__file__).parent
def pinned(name,h):
    b=(D/name).read_bytes()
    assert hashlib.sha256(b).hexdigest()==h,name
    return b.decode()
def lines(name,h):
    return {r['id']:r for r in map(json.loads,pinned(name,h).splitlines())}
def kappa(A,B):
    assert len(A)==len(B)
    n=len(A)
    a,b=map(Counter,(A,B))
    o=Q(sum(x==y for x,y in zip(A,B)),n)
    e=Q(sum(a[k]*b[k] for k in a.keys()|b.keys()),n*n)
    k=(o-e)/(1-e) if e!=1 else None
    return dict(paired=n,agreement_count=o*n,kappa=str(k) if k is not None else None,kappa_decimal=float(k) if k is not None else None,
                matrix=[dict(a=x,b=y,count=n) for (x,y),n in sorted(Counter(zip(A,B)).items())])
def freeze(r):
    v=r['wrong_result']
    assert v in ('yes','no','unknown')
    if v=='yes':
        assert r['class'] in {f'F{i}' for i in range(1,11)}|{'O3','O4','other','unknown'}
        return v,r['class']
    return v,'other' if v=='no' else 'unknown'
def main():
    r=list(csv.DictReader(pinned('ROSTER.csv','057b0c7256bea60b1da76462e76654d0c978ef950699c11ae7eb9cd8e990383f').splitlines()))
    audit={x['id']:x for x in csv.DictReader(pinned('STRATA.csv','97fe54069f892d2e59b78ed8726ff645eeb41246958e11cc4cf95ffccfad5e70').splitlines())}
    a=lines('RATER-A.jsonl','f2f4c72307c17205181f0382778bacc285d115c63a5aa34619dfff7fbc3000ef')
    b=lines('RATER-B.jsonl','1b163e3392c0bd39e2641c7c75c067f5ec63b922fddc359abafb9bcd66481a4a')
    names=[q['id'] for q in r]
    assert len(names)==300 and set(names)==set(a)==set(b)==set(audit)
    T=[(i,freeze(a[i]),freeze(b[i])) for i in names]
    matches={i for i,x,y in T if x==y}
    assert len(matches)==272
    s=kappa([x[0] for i,x,y in T],[y[0] for i,x,y in T])
    c=kappa([':'.join(x) for i,x,y in T],[':'.join(y) for i,x,y in T])
    yy=[(x[1],y[1]) for i,x,y in T if x[0]==y[0]=='yes']
    b2=kappa([x for x,y in yy],[y for x,y in yy])
    out=dict(wrong_result=s,joint_wrong_result_and_class=c,class_given_both_yes=b2,adjudication_needed=len(names)-len(matches))
    adj=D/'ADJUDICATED.jsonl'
    if adj.exists():
        cases={r['id']:r for r in map(json.loads,adj.read_text(encoding='utf-8').splitlines())}
        assert set(cases)==set(names)-matches and len(cases)==28
    else: cases={}
    fit=Counter(); class_counts=Counter(); per=Counter()
    joint_fixes=[]
    for i,x,y in T:
        if i not in matches and i not in cases: continue
        w,k=x if i in matches else freeze(cases[i])
        fit[w]+=1
        per[audit[i]['tracker'],w]+=1
        if w=='yes':
            class_counts[k]+=1
            rx=r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+'
            f1,f2=(set(re.findall(rx,r['fix_status'])) for r in (a[i],b[i]))
            if 'merged' in a[i]['fix_status'].lower() and 'merged' in b[i]['fix_status'].lower() and f1&f2:
                joint_fixes.append(i)
    out['adjudicated']={'status':fit,'yes_class':class_counts,'by_tracker':[dict(tracker=x,status=y,n=z) for (x,y),z in sorted(per.items())],
                        'yes_both_named_same_merged_pr':len(joint_fixes),'reviewed_rows':sum(fit.values())}
    for d in (s,c,b2): d['agreement_count']=int(d['agreement_count'])
    print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__':main()
