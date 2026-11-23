"""Derive exact descriptive medians from frozen local timing ledger."""
from collections import defaultdict
from statistics import median
import csv,json
g = defaultdict(list)
with open("timing.csv", newline="") as f:
    for r in csv.DictReader(f):
        g[r["file"],int(r["k"]),r["method"]].append(int(r["wall_ns"]))
assert len(g)==16 and all(len(v)==7 and min(v)>0 for v in g.values())
out = []
for file,k in sorted({(a,b) for a,b,_ in g}):
    x,y=(median(g[file,k,m]) for m in ("topn","guard"))
    out.append({"file":file,"k":k,"rerun_median_ns":x,"guard_median_ns":y,
                "guard_over_rerun":round(y/x,6)})
print(json.dumps(out,indent=2))
