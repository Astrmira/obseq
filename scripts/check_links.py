"""Check inline and reference-style relative links in shipped Markdown."""

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

root = Path(__file__).resolve().parents[1]
links = re.compile(r"\]\(<?([^\s)>]+)>?(?:\s+[\"'][^\n]*?[\"'])?\)|^\s*\[[^\]\n]+\]:\s*<?([^\s>]+)", re.M)
errors = []
ignored = {".git", ".venv", "scratch", "build", "dist"}
for path in root.rglob("*.md"):
    if ignored.intersection(path.relative_to(root).parts):
        continue
    text = re.sub(r"```.*?^```[^\n]*", "", path.read_text(encoding="utf-8"), flags=re.S | re.M)
    for match in links.finditer(text):
        value = urlsplit(match[1] or match[2])
        if value.scheme or value.netloc or not value.path:
            continue
        target = (path.parent / unquote(value.path)).resolve()
        if not target.is_relative_to(root) or not target.exists():
            errors.append(f"{path.relative_to(root)}: {value.path}")
if errors:
    print("\n".join(errors), file=sys.stderr)
sys.exit(bool(errors))
