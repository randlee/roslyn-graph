"""Which store types does #if evaluation lose or gain compared with scanning every branch."""

import json
import sys
from pathlib import Path

from csharp_scan import declarations

items = json.loads(Path("compile-items.json").read_text(encoding="utf-8"))
acc = json.loads(Path("scan-accuracy.json").read_text(encoding="utf-8"))
missing = {(r, n) for r, n, _k in acc["notFoundAll"]}
for r in items:
    defines = set(r.get("defineConstants", []))
    for f in r.get("files", []):
        text = Path(f).read_text(encoding="utf-8-sig", errors="replace")
        every = {n for n, _ in declarations(text)}
        active = {n for n, _ in declarations(text, defines)}
        for n in sorted(every - active):
            if (r["repository"], n) in missing:
                print("lost", r["repository"], n, f)
sys.exit(0)
