"""B0 experiment 1: MSBuild Compile items for every source component of a solution or view manifest."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def components(manifest_path: Path, data_root: Path) -> list[dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["kind"] == "view":
        solution = json.loads((data_root / manifest["baseSolution"]["manifestPath"]).read_text(encoding="utf-8"))
        entries = solution["components"] + manifest["overlayComponents"]
    else:
        solution, entries = manifest, manifest["components"]
    workspace = Path(solution["workspace"]["path"])
    return [dict(e, componentManifest=json.loads((data_root / e["manifestPath"]).read_text(encoding="utf-8")), workspace=workspace) for e in entries]


def project_path(component: dict) -> tuple[Path, str]:
    """Absolute project path and its repo-relative form, for v2 (profile-relative) and v3 (repo-relative) manifests."""
    m = component["componentManifest"]
    repo = Path(m["origin"]["repository"])
    rel = m["build"]["project"]
    if m["identity"].startswith("assembly/v3|"):
        absolute = repo / rel
    else:
        candidates = [repo.parent / rel, repo / rel]
        absolute = next((c for c in candidates if c.is_file()), candidates[0])
    return absolute, absolute.relative_to(repo).as_posix() if absolute.is_relative_to(repo) else rel


def run(component: dict, msbuild: list[str]) -> dict:
    m = component["componentManifest"]
    project, rel = project_path(component)
    b = m["build"]
    args = [*msbuild, str(project), "-getItem:Compile", "-getProperty:DefineConstants", "-t:AddImplicitDefineConstants", "-nologo",
            f"-p:Configuration={b['configuration']}", f"-p:TargetFramework={b['targetFramework']}"]
    if b.get("platform"):
        args.append(f"-p:Platform={b['platform']}")
    if b.get("solution"):
        # Projects import $(SolutionDir)Common.targets: evaluate as the solution build did.
        repo = Path(m["origin"]["repository"])
        sln = next((c for c in (repo.parent / b["solution"], repo / b["solution"]) if c.is_file()), None)
        if sln:
            args += [f"-p:SolutionDir={sln.parent}{os.sep}", f"-p:SolutionPath={sln}", f"-p:SolutionName={sln.stem}",
                     f"-p:SolutionFileName={sln.name}", f"-p:SolutionExt={sln.suffix}"]
    started = time.monotonic()
    done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    seconds = round(time.monotonic() - started, 2)
    out = {"repository": m["origin"]["id"], "project": rel, "exists": project.is_file(), "seconds": seconds, "exit": done.returncode}
    if done.returncode != 0:
        out["error"] = (done.stdout + done.stderr).strip().splitlines()[-5:]
        return out
    doc = json.loads(done.stdout[done.stdout.index("{"):])
    items = doc["Items"]["Compile"]
    out["defineConstants"] = sorted({d.strip() for d in doc["Properties"]["DefineConstants"].split(";") if d.strip()})
    project_dir = project.parent.resolve()
    repo = Path(m["origin"]["repository"]).resolve()
    full = [Path(i["FullPath"]).resolve() for i in items]
    out.update(
        items=len(full),
        outsideProjectDir=sorted(p.as_posix() for p in full if not p.is_relative_to(project_dir)),
        outsideRepository=sorted(p.as_posix() for p in full if not p.is_relative_to(repo)),
        underObj=sum(1 for p in full if p.is_relative_to(project_dir / "obj")),
        files=[p.as_posix() for p in full],
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--data-root", default=os.environ.get("ROSLYN_GRAPH_DATA_ROOT", "F:\\"))
    ap.add_argument("--output", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--msbuild", default="dotnet msbuild")
    a = ap.parse_args()
    data_root = Path(a.data_root) / ".roslyn-graph"
    comps = [c for c in components(Path(a.manifest), data_root) if c["componentManifest"]["origin"]["kind"] == "source"]
    with ThreadPoolExecutor(a.jobs) as pool:
        results = list(pool.map(lambda c: run(c, a.msbuild.split()), comps))
    Path(a.output).write_text(json.dumps(results, indent=1), encoding="utf-8")
    ok = [r for r in results if r["exit"] == 0]
    summary = {
        "type": "compile-items", "projects": len(results), "ok": len(ok), "failed": [(r["repository"], r["project"], r.get("error")) for r in results if r["exit"] != 0],
        "secondsTotal": round(sum(r["seconds"] for r in results), 1), "secondsMax": max(r["seconds"] for r in results),
        "items": sum(r["items"] for r in ok),
        "projectsWithLinkedFiles": sum(1 for r in ok if r["outsideProjectDir"]),
        "linkedFiles": sum(len(r["outsideProjectDir"]) for r in ok),
        "filesOutsideRepository": sum(len(r["outsideRepository"]) for r in ok),
        "underObj": sum(r["underObj"] for r in ok),
    }
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
