import json,tempfile,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import openpyxl as x
ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def result(p,reset,formula):
    b=x.load_workbook(p,read_only=True,data_only=False);s=b.active
    v=x.load_workbook(p,read_only=True,data_only=True);c=v.active
    if reset:s.reset_dimensions();c.reset_dimensions()
    out=[]
    rows=s.iter_rows(min_row=2,min_col=1,max_col=3,values_only=True)
    vals=c.iter_rows(min_row=2,min_col=1,max_col=3,values_only=True)
    for (i,op,expr),(j,act,k) in zip(rows,vals,strict=True):
        assert i==j and op==act
        if i is None:continue
        if op=='WRITE' and k is None:
            op='UNCACHED' if formula and isinstance(expr,str) and expr.startswith('=') else 'CLEAR'
        out.append([str(i),op,None if k is None else str(k)])
    b.close();v.close()
    return out
with tempfile.TemporaryDirectory() as d:
    p=Path(d)/'src.xlsx';q=Path(d)/'patch.xlsx'
    w=x.Workbook();s=w.active
    for row in [(1,'id','op','key'),(2,11,'WRITE','=2+2'),(3,12,'CLEAR',None),(4,13,'WRITE','=1+1'),(8,14,'WRITE',0)]:
        for i,k in enumerate(row[1:],1):
            if k is not None:s.cell(row[0],i,k)
    w.save(p)
    with zipfile.ZipFile(p) as a,zipfile.ZipFile(q,'w') as b:
        for n in a.namelist():
            raw=a.read(n)
            if n=='xl/worksheets/sheet1.xml':
                t=ET.fromstring(raw);t.find('s:dimension',ns).set('ref','A1:C4')
                for f in t.findall('.//s:c',ns):
                    if f.get('r')=='C2':f.find('s:v',ns).text='4'
                raw=ET.tostring(t)
            b.writestr(n,raw)
    print(json.dumps({'openpyxl':x.__version__,'source':{'default':result(q,False,False),'reset_only':result(q,True,False),'contract':result(q,True,True)}}))
