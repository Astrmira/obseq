"""Independent contract interpreter for the frozen fixture schemas, not a SQL engine."""
import json, re, struct, math
from collections import Counter, defaultdict
from fractions import Fraction as F
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import argparse

def freeze(x):
    if isinstance(x,list): return ('list',tuple(map(freeze,x)))
    if isinstance(x,dict): return ('dict',tuple((k,freeze(v)) for k,v in sorted(x.items())))
    return (type(x).__name__,x)

def eq(x,y): return freeze(x)==freeze(y)
def bag(x): return Counter(map(freeze,x))
def rat(x):
    s=str(x)
    if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',s):
        raise ValueError('non-decimal')
    return F(s)
def latest(pairs,t):
    return max(((v,w) for v,w in pairs if v<=t),key=lambda o:o[0],default=(None,None))[1]
def cmp_top(rows,ids,n,key=lambda r:r[1],descending=False):
    D={r[0]:r for r in rows}
    return len(ids)==n and len(set(ids))==n and all(i in D for i in ids) and sorted(key(D[i]) for i in ids)==sorted(sorted(map(key,rows),reverse=descending)[:n])
def normalize_dt(t): return datetime.fromisoformat(t.replace('Z','+00:00'))
def offset(s):
    assert re.fullmatch(r'[+-]\d\d:\d\d',s)
    h,m=map(int,s[1:].split(':'))
    return (1 if s[0]=='+' else -1)*timedelta(hours=h,minutes=m)
def walls(x):
    w=datetime.fromisoformat(x['local'])
    if 'timeline' in x:
        a,b,c,d=re.fullmatch(r'Synthetic zone: at local (\d\d:\d\d) clock advances to (\d\d:\d\d), from ([+-]\d\d:\d\d) to ([+-]\d\d:\d\d)\.',x['timeline']).groups()
        before=datetime.fromisoformat(w.date().isoformat()+'T'+a)
        after=datetime.fromisoformat(w.date().isoformat()+'T'+b)
        if not before<=w<after: raise NotImplementedError('synthetic fixture is specified only inside this forward gap')
        assert after-before==offset(d)-offset(c)
        return (w+(after-before)-offset(d)).replace(tzinfo=timezone.utc)
    if 'validOffsets' in x:
        s=x['claimedOffset']
        return 'invalid_offset' if s not in x['validOffsets'] else (w-offset(s)).replace(tzinfo=timezone.utc)
    z=ZoneInfo(x['zone']); choices={}
    for fold in range(2):
        a=w.replace(tzinfo=z,fold=fold)
        u=a.astimezone(timezone.utc)
        if u.astimezone(z).replace(tzinfo=None)==w: choices[u]=a.utcoffset()
    if not choices:return 'nonexistent'
    if x.get('offset') is not None:
        choices={u:o for u,o in choices.items() if o==offset(x['offset'])}
        if not choices:return 'invalid_offset'
    if x.get('occurrence')=='later':return max(choices)
    if x.get('occurrence')=='earlier':return min(choices)
    if len(choices)>1:return 'ambiguous'
    return next(iter(choices))

def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def on(a,b,p):return cross(a,b,p)==0 and all(min(a[i],b[i])<=p[i]<=max(a[i],b[i]) for i in range(2))
def meet(a,b,c,d):
    return any(on(x,y,p) for x,y,p in [(a,b,c),(a,b,d),(c,d,a),(c,d,b)]) or (cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0)
def polygon(ring,p):
    hit=False
    for a,b in zip(ring,ring[1:]+ring[:1]):
        if on(a,b,p):return 0
        if (a[1]>p[1])!=(b[1]>p[1]):
            xx=F(b[0]-a[0],b[1]-a[1])*(p[1]-a[1])+a[0]
            if xx>p[0]:hit=not hit
    return 1 if hit else -1

