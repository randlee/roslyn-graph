"""B0 experiment 2 audit: is any not-found type declared somewhere in its repository's Compile items?

A type the scanner missed would still have `class|struct|interface|enum|record|delegate <Name>` in some compiled
file. A type with no such text anywhere was produced by a source generator, weaver or the compiler.
"""

import collections
import json
import re
import sys
from pathlib import Path

items = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
acc = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
texts: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
for r in items:
    for f in r.get("files", []):
        texts[r["repository"]].append((f, Path(f).read_text(encoding="utf-8-sig", errors="replace")))

declared, absent = [], []
for repo, full, kind in acc["notFoundAll"]:
    simple = re.split(r"[.+]", re.sub(r"<[^<>]*>", "", full))[-1]
    if simple.startswith("<") or not simple:
        absent.append((repo, full, "compiler-named"))
        continue
    pat = re.compile(rf"\b(class|struct|interface|enum|record|delegate|Class|Structure|Interface|Enum|Module)\s+(?:[\w.<>,\s]*\s)?{re.escape(simple)}\b")
    hits = [f for f, t in texts[repo] if pat.search(t)]
    (declared if hits else absent).append((repo, full, hits[:3]))

graph_missing = [r for r in acc["graphTypes"] if r["status"] == "not-found"]
print(json.dumps({"notFound": len(acc["notFoundAll"]), "declaredSomewhere": len(declared), "absentFromSource": len(absent),
                  "graphNotFound": [(r["repository"], r["fullName"]) for r in graph_missing]}, indent=1))
for d in declared:
    print("declared:", d)
