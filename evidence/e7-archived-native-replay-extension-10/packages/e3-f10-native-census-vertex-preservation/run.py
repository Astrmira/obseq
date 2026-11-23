import sys,hashlib,json,pathlib,subprocess
import shapely as s
p=pathlib.Path(sys.argv[1]).resolve()
h=hashlib.sha256(p.read_bytes()).hexdigest()
assert h=='7bc773d83c01b6df69b8aada9c2b5983d97f22f4551947cc5c00b87c663223ef'
data=json.loads(subprocess.check_output(['/usr/bin/python3',str(pathlib.Path(__file__).with_name('read_gdal.py')),str(p)]))
def is_eligible(g):return g.geom_type in ('Polygon','MultiPolygon') and g.is_valid and not g.is_empty and s.get_coordinate_dimension(g)==2
r=[(i,s.from_wkb(bytes.fromhex(w))) for i,w in enumerate(data.pop('wkbs'))]
selected=[(i,g,s.Point((g if g.geom_type=='Polygon' else g.geoms[0]).exterior.coords[0])) for i,g in r if is_eligible(g)]
assert all(g.covers(a) for i,g,a in selected)
assert all(s.set_precision(g,0).covers(a) for i,g,a in selected)
out={'source_sha256':h,'source':data,'geos':s.geos_version_string,'shapely':s.__version__,'baseline_covers':len(selected),'excluded':len(r)-len(selected),'cells':[]}
for grid in [1e-9,1e-8,1e-7,1e-6,1e-5]:
 new=[(i,g,a,s.set_precision(g,grid)) for i,g,a in selected]
 weak=lambda g,n:is_eligible(n) and n.geom_type==g.geom_type
 missed=[i for i,g,a,n in new if weak(g,n) and not n.covers(a)]
 out['cells'].append(dict(grid=grid,row_count=len(new),weak_pass=sum(weak(g,n) for i,g,a,n in new),weak_pass_anchor_loss=len(missed),witness_ordinal_sha256=hashlib.sha256(json.dumps(missed).encode()).hexdigest()))
print(json.dumps(out,sort_keys=True,indent=2))
