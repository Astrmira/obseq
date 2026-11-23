"""Execute the archived developed cohort in a normal checkout with admitted local inputs."""
from pathlib import Path
import hashlib, json, subprocess, sys
r=Path(__file__).resolve().parent
pins=json.loads((r/'BASE-PINS.json').read_text())['roots']
cmd=[sys.executable,'-IB',str(r/'replay.py'),'--include-prior']
for meta in pins.values():
 here=r.parent/Path(meta['source_path']).parts[-2]
 manifest=here/'MANIFEST.json'
 if not manifest.is_file() or hashlib.sha256(manifest.read_bytes()).hexdigest()!=meta['manifest_sha256']:
  raise SystemExit('Missing or modified archive baseline: '+str(manifest))
 cmd.extend(('--prior-root',str(here)))
raise SystemExit(subprocess.run(cmd+sys.argv[1:]).returncode)
