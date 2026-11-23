import argparse, json, tempfile, pathlib, subprocess, re, zipfile
from xml.etree import ElementTree as ET
import openpyxl as x
from openpyxl.utils.datetime import CALENDAR_MAC_1904,CALENDAR_WINDOWS_1900
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
inputs=[58,59,59.5,60,60.5,61,61.5]
def raw(p,column):
 with zipfile.ZipFile(p) as z:r=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
 return [float(c.find('s:v',NS).text) for c in r.findall('.//s:c',NS) if c.get('r').startswith(column)]
def restore(src,dst,cells):
 with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst,"w",zipfile.ZIP_DEFLATED) as zout:
  for name in zin.namelist():
   payload=zin.read(name)
   if name=="xl/worksheets/sheet1.xml":
    tree=ET.fromstring(payload)
    for cell in tree.findall(".//s:c",NS):
     if cell.get("r") in cells:
      value=cell.find("s:v",NS); value.text=str(float(value.text)+1)
    payload=ET.tostring(tree)
   zout.writestr(name,payload)
def generate(p,epoch):
 w=x.Workbook();w.epoch=epoch;s=w.active
 for i,a in enumerate(inputs,1):
  s[f'A{i}']=a;s[f'A{i}'].number_format='yyyy-mm-dd hh:mm';s[f'B{i}']=a;s[f'C{i}']=f'=A{i}-B{i}'
 w.save(p)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--consumer',action='store_true');a=ap.parse_args()
 out={}
 with tempfile.TemporaryDirectory() as d:
  d=pathlib.Path(d); dest=d/'dest';dest.mkdir()
  files=[]
  for name,ep in [('windows1900',CALENDAR_WINDOWS_1900),('mac1904',CALENDAR_MAC_1904)]:
   p=d/(name+'.xlsx');generate(p,ep)
   f=d/(name+'-roundtrip.xlsx');w=x.load_workbook(p); a_values=[w.active[f'A{i}'].value.isoformat() for i in range(1,8)]
   w.save(f);files.extend([p,f])
   before=raw(p,'A');after=raw(f,'A')
   assert before==inputs and raw(p,'B')==raw(f,'B')==inputs
   assert after==([58,59,59.5,59,59.5,61,61.5] if name=='windows1900' else inputs)
   out[name]={'before':before,'after':after,'header_epoch':ep.date().isoformat(),'dates':a_values}
   marked={"A"+str(i) for i,v in enumerate(before,1) if name=="windows1900" and 60<=v<61}
   recovered=d/(name+"-recovered.xlsx");restore(f,recovered,marked)
   assert raw(recovered,"A")==before and raw(recovered,"B")==inputs
   out[name]["ambiguity_bits"]=sorted(marked)
  if a.consumer:
   binary='soffice'
   subprocess.run([binary,'-env:UserInstallation='+(d/'profile').as_uri(),'--headless','--convert-to','xlsx','--outdir',str(dest),*[str(p) for p in files]],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=100)
   for name,row in out.items():
    row['original_consumer_differences']=raw(dest/(name+'.xlsx'),'C')
    row['roundtrip_consumer_differences']=raw(dest/(name+'-roundtrip.xlsx'),'C')
    assert row["original_consumer_differences"]==[0]*7
    assert row["roundtrip_consumer_differences"]==([0,0,0,-1,-1,0,0] if name=="windows1900" else [0]*7)
 print(json.dumps({'openpyxl':x.__version__,'matrix':out},indent=2,sort_keys=True))
if __name__=='__main__':main()
