"""B0 experiments 3-6: build an OpenWiki scope (records, .openwikiignore, INSTRUCTIONS.md) for N graph types of one repository.

Prototype of the B3 adapter: the chain generator and brief here are what openwiki-scope will produce.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path, PurePosixPath


def chain(paths: list[str], directories: bool) -> list[str]:
    """Deny everything, then open each path's ancestors one level at a time (gitignore last-match-wins)."""
    targets = sorted({str(PurePosixPath(p).parent) if directories else p for p in paths})
    if directories:
        # A directory inside another opened directory is already open.
        targets = [t for t in targets if not any(t != o and t.startswith(o + "/") for o in targets)]
    lines = ["*", "!/openwiki/"]
    opened: set[str] = set()
    for t in targets:
        parts = PurePosixPath(t).parts
        for i in range(1, len(parts)):
            ancestor = "/".join(parts[:i])
            if ancestor not in opened:
                lines += [f"!/{ancestor}/", f"/{ancestor}/*"]
                opened.add(ancestor)
        lines.append(f"!/{t}/" if directories else f"!/{t}")
    return lines


def brief(types: list[dict], repository: str, jsonl: str | None) -> str:
    by_ns: dict[str, list[dict]] = collections.defaultdict(list)
    for t in types:
        by_ns[t["fullName"].rsplit(".", 1)[0] if "." in t["fullName"] else ""].append(t)
    out = [
        "# Scope",
        "",
        f"Document only the {len(types)} types below from the `{repository}` repository, and how they work together.",
        "Every other file in the repository is outside the scope: do not read or document it.",
        "Types outside the list may be mentioned only where a listed type depends on them.",
    ]
    if jsonl:
        out += ["", f"`{jsonl}` lists the same types as JSON lines (name, kind, namespace, files). Use it as an index; ground every claim in the source files."]
    out += ["", "## Types", ""]
    for ns in sorted(by_ns):
        out.append(f"### {ns or '(global)'}")
        out.append("")
        for t in sorted(by_ns[ns], key=lambda t: t["fullName"]):
            out.append(f"- `{t['fullName']}` ({t['kind'].lower()}): {', '.join(f'`{f}`' for f in t['files'])}")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", required=True, help="scan-accuracy.json with graphTypes")
    ap.add_argument("--repository", required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--namespace-prefix", default="")
    ap.add_argument("--mode", choices=["files", "dirs", "brief-only"], required=True)
    ap.add_argument("--jsonl", action="store_true", help="also commit the records as openwiki/scope.jsonl and name it in the brief")
    ap.add_argument("--repo-root", required=True)
    a = ap.parse_args()

    scan = json.loads(Path(a.scan).read_text(encoding="utf-8"))
    pool = [r for r in scan["graphTypes"] if r["repository"] == a.repository and r["status"] == "found"
            and r["fullName"].startswith(a.namespace_prefix)]
    # Contiguous by namespace and name, so a scope is a coherent area rather than a random scatter.
    pool.sort(key=lambda r: r["fullName"])
    picked = pool[: a.count]
    if len(picked) < a.count:
        print(json.dumps({"type": "error", "message": f"only {len(picked)} found types"}))
        return 1
    root = Path(a.repo_root)
    records = [{"name": r["fullName"], "kind": r["kind"], "namespace": r["fullName"].rsplit(".", 1)[0],
                "repository": r["repository"], "files": r["files"], "locationStatus": r["status"]} for r in picked]
    files = sorted({f for r in records for f in r["files"]})
    (root / "openwiki").mkdir(exist_ok=True)
    jsonl_rel = "openwiki/scope.jsonl" if a.jsonl else None
    if a.jsonl:
        (root / jsonl_rel).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")
    (root / "openwiki" / "INSTRUCTIONS.md").write_text(brief(picked, a.repository, jsonl_rel), encoding="utf-8")
    ignore = [] if a.mode == "brief-only" else chain(files, a.mode == "dirs")
    if ignore:
        (root / ".openwikiignore").write_text("\n".join(ignore) + "\n", encoding="utf-8")
    (root.parent / f"{root.name}.scope.json").write_text(json.dumps({"types": [r["name"] for r in records], "files": files,
                                                       "ignore": ignore}, indent=1), encoding="utf-8")
    print(json.dumps({"type": "scope", "types": len(records), "files": len(files), "ignoreLines": len(ignore),
                      "namespaces": len({r["namespace"] for r in records})}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
