"""Discovery for the design-toml workflow.

This is the one place that scans directories, and only to *suggest* values. Generation never scans:
it uses exactly what workspace.toml records.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

from . import gitinfo, msbuild
from .result import RgError
from .util import full_path, rel_posix

FINGERPRINT_NAMES = {"directory.build.props", "directory.build.targets", "directory.packages.props", "global.json", "nuget.config"}


def _find_outputs(name: str, places: list[Path]) -> list[dict[str, Any]]:
    found = {}
    for place in places:
        if not place.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(place):
            dirnames[:] = [d for d in dirnames if d.lower() not in {"obj", "ref", "refint", ".git", "node_modules"}]
            if f"{name}.dll" in filenames:
                path = Path(dirpath) / f"{name}.dll"
                found[str(path).lower()] = {"path": str(path), "modified": path.stat().st_mtime}
    return sorted(found.values(), key=lambda f: -f["modified"])


_PROPERTY = re.compile(r"\$\(([A-Za-z_][A-Za-z0-9_.]*)\)")


def _substitute(value: str, props: dict[str, str]) -> str:
    return _PROPERTY.sub(lambda m: props.get(m.group(1), m.group(0)), value)


_EMPTY_GUARD = re.compile(r"^\s*'\$\(([A-Za-z_][A-Za-z0-9_.]*)\)'\s*==\s*''\s*$")


def _only_if_empty(condition: str, props: dict[str, str]) -> bool:
    """True when a "'$(X)' == ''" guard is false because X is already set (for example SolutionDir in a solution build)."""
    match = _EMPTY_GUARD.match(condition)
    return bool(match and props.get(match.group(1)))


def import_chain(project: Path, solution_dir: Path) -> tuple[list[Path], set[str]]:
    """Follow <Import> elements, substituting properties defined literally along the way.

    Conditions are ignored except that an import must exist on disk. Imports that still contain an
    unknown $(Property) are returned as unresolved so the designer can decide by hand.
    """
    props = {"SolutionDir": str(solution_dir) + os.sep, "MSBuildProjectDirectory": str(project.parent)}
    found: list[Path] = []
    unresolved: set[str] = set()
    visiting: set[str] = set()

    def walk(file: Path) -> None:
        key = str(file).lower()
        if key in visiting:
            return
        visiting.add(key)
        try:
            root = ET.parse(file).getroot()
        except (ET.ParseError, OSError):
            return
        props["MSBuildThisFileDirectory"] = str(file.parent) + os.sep
        for node in root.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "PropertyGroup":
                if _only_if_empty(node.attrib.get("Condition", ""), props):
                    continue
                for child in node:
                    name = child.tag.rsplit("}", 1)[-1]
                    if _only_if_empty(child.attrib.get("Condition", ""), props):
                        continue
                    value = _substitute((child.text or "").strip(), props)
                    if value and "$(" not in value:
                        props[name] = value
            elif tag == "Import" and "Project" in node.attrib:
                raw = node.attrib["Project"]
                resolved = _substitute(raw, props)
                if "$(" in resolved or "*" in resolved:
                    unresolved.add(raw)
                    continue
                target = full_path(resolved.replace("\\", os.sep), file.parent)
                if target.is_file() and target not in found:
                    found.append(target)
                    walk(target)
                    props["MSBuildThisFileDirectory"] = str(file.parent) + os.sep

    walk(project)
    return found, unresolved


def _upward_files(start: Path, stop: Path) -> list[Path]:
    found, current = [], start
    while True:
        if current.is_dir():
            found += [p for p in current.iterdir() if p.is_file() and p.name.lower() in FINGERPRINT_NAMES]
        if current == stop or current.parent == current:
            break
        current = current.parent
    return found


def solution(solution_path: Path, root: Path | None, tfm: str | None) -> dict[str, Any]:
    solution_path = full_path(solution_path)
    projects = msbuild.read_solution(solution_path)
    if not projects:
        raise RgError.of("SOLUTION_EMPTY", f"{solution_path} lists no C# projects.")
    root = full_path(root) if root else Path(os.path.commonpath([solution_path.parent, *[p.path.parent for p in projects]]))
    repos: dict[str, dict[str, Any]] = {}
    packages: dict[str, dict[str, set[str]]] = {}
    fingerprint: dict[str, str] = {}
    unresolved_imports: set[str] = set()
    frameworks: Counter[str] = Counter()
    output_dirs: Counter[str] = Counter()
    rows = []
    for project in projects:
        rel = rel_posix(project.path, root)
        row: dict[str, Any] = {"project": rel, "name": project.name}
        try:
            info = msbuild.read_project(project.path)
            row["assemblyName"] = info.assembly_name
            row["targetFrameworks"] = info.target_frameworks
            frameworks.update(info.target_frameworks)
        except RgError as exc:
            row["problem"] = exc.problems[0].to_json()
            rows.append(row)
            continue
        try:
            state = gitinfo.repo_state(project.path.parent)
            repos[state.name] = state.to_json()
            row["repository"] = state.name
        except RgError as exc:
            row["repository"] = None
            row["problem"] = exc.problems[0].to_json()
        outputs = _find_outputs(info.assembly_name, [solution_path.parent / "bin", project.path.parent / "bin"])
        row["outputCandidates"] = [o["path"] for o in outputs[:3]]
        if outputs:
            output_dirs[rel_posix(Path(outputs[0]["path"]).parent, root)] += 1
        assets = msbuild.assets_path(project.path)
        if assets.is_file() and (tfm or info.target_frameworks):
            try:
                for pkg in msbuild.read_assets(assets, tfm or info.target_frameworks[0]).packages.values():
                    packages.setdefault(pkg.id, {}).setdefault(pkg.version, set()).add(project.name)
            except RgError:
                pass
        chain, unresolved = import_chain(project.path, solution_path.parent)
        unresolved_imports.update(unresolved)
        for target in chain:
            fingerprint.setdefault(rel_posix(target, root), "imported by the project build")
        for path in _upward_files(project.path.parent, root):
            fingerprint.setdefault(rel_posix(path, root), "inherited by MSBuild or NuGet")
        rows.append(row)
    common_output = output_dirs.most_common(1)[0][0] if output_dirs else ""
    overrides = {}
    for row in rows:
        if row.get("outputCandidates"):
            directory = rel_posix(Path(row["outputCandidates"][0]).parent, root)
            if directory != common_output:
                overrides[row["project"]] = directory
        elif "assemblyName" in row:
            row["problem"] = {"code": "NO_OUTPUT_FOUND", "message": "No built DLL found; build the solution before designing the profile."}
    return {
        "type": "discovery",
        "solution": str(solution_path),
        "suggestedRoot": str(root),
        "projects": rows,
        "repositories": repos,
        "targetFrameworks": dict(frameworks),
        "suggestedOutputDir": common_output,
        "outputOverrides": overrides,
        "packages": [
            {"id": pid, "versions": {v: sorted(c) for v, c in versions.items()}, "consumers": sum(len(c) for c in versions.values())}
            for pid, versions in sorted(packages.items(), key=lambda kv: (-sum(len(c) for c in kv[1].values()), kv[0].lower()))
        ],
        "fingerprintCandidates": [{"path": p, "reason": r} for p, r in sorted(fingerprint.items())],
        "unresolvedImports": sorted(unresolved_imports),
    }
