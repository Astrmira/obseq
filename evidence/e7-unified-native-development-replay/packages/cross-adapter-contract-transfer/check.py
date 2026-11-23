import argparse,hashlib,json,tempfile
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import openpyxl as xl,pandas as pd
import runpy
C=runpy.run_path(str(Path(__file__).with_name('oracle_contract.py')))
check,digest,oracle=(C[k] for k in ('check','digest','oracle'))
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def workbook(p,m,rev):
 raw=p.with_suffix('.draft.xlsx');w=xl.Workbook();s=w.active
 s.append(m['artifact']['columns']+['cached'])
 chosen=list(reversed(m['artifact']['rows'])) if rev else m['artifact']['rows']
 for i,r in enumerate(chosen,2):s.append(r+[f'=C{i}+D{i}*0'])
 w.save(raw)
 with ZipFile(raw) as src, ZipFile(p,'w') as out:
  for n in src.namelist():
   buf=src.read(n)
   if n=='xl/worksheets/sheet1.xml':
    t=ET.fromstring(buf)
    for j,r in enumerate(chosen,2):
     t.find(f".//s:c[@r='F{j}']/s:v",NS).text=str(r[2])
    buf=ET.tostring(t)
   out.writestr(n,buf)
def run(p,m,mode):
 b=xl.load_workbook(p,data_only=True,read_only=True)
 rows=[list(r) for r in b.active.iter_rows(min_row=2,values_only=True)]
 b.close()
 b=xl.load_workbook(p,data_only=False,read_only=True)
 formulas=[list(r) for r in b.active.iter_rows(min_row=2,values_only=True)]
 b.close()
 assert [r[:5] for r in formulas]==[r[:5] for r in rows]
 for j,(f,row) in enumerate(zip(formulas,rows,strict=True),2):
  assert f[5]==f'=C{j}+D{j}*0' and row[5]==row[2]
 logical=sorted(r[:5] for r in rows)
 e=m['derivation']['required_runtime_epoch']
 df=pd.DataFrame(rows,columns=m['artifact']['columns']+['cached']);df=df[df['eligible']==1].copy()
 df['score']=df['base']+e*df['sensitivity']
 df['evidence']='computed';df['produced_epoch']=e
 if mode=='cached':
  df['score']=df['cached'];df['evidence']='cache@0';df['produced_epoch']=0
 if mode=='invariant-cache':
  same=df['sensitivity']==0
  df.loc[same,'score']=df.loc[same,'cached'];df.loc[same,'evidence']='cache@0';df.loc[same,'produced_epoch']=0
 sort=df.sort_values(['group','score','id'],ascending=[True,False,mode!='reverse'])
 limits={int(g):k for g,k in m['output']['quota_by_group'].items()}
 sel=sort[sort.groupby('group').cumcount()<sort['group'].map(limits)]
 dto={'manifest_hash':digest(m),'logical_rows_hash':digest(logical),'runtime_epoch':e,
      'scores':df.sort_values('id')[['id','score']].values.tolist(),'ids':sel['id'].tolist()}
 return dto,df.sort_values('id')[['id','produced_epoch','evidence']].values.tolist()
def main():
 m=json.load(open('manifest.json'));out={}
 with tempfile.TemporaryDirectory() as t:
  for name in ('forward','reverse','cached','invariant-cache'):
   p=Path(t)/(name+'.xlsx');workbook(p,m,name=='reverse')
   wire,ev=run(p,m,name);wire=json.loads(json.dumps(wire))
   out[name]={'receipt':wire,'strict_evidence':ev,'gates':check(m,wire),'strict_epoch_gate':all(e==m['derivation']['required_runtime_epoch'] for _,e,_ in ev)}
 assert out['forward']['receipt']['ids']!=out['reverse']['receipt']['ids']
 for name in ('forward','reverse','invariant-cache'):
  assert all(out[name]['gates'].values()),out
 assert not out['cached']['gates']['derived'] and not out['cached']['gates']['output']
 assert out['forward']['receipt']==out['invariant-cache']['receipt']
 assert out['forward']['strict_evidence']!=out['invariant-cache']['strict_evidence']
 assert out['forward']['strict_epoch_gate'] and not out['invariant-cache']['strict_epoch_gate']
 print(json.dumps({'shared_contract_code_sha256':hashlib.sha256(Path('oracle_contract.py').read_bytes()).hexdigest(),
   'openpyxl':xl.__version__,'pandas':pd.__version__,'cases':out},indent=2,sort_keys=True))
if __name__=='__main__':main()
