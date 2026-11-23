"""Native H2O Q3 association audit. Pass the original generator output directory."""
import csv, hashlib, json, math, sys
from collections import defaultdict
from pathlib import Path
import duckdb

P, M = 2**61-1, 10_001
names = ['J1_1e7_NA_5_0.csv','J1_1e7_1e4_5_0.csv']
hashes = ['29205553b85cee0eb36a52b0d16ed1a8067ba066ac28d7c2a995a5db371f7061',
          'f2e8ce2fd70647d1930a6401b3ca4786f361f85b7456ff7ddcee90a5e721fce1']
paths = [Path(sys.argv[1])/n for n in names]
for f,h in zip(paths,hashes):
    with f.open('rb') as src:
        assert hashlib.file_digest(src,'sha256').hexdigest()==h
L,R=paths
with R.open(newline='') as f:
    rd=csv.reader(f); assert next(rd)==['id1','id2','id4','id5','v2']
    right={}
    for j,(_,key,_,_,v) in enumerate(rd,1):
        assert key and key not in right
        right[key]=(j,v)
assert len(right)==10_000<M
groups=defaultdict(lambda:[0]*4)
witness=[]
with L.open(newline='') as f:
    rd=csv.reader(f); assert next(rd)==['id1','id2','id3','id4','id5','id6','v1']
    for i,(_,key,id3,*_) in enumerate(rd,1):
        acc=groups[key]; acc[0]+=1; acc[1]+=i; acc[2]+=i*i; acc[3]+=i*i*i
        if len(witness)<2 and id3 and key in right and all(prev[2]!=right[key][1] for prev in witness):
            witness.append((i,*right[key],int(id3)))
assert i==10_000_000 and i*M+M-1<P
exp=[0]*4
for key,acc in groups.items():
    j=right.get(key,(0,None))[0]
    for k in range(4):
        exp[k]+=sum(math.comb(k,t)*M**t*acc[t]*j**(k-t) for t in range(k+1))
exp=[v%P for v in exp]
(a,x,u,id3a),(b,y,v,id3b)=witness
ls="{'id1':'BIGINT','id2':'BIGINT','id3':'BIGINT','id4':'VARCHAR','id5':'VARCHAR','id6':'VARCHAR','v1':'DECIMAL(18,6)'}"
rs="{'id1':'BIGINT','id2':'BIGINT','id4':'VARCHAR','id5':'VARCHAR','v2':'DECIMAL(18,6)'}"
c=duckdb.connect(config={'threads':1,'memory_limit':'550MB','max_temp_directory_size':'0B','preserve_insertion_order':'true'})
# Both reductions use signed HUGEINT; intermediates are bounded by P squared.
modes={
 'clean':('j','v2'),
 'swap':(f'CASE i WHEN {a} THEN {y} WHEN {b} THEN {x} ELSE j END',
         f'CASE i WHEN {a} THEN {v}::DECIMAL(18,6) WHEN {b} THEN {u}::DECIMAL(18,6) ELSE v2 END'),
 'payload':('j',f'CASE WHEN i={a} THEN v2+0.000001 ELSE v2 END'),
 'forged-sentinel':('coalesce(j,1)','v2'),
}
def scan(mode, split=False):
    j,val=modes[mode]
    group='i%2 block,' if split else ''
    tail='GROUP BY block ORDER BY block DESC' if split else ''
    out=c.execute(f'''
WITH l AS (SELECT ordinality i,id2,v1 FROM read_csv(?,header=true,columns={ls},parallel=false) WITH ORDINALITY),
r AS (SELECT ordinality j,id2,v2 FROM read_csv(?,header=true,columns={rs},parallel=false) WITH ORDINALITY),
joined AS (SELECT i, {M}*i::HUGEINT+coalesce({j},0) z, v1, {val} val, v2 bound FROM l LEFT JOIN r USING(id2)),
sq AS (SELECT *,z*z%{P} z2 FROM joined)
SELECT {group}count(*),sum(z)%{P},sum(z2)%{P},sum(z2*z%{P})%{P},
  sum(v1),sum(val),count(*) FILTER(WHERE val IS DISTINCT FROM bound)
FROM sq {tail}''',list(map(str,paths))).fetchall()
    if split: out=[row[1:] for row in out]
    return dict(moment=[sum(r[k] for r in out)%P for k in range(4)],
                sums=[str(sum(r[k] for r in out)) for k in (4,5)],
                value_mutations_vs_clean=sum(r[6] for r in out))

clean, swap, payload, sentinel=[scan(mode) for mode in modes]
assert clean==scan('clean',True)
assert clean['moment']==exp and clean['value_mutations_vs_clean']==0
assert clean['sums']==swap['sums'] and clean['moment'][:2]==swap['moment'][:2]
assert (swap['moment'][2]-clean['moment'][2])%P==(2*M*(a-b)*(y-x))%P!=0
assert payload['moment']==exp and payload['value_mutations_vs_clean']==1
assert sentinel['moment'][0]==exp[0] and (sentinel['moment'][1]-exp[1])%P==1_452_830
five_codes=[sum(w*pow(M*i+1,k,P) for i,w in enumerate((1,-4,6,-4,1),1))%P for k in range(5)]
assert five_codes[:4]==[0]*4 and five_codes[4]!=0
print(json.dumps(dict(duckdb=duckdb.__version__,sha256=dict(zip(names,hashes)),P=P,M=M,
    left_rows=i, right_rows=len(right), left_key_groups=len(groups), expected=exp, witness=witness,
    clean=clean,swap=swap,payload=payload,forged_sentinel=sentinel,reversed_native_fold_equal=True,
    abstract_support_five_counterexample=five_codes),sort_keys=True,indent=2))