def wkb(h):
    b=bytes.fromhex(h)
    if len(b)<5 or b[0] not in (0,1):raise ValueError('bad WKB header')
    order='<' if b[0] else '>'
    typ,=struct.unpack_from(order+'I',b,1)
    if typ==1:
        if len(b)!=21:raise ValueError('invalid Point length')
        p=struct.unpack_from(order+'dd',b,5)
        if not all(map(math.isfinite,p)):raise ValueError('nonfinite point not covered')
        return (typ,p)
    if typ in (2,4):
        if len(b)<9:raise ValueError('invalid geometry length')
        n,=struct.unpack_from(order+'I',b,5)
        if typ==4 and n!=0:raise NotImplementedError('nonempty MultiPoint WKB')
        if len(b)!=9+16*n:raise ValueError('invalid coordinate count')
        coords=struct.unpack_from(order+'d'*(2*n),b,9)
        if not all(map(math.isfinite,coords)):raise ValueError('nonfinite coordinates')
        return typ,tuple(zip(coords[::2],coords[1::2]))
    raise NotImplementedError('WKB type not covered')
def date_serial(x,v):
    if 'referenceDate' in x:
        dst=date.fromisoformat(x['referenceDate'])
        sys=x.get('system')
        if sys=='1900-compat':
            n=(dst-date(1899,12,31)).days+(dst>=date(1900,3,1))
        elif sys=='1904':n=(dst-date(1904,1,1)).days
        else:n=(dst-date.fromisoformat(x['epoch'])).days
        return rat(v)==n
    dt=normalize_dt(x['reference'])-normalize_dt(x['epoch'])
    micros=((dt.days*86400+dt.seconds)*1000000+dt.microseconds)
    return rat(v)==F(micros,86400*1000000)
def rows_number(rows,nums,part,key,keep=lambda r:True):
    P=defaultdict(list)
    for r in rows:P[part(r)].append(r)
    remaining=dict(nums)
    for R in P.values():
        grouped=defaultdict(list)
        for r in R:grouped[key(r)].append(r)
        first=1
        for value in sorted(grouped):
            block=grouped[value]
            seen=[]
            for r in block:
                if keep(r):
                    if r[0] not in remaining:return False
                    seen.append(remaining.pop(r[0]))
            if len(seen)!=len(set(seen)) or any(type(i) is not int or not first<=i<first+len(block) for i in seen):
                return False
            first+=len(block)
    return not remaining

