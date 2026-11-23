import openpyxl as x
from openpyxl.workbook.defined_name import DefinedName
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from xml.etree import ElementTree as E
import json,argparse,subprocess
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def build(p,mode):
 w=x.Workbook();src=w.active;src.title='Template';g=w.create_sheet('Global')
 g['A1']=100;src['A1']=10;src['B1']='=Marker*2'
 w.defined_names.add(DefinedName('Marker',attr_text="'Global'!$A$1"))
 src.defined_names.add(DefinedName('Marker',attr_text="'Template'!$A$1"))
 dst=w.copy_worksheet(src);dst.title='Copy';dst['A1']=20
 if mode=='stale':dst.defined_names.add(DefinedName('Marker',attr_text="'Template'!$A$1"))
 if mode=='retarget':dst.defined_names.add(DefinedName('Marker',attr_text="'Copy'!$A$1"))
 w.move_sheet(dst,offset=-2)
 w.save(p)
def graph(p):
 with ZipFile(p) as z:
  root=E.fromstring(z.read('xl/workbook.xml'))
  sheet_nodes=root.findall('s:sheets/s:sheet',NS)
  sheets=[s.get('name') for s in sheet_nodes]
  links={rel.get('Id'):rel.get('Target') for rel in E.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
  for sn in sheet_nodes[:2]:
   sid=sn.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
   path=links[sid]
   formula=E.fromstring(z.read(path.lstrip('/') if path.startswith('/') else 'xl/'+path))
   assert formula.findtext(".//s:c[@r='B1']/s:f",namespaces=NS)=='Marker*2'
  globals={};local={}
  for d in root.findall('s:definedNames/s:definedName',NS):
   i=d.get('localSheetId')
   if i is None: globals[d.get('name')]=d.text
   else:local[sheets[int(i)],d.get('name')]=d.text
  refs={a:local.get((a,'Marker'),globals['Marker']) for a in ('Copy','Template')}
  assert sheets==['Copy','Template','Global']
  return refs
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--consumer',action='store_true');opt=ap.parse_args()
 out={}
 with TemporaryDirectory() as d:
  d=Path(d);re=d/'recalc';re.mkdir();paths=[]
  for mode,wanted in [('default','Global'),('stale','Template'),('retarget','Copy')]:
   p=d/(mode+'.xlsx');paths.append(p);build(p,mode)
   bindings=graph(p)
   assert bindings=={'Copy':f"'{wanted}'!$A$1",'Template':"'Template'!$A$1"}
   wb=x.load_workbook(p)
   assert wb['Copy']['B1'].value==wb['Template']['B1'].value=='=Marker*2'
   out[mode]=dict(bindings=bindings)
  if opt.consumer:
   subprocess.run(['soffice','-env:UserInstallation='+(d/'profile').as_uri(),'--headless','--convert-to','xlsx','--outdir',str(re),*map(str,paths)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=100)
   for mode,expected in [('default',200),('stale',20),('retarget',40)]:
    b=x.load_workbook(re/(mode+'.xlsx'),data_only=True)
    vals={name:b[name]['B1'].value for name in ('Copy','Template')}
    assert vals=={'Copy':expected,'Template':20}, vals
    out[mode]['consumer']=vals
 print(json.dumps({'openpyxl':x.__version__,'cases':out},indent=2,sort_keys=True))
if __name__=='__main__':main()
