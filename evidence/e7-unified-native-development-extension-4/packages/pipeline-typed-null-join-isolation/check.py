"""Run: /usr/bin/python3 -IB producer.py | python3 -IB check.py"""
import json,sys
import pandas as pd
src=json.load(sys.stdin)
results={}
for name,case in src.pop("cases").items():
    expect={tuple(p) for p in case["oracle"]}
    results[name]={}
    for typed in (False,True):
        for filter_null in (False,True):
            tables=[]
            for side,rows in zip(("left","right"),case["tables"]):
                ids,keys=zip(*rows)
                # Extension construction through object avoids any binary64 intermediate.
                if typed:keys=pd.array(pd.Series(keys,dtype=object),dtype="Int64")
                f=pd.DataFrame({side:ids,"key":keys})
                if filter_null:f=f[f.key.notna()]
                tables.append(f)
            a,b=tables
            merged=a.merge(b,on="key")
            got=set(zip(merged.left,merged.right))
            assert len(got)==len(merged)
            extra=sorted(got-expect);missing=sorted(expect-got)
            results[name][("int64" if typed else "infer")+("-sql-null" if filter_null else "-native")]={
                "dtype":str(a.key.dtype),"extra":extra,"missing":missing}
            clean=not name.endswith("-null")
            collapse=not (typed or clean or name=="small-null")
            assert len(extra)==(3 if collapse else 0)+int(not filter_null and not clean)
            assert not missing
print(json.dumps({"versions":dict(src,pandas=pd.__version__),"comparisons":results},sort_keys=True,indent=2))
