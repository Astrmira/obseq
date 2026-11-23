from pathlib import Path
from collections import Counter
import subprocess
p=Path(__file__).resolve().parent
subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=p,check=True,stdout=subprocess.DEVNULL)
rows=(p/'REPLAY.tsv').read_text().splitlines()
assert len({r.split()[0] for r in rows})==len(rows)==87
assert Counter(r.split()[1] for r in rows)=={'native_authored_development':55,'native_external_transfer':31,'receipt_only':1}
new=(p/'NEW-REPLAY.tsv').read_text().splitlines()
assert len(new)==10 and len({r.split()[0] for r in new})==10 and all(r.split()[2]=='PASS' for r in new)
print('\n'.join(new))
