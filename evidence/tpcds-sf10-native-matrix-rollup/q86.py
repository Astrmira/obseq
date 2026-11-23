import sys,json,pathlib
from collections import defaultdict,Counter
E,W=map(pathlib.Path,sys.argv[1:3]);sys.path.insert(0,str(E/'input/duck143'));import duckdb
d=duckdb.connect(str(W/'tpcds.duckdb'),read_only=True,config={'threads':'2','memory_limit':'700MB','max_temp_directory_size':'500MB','temp_directory':str(W/'spill-q86')})
q=dict(json.load((E/'sql-tpcds-143.json').open())['queries'])[86]
I={k:(a,b) for k,a,b in d.execute('SELECT i_item_sk,i_category,i_class FROM item').fetchall()}
dkeys={k for (k,) in d.execute('SELECT d_date_sk FROM date_dim WHERE d_month_seq BETWEEN 1200 AND 1211').fetchall()}
S=defaultdict(lambda: [0,0]); n=0
cur=d.execute('SELECT ws_sold_date_sk,ws_item_sk,ws_net_paid FROM web_sales WHERE ws_sold_date_sk BETWEEN ? AND ?',[min(dkeys),max(dkeys)])
while B:=cur.fetchmany(50000):
 for date,i,v in B:
  if date not in dkeys or i not in I:continue
  n+=1
  a,b=I[i]
  for k in [(a,b,0),(a,None,1),(None,None,2)]:
   rec=S[k]
   if v is not None: assert v*100==int(v*100);rec[0]+=int(v*100);rec[1]+=1
def descnullast(a):return (a is None,-a if a is not None else 0)
def output_key(r):
 amount,a,b,level,rank=r
 cat=a if level==0 else None
 return (-level,(cat is not None,cat),rank)
def tierrows(mutate):
 P=defaultdict(list)
 for (a,b,lev),(s,n) in S.items():
  r=lev if not mutate else int(a is None)+int(b is None)
  split= a if (lev==0 if not mutate else b is not None) else None
  P[r,split].append((s if n else None,a,b,r))
 O=[]
 for values in P.values():
  prev=object();rank=0
  for j,row in enumerate(sorted(values,key=lambda v:descnullast(v[0])),1):
   if row[0]!=prev:prev=row[0];rank=j
   O.append(row+(rank,))
 return sorted(O,key=output_key)
full=tierrows(False); faulty=tierrows(True)
def canon(l):return [(None if v is None else int(v*100),a,b,lev,r) for v,a,b,lev,r in l]
stock=canon(d.execute(q).fetchall())
qmut=q.replace('grouping(i_category)','(i_category IS NULL)::INTEGER').replace('grouping(i_class)','(i_class IS NULL)::INTEGER')
mut=canon(d.execute(qmut).fetchall())
def check(out,oracle):
 assert len(out)==min(100,len(oracle))
 assert [output_key(x) for x in out]==[output_key(x) for x in oracle[:len(out)]]
 top=output_key(oracle[len(out)-1]);target=Counter(x for x in oracle if output_key(x)<top)
 assert Counter(x for x in out if output_key(x)<top)==target
 virtual=Counter(x for x in oracle if output_key(x)==top)
 obs=Counter(x for x in out if output_key(x)==top)
 assert obs<=virtual
check(stock,full);check(mut,faulty)
different= sum(abs(v) for v in (Counter(stock)-Counter(mut)).values()) + sum(abs(v) for v in (Counter(mut)-Counter(stock)).values())
print(json.dumps({'qualifying_join_facts':n,'tagged_output_rows_before_limit':len(full),'null_dimension_rendering_collisions':sum(len({l for x,y,l in S if (x,y)==(a,b)})>1 for a,b in {(a,b) for a,b,k in S}),'groups_wrongly_inferred_by_nullability':sum(int(a is None)+int(b is None)!=k for a,b,k in S),'stock_exact':True,'mutant_exact_against_its_own_declared_contract':True,'stock_mutant_output_bag_symdiff':different,'stock_head_hierarchy_counts':dict(Counter(x[3] for x in stock)),'wrong_head_hierarchy_counts':dict(Counter(x[3] for x in mut))},sort_keys=True,indent=2))