def legal(r):
    c,x,s=r['candidate'],r['inputs'],r['contract']
    cls=r['class']
    if cls=='F1':
        if 'match' in c:return c['match'] == (int(x['left'])==int(x['right']))
        if 'value' in c:return int(c['value'])==int(x['R'])
        if 'groups' in c:return c['groups']==len(set(map(int,x['tokens'])))
        if 'integer' in c:return int(c['integer'])==int(x['token'])
        if 'max' in c:return int(c['max'])==max(map(int,x['keys']))
        if 'difference' in c:return int(c['difference'])==int(x['end'])-int(x['start'])
    if cls=='F2':
        if 'equal' in c:return c['equal']==eq(x['left'],x['right'])
        if 'pairs' in c:
            pairs=[]
            for l,*a in x['left']:
                matches=[[l,rr] for rr,*b in x['right'] if ('NULL-safe' in s or None not in a+b) and eq(a,b)]
                pairs.extend(matches or ([[l,None]] if 'outer' in s else []))
            return bag(c['pairs'])==bag(pairs)
    if cls=='F3':
        if 'history' in x:return c['present']==(latest(x['history'],x['s']) is not None)
        if 'revisions' in x:return eq(c['balance'],latest(x['revisions'],x['s']))
        if 'events' in x:
            active=set()
            for ts,i,op in sorted(x['events']):
                if ts<=int(re.search(r'commit ([0-9]+)',s)[1]):
                    if op=='insert':active.add(i)
                    elif op=='delete':active.discard(i)
                    else:raise NotImplementedError('unknown operation')
            return c['active']==len(active)
        if 'versions' in x:return eq(c,latest(x['versions'],x['s']))
        if 'writes' in x:return eq(c['value'],latest([(v['commit'],v['v']) for v in x['writes']],x['s']))
        if 'commits' in x:return eq(c['values'],[latest(x['commits'],x['start']) for _ in x['readTimes']])
    if cls=='F4':
        if 'changes' in x:
            q=x['prior']|x['changes'];return c['subtotal']==q['units']*q['price']
        if 'delete' in x:
            y=[v for k,v in x['prior'] if k!=x['delete']];return rat(c['mean'])==F(sum(y),len(y))
        if 'rename' in x:
            k,v=x['rename'];d=dict(x['prior']);d[k]=v
            return bag(c['ids'])==bag([i for i,j in d.items() if j.lower()==x['lookup']])
        if 'patch' in x:
            q=x['before']|x['patch'];return c['grandTotal']==q['quantity']*q['unitPrice']+q['shipping']
        if 'move' in x:
            i,b=x['move'];d=defaultdict(list)
            for r,k,v in x['before']:d[b if r==i else k].append(v)
            return eq(c,{k:max(v) for k,v in d.items()})
        if 'new' in x:return c['width']==x['new']['hi']-x['new']['lo']
    if cls=='F5':
        d=dict(x['old'])
        for p in x['patches'] if 'patches' in x else [x['patch']]:d.update(p)
        return eq(c,d)
    if cls=='F6':
        R=x['rows']
        if 'ids' in c:return cmp_top(R,c['ids'],2,descending='highest' in s)
        if 'target' in x:return cmp_top(R,[c['id']],1,key=lambda r:abs(r[1]-x['target']))
        if 't' in x:return any(c['id']==i and a<=x['t']<b for i,a,b in R)
        if 'maximum' in s:return cmp_top([r for r in R if r[1] is not None],[c['id']],1,descending=True)
        if 'closed interval' in s:
            lo,hi=map(rat,re.search(r'\[([^,]+),\s*([^\]]+)\]',s).groups())
            return any(c['id']==i and lo<=rat(v)<=hi for i,v in R)
    if cls=='F7':
        if 'items' in c:return bag(x['reference'])==bag(c['items'])
        if 'events' in c:return bag(x['reference'])==bag(c['events'])
        if 'amounts' in x:return c['net']==sum(x['amounts'])
        return eq(c,x['reference'])
    if cls=='F8':
        w=walls(x)
        if isinstance(w,str):return c.get('error')==w
        return 'utc' in c and normalize_dt(c['utc'])==w
    if cls=='F9':
        return eq(c['repr'],x['inOrder'][0]) if 'inOrder' in x else any(eq(c['repr'],p) for p in x['peers'])
    if cls=='F10':
        x={k:([list(map(rat,a)) for a in v] if v and isinstance(v[0],list) else list(map(rat,v))) for k,v in x.items() if k!='format'}
        if 'inside' in c:return c['inside']==(polygon(x['shell'],x['pt'])==1)
        if 'member' in c:return c['member']==(polygon(x['shell'],x['pt'])>=0 and polygon(x['hole'],x['pt'])!=1)
        if 'intersects' in c or 'meet' in c:return next(iter(c.values()))==meet(*x['a'],*x['b'])
        if 'overlap' in c:return c['overlap']==all(max(x['a'][i],x['b'][i])<min(x['a'][i+2],x['b'][i+2]) for i in range(2))
        if 'within' in c:return c['within']==(sum((p-q)**2 for p,q in zip(x['p'],x['q']))<=rat(re.search(r'<= (\d+)',s)[1])**2)
    if cls=='O3':
        if 'numbers' in c:
            P=lambda r:0;K=lambda r:r[1];keep=lambda r:True
            if 'per partition' in s:P=lambda r:r[1];K=lambda r:r[2]
            if 'NULLS FIRST' in s:K=lambda r:(r[1] is not None,r[1])
            if 'stable ID ASC' in s:K=lambda r:(-r[1],r[0])
            if 'filtering' in s:keep=lambda r:r[2] is True
            return rows_number(x['rows'],c['numbers'],P,K,keep)
        if 'ids' in c:
            ids=c['ids']; R=x['rows']
            if 'sum' in c:return cmp_top(R,ids,2,descending=True) and c['sum']==sum(r[2] for r in R if r[0] in ids)
            if 'ties by ascending ID' in s:return ids==[r[0] for r in sorted(R,key=lambda r:(-r[1],r[0]))[:2]]
            if 'WITH TIES' in s:
                cutoff=sorted(r[1] for r in R)[min(2,len(R))-1]
                return bag(ids)==bag([r[0] for r in R if r[1]<=cutoff])
            if 'NULLS LAST' in s:
                return len(ids)<=3 and cmp_top(R,ids,len(ids),key=lambda r:(r[1] is None,r[1]))
            if 'per supplied division' in s:
                groups=defaultdict(list)
                for r in R:groups[r[1]].append(r)
                return len(ids)==len(groups) and all(cmp_top(z,[r[0] for r in z if r[0] in ids],1,key=lambda r:r[2],descending=True) for z in groups.values())
            nword=re.search(r'exactly (\d+|two|three)',s)[1]
            return cmp_top(R,ids,{'two':2,'three':3}.get(nword,int(nword) if nword.isdigit() else 0),descending=True)
        if 'offers' in x:return any(a==min(o[0] for o in x['offers']) and [b,d]==[c['vendor'],c['days']] for a,b,d in x['offers'])
        if 'teams' in x:return set(c)==set(x['teams']) and all(c[t] in a for t,a in x['teams'].items())
        if 'first' in c:
            R=x['rows']; lo=min(r[1] for r in R); hi=max(r[1] for r in R)
            return (len(R)==1 or c['first']!=c['last']) and any(i==c['first'] and v==lo for i,v in R) and any(i==c['last'] and v==hi for i,v in R)
        if 'edges' in x:return any(v==max(e[2] for e in x['edges']) and bag([a,b])==bag([c['from'],c['to']]) for a,b,v in x['edges'])
        if 'raw' in c:return c['raw'] in x['peers'] and c['normalized']==c['raw'].lower()
        if 'groups' in c:
            P=defaultdict(list)
            if 'department' in s:
                R=x['rows']; key=lambda r:(r[0],r[1].lower())
                vs=lambda rec:(rec[:-1],rec[-1])
            else:
                R=x.get('inOrder',x.get('values'))
                if 'trailing ASCII' in s:key=lambda v:v.rstrip(' ')
                elif 'absolute integer' in s:key=abs
                elif 'case-insensitively' in s or 'earliest inserted' in s:key=str.lower
                else:key=lambda v:v
                vs=lambda rec:(rec[0],rec[1])
            for i in R:P[key(i)].append(i)
            if len(c['groups'])!=len(P):return False
            for rec in c['groups']:
                val,count=vs(rec); A=P.pop(key(val),[])
                if not A or val not in (A[:1] if 'earliest inserted' in s else A) or count!=len(A):return False
            return not P
    if cls=='O4':
        if 'referenceHex' in x:
            a=wkb(x['referenceHex'])
            try:return a==wkb(c['hex'])
            except (ValueError,struct.error):return False
        if 'text' in c:
            a=rat(x['reference'])
            try:return rat(c['text'])==a
            except ValueError:return False
        if 'serial' in c:return date_serial(x,c['serial'])
        if 'points' in c:
            def coords(ps):
                return {tuple(map(rat,p[:2] if 'Project triples' in s else p)) for p in ps}
            return coords(x['points'])==coords(c['points'])
    raise NotImplementedError('unhandled contract schema')

def predictions(rows):
    out=[]
    for r in rows:
        assert 'expected_legal' not in r
        p={k:r[k] for k in ('case_id','class','subtype')}
        try:
            p['predicted_legal']=legal(r)
            assert type(p['predicted_legal']) is bool
        except (NotImplementedError,ValueError,TypeError,KeyError,AttributeError,AssertionError,IndexError,ZeroDivisionError) as e:
            p.update(predicted_legal=None,unsupported=f'{type(e).__name__}: {e}')
        out.append(p)
    return out

if __name__=='__main__':
    args=argparse.ArgumentParser()
    args.add_argument('blind',type=Path)
    rows=json.loads(args.parse_args().blind.read_text())
    print(json.dumps(predictions(rows),indent=2))
