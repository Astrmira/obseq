import argparse,ast,csv,hashlib,json,math,re,subprocess,sys,tempfile
from decimal import Decimal
from pathlib import Path
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run_h2o(prev, data, stock, helper):
    assert sha(prev)=='e29693757889929569326e62552ffb795d188ac321a951004bec27bca972651a'
    assert sha(helper)=='d64c4ecafab8e2fc2534f42402ca959e79f83f972a6dea8c50fc31771d1784f6'
    ns={}
    m=ast.parse(helper.read_text())
    m.body=[x for x in m.body if isinstance(x,ast.FunctionDef) and x.name in {'str_round','make_chk'}]
    assert len(m.body)==2
    exec(compile(m,str(helper),'exec'),ns)
    text=prev.read_text()
    idx=text.index('row=con.execute(')
    original=sys.argv
    try:
        sys.argv=[str(prev),str(data),str(stock)]
        env={'__name__':'__main__'}
        exec(compile(text[:idx],str(prev),'exec'),env)
    finally:
        sys.argv=original
    c,Q,code,u,v,mu,mv=[env[k] for k in ('con','Q','lcode','u','v','mu','mv')]
    stock_section=stock.read_text().split(' # q3',1)[1].split(' # q4',1)[0]
    [chk1,chk2]=re.findall(r'chk = con.execute\("([^"]+)"\)', stock_section)
    assert chk1==chk2=='SELECT SUM(v1) AS v1, SUM(v2) AS v2 FROM ans'
    def val(n):return "'"+format(Decimal(n)/1000000,'f')+"'::DOUBLE"
    wm=f'CASE WHEN ({code})={u} THEN {val(mv)} WHEN ({code})={v} THEN {val(mu)} ELSE v2 END'
    neg=f'CASE WHEN ({code})={u} THEN v2+1 ELSE v2 END'
    rows=[]
    for name,base in [('clean',Q),('payload_exchange',f'SELECT * REPLACE ({wm} AS v2) FROM ({Q})'),('one_unit_positive_control',f'SELECT * REPLACE ({neg} AS v2) FROM ({Q})')]:
        c.execute('CREATE OR REPLACE TEMP VIEW ans AS '+base)
        pair=c.execute(chk1).fetchone()
        rows.append(dict(arm=name,rounded_stock_chk=ns['make_chk'](pair)))
    assert rows[0]['rounded_stock_chk']==rows[1]['rounded_stock_chk']!=rows[2]['rounded_stock_chk']
    return dict(rows=10000000,stock_checksums=rows,
        nontrivial_payload_exchange=bool(env['payload_expected']),witness_source_check='predecessor hash-pinned exact observer')

def q39(folder,stock):
    assert sha(stock)=='65171e4a8a54b5330fba5c97c4d705f34410c62748d9180cb2e161b628a7540f'
    z=[]
    locks=json.loads(Path(__file__).with_name('SF10-SHA256.json').read_text())
    for f,h in sorted(locks.items()):
        p=folder/f; assert sha(p)==h
        z.extend(json.loads(l) for l in p.read_text().splitlines())
    assert len(z)==2433 and len({tuple(r['key']) for r in z})==2433
    def arr(tag):
        out=[]
        for row in z:
            i,k=row['key']; a,b,c,d=map(float.fromhex,row[tag])
            out.append([i,k,1,a,b,i,k,2,c,d])
        return out
    A,B=arr('t1'),arr('t4')
    C=[r[:] for r in B]; D=[r[:] for r in B]
    existing={tuple(x['key']) for x in z}
    j=next(i for i,r in enumerate(B) if (r[0],r[1]+1) not in existing)
    C[j][1]+=1; C[j][6]+=1
    D[j][3]*=2
    K=(0,1,2,5,6,7); V=(3,4,8,9)
    def typed(a,b):
        return all(all(x[k]==y[k] for k in K) and all(abs(x[i]-y[i])<=4*max(math.ulp(x[i]),math.ulp(y[i])) for i in V) for x,y in zip(a,b))
    with tempfile.TemporaryDirectory(prefix='q39-e8-') as root:
        root=Path(root); files=[]
        for i,x in enumerate((A,B,C,D)):
            f=root/f'{i}.ans'
            with f.open('w',newline='') as p: csv.writer(p,delimiter='\t',lineterminator='\n').writerows(x)
            files.append(f)
        obs=[]
        for tag,i,k,ref,cand in [('native_1_to_4',0,1,A,B),('native_4_to_1',1,0,B,A),('exact_key_plus_one',0,2,A,C),('double_approximate_positive_control',0,3,A,D)]:
            p=subprocess.run([sys.executable,'-B',str(stock),str(files[i]),str(files[k])],capture_output=True,text=True)
            v=ast.literal_eval(p.stdout.strip()); assert not p.stderr and v['class'] in ('match','diff')
            assert p.returncode==int(v['class']=='match')
            obs.append(dict(arm=tag,cwi=v['class'],typed=typed(ref,cand)))
    return dict(rows=len(A),rows_with_numeric_drift=sum(a!=b for a,b in zip(A,B)),results=obs)
def main():
    p=argparse.ArgumentParser()
    for a in ('h2o_prev','h2o_data','h2o_stock','h2o_helper','sf10','cwi'):p.add_argument(a,type=Path)
    a=p.parse_args()
    print(json.dumps(dict(h2o=run_h2o(a.h2o_prev,a.h2o_data,a.h2o_stock,a.h2o_helper),tpcds=q39(a.sf10,a.cwi)),sort_keys=True,indent=2))
if __name__=='__main__':main()
