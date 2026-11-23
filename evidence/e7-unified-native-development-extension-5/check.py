import argparse
from collections import Counter
from pathlib import Path
import json,sys,subprocess
p=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('inputs',type=Path);a=ap.parse_args()
subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=p,check=True,stdout=subprocess.DEVNULL)
ids=(p/'NEW-IDS.txt').read_text().split();assert len(set(ids))==len(ids)==15
assert sorted(x.name for x in (p/'packages').iterdir())==sorted(ids)
rows=(p/'REPLAY.tsv').read_text().splitlines()
assert len({x.split()[0] for x in rows})==len(rows)==55
assert Counter(x.split()[1] for x in rows)=={'native_authored_development':39,'native_external_transfer':15,'receipt_only':1}
r=subprocess.check_output([sys.executable,'-IB','replay.py','--inputs',str(a.inputs.resolve()),*ids],cwd=p)
assert r==(p/'NEW-REPLAY.tsv').read_bytes();sys.stdout.buffer.write(r)
