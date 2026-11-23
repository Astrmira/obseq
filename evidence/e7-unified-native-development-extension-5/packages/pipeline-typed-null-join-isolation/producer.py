import json, sqlite3
from osgeo import gdal, ogr
import numpy as np
gdal.UseExceptions()
base=2**53
cases={"small":[0,1],"negative-boundary":[-base,-base-1],
       "positive-boundary":[base,base+1],"near-extreme":[2**63-2,2**63-1]}
out={}
for name,keys in cases.items():
    for null in (False,True):
        L=[keys[0],keys[1],keys[1]]+([None] if null else [])
        R=[keys[0],keys[1]]+([None] if null else [])
        db=sqlite3.connect(":memory:"); data=ogr.GetDriverByName("Memory").CreateDataSource("X")
        exported=[]
        for side,values in (("L",L),("R",R)):
            db.execute(f"create table {side}(id integer primary key, k integer)")
            db.executemany(f"insert into {side} values(?,?)",enumerate(values))
            layer=data.CreateLayer(side,geom_type=ogr.wkbNone)
            layer.CreateField(ogr.FieldDefn("k",ogr.OFTInteger64))
            for v in values:
                f=ogr.Feature(layer.GetLayerDefn())
                if v is not None:f.SetField(0,v)
                layer.CreateFeature(f)
            with layer.GetArrowStreamAsNumPy() as stream:
                batch=next(iter(stream)); field=batch["k"]
                assert field.dtype==np.int64
                mask=np.ma.getmaskarray(field)
                arr=[[int(i),None if m else int(v)] for i,m,v in zip(batch["OGC_FID"],mask,field)]
            assert arr==list(map(list,enumerate(values)));exported.append(arr)
        sql=list(map(list,db.execute("select L.id,R.id from L join R on L.k=R.k order by 1,2")))
        pure=[[i,j] for i,x in enumerate(L) for j,y in enumerate(R) if x is not None and y is not None and x==y]
        assert sql==pure
        out[name+("-null" if null else "-clean")]={"tables":exported,"oracle":sql}
print(json.dumps({"gdal":gdal.VersionInfo(),"numpy":np.__version__,"sqlite":sqlite3.sqlite_version,"cases":out},sort_keys=True))
