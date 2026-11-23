import openpyxl as x,json,tempfile,pathlib,subprocess,argparse
from zipfile import ZipFile
from xml.etree import ElementTree as E
N=115
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def build(p,arm):
 w=x.Workbook();src=w.active;src.title='Template'
 src['A1']='REPEATABLE_HEADER'
 for i in range(2,N+2):src.cell(i,1,'ROAD_'+str(i).zfill(3))
 src.print_title_rows='1:1'
 if arm!='template':
  c=w.copy_worksheet(src);c.title='Copy'
  if arm=='repair':c.print_title_rows=src.print_title_rows
  w.remove(src)
 w.save(p)
def meta(p):
 with ZipFile(p) as z:
  t=E.fromstring(z.read('xl/workbook.xml'))
  return [[e.get('localSheetId'),e.text] for e in t.findall('.//s:definedName',NS) if e.get('name')=='_xlnm.Print_Titles']
def run():
 ap=argparse.ArgumentParser();ap.add_argument('--consumer',action='store_true'); opt=ap.parse_args()
 out={}
 with tempfile.TemporaryDirectory() as t:
  d=pathlib.Path(t)
  files=[]
  for arm in ('template','plain-copy','repair'):
   p=d/(arm+'.xlsx');build(p,arm);files.append(p)
   m=meta(p);assert m==([[str(0),"'Template'!$1:$1"]] if arm=='template' else [] if arm=='plain-copy' else [[str(0),"'Copy'!$1:$1"]])
   w=x.load_workbook(p);s=w.active
   assert [s.cell(i,1).value for i in range(2,N+2)]==['ROAD_'+str(i).zfill(3) for i in range(2,N+2)]
   out[arm]={'print_title_defs':m}
  if opt.consumer:
   subprocess.run(['soffice','-env:UserInstallation='+(d/'profile').as_uri(),'--headless','--convert-to','pdf','--outdir',str(d),*map(str,files)],check=True,timeout=120,capture_output=True)
   for arm in out:
    txt=subprocess.check_output(['pdftotext','-layout',str(d/(arm+'.pdf')),'-'],text=True)
    pages=[q for q in txt.split('\f') if 'ROAD_' in q]
    nums=[[int(word.split('_')[1]) for word in q.split() if word.startswith('ROAD_')] for q in pages]
    assert len(pages)>=2 and [i for p in nums for i in p]==list(range(2,N+2))
    header=['REPEATABLE_HEADER' in q for q in pages]
    assert header==([True]+[False]*(len(pages)-1) if arm=='plain-copy' else [True]*len(pages))
    out[arm].update(headers=header,pages=[[row[0],row[-1]] for row in nums])
 print(json.dumps({'openpyxl':x.__version__,'cases':out},sort_keys=True,indent=2))
if __name__=='__main__':run()
