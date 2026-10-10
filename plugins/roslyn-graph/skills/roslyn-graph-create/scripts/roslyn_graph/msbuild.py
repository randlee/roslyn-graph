"""Read solution files, project files and NuGet restore assets without evaluating MSBuild.

The skill never builds. It only reads what a successful build and restore left behind.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .result import RgError
from .util import full_path

_SLN_PROJECT = re.compile(r'^Project\("\{[0-9A-Fa-f-]+\}"\)\s*=\s*"(?P<name>[^"]*)",\s*"(?P<path>[^"]+)"')


@dataclass(frozen=True)
class SolutionProject:
    name: str
    relative_path: str  # as written in the solution, normalized to forward slashes
    path: Path


def read_solution(solution: Path) -> list[SolutionProject]:
    if not solution.is_file():
        raise RgError.of("SOLUTION_NOT_FOUND", f"Solution file does not exist: {solution}", "Check 'root' and 'solution' in the profile.")
    if solution.suffix.lower() == ".slnx":
        entries = [(Path(p).stem, p) for p in _slnx_paths(solution)]
    elif solution.suffix.lower() == ".sln":
        entries = []
        for line in solution.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            match = _SLN_PROJECT.match(line.strip())
            if match:
                entries.append((match["name"], match["path"]))
    else:
        raise RgError.of("SOLUTION_UNSUPPORTED", f"Unsupported solution file type: {solution.suffix}", "Use a .sln or .slnx file.")
    projects = []
    for name, raw in entries:
        if not raw.lower().endswith(".csproj"):
            continue  # solution folders and non-C# projects
        rel = raw.replace("\\", "/")
        projects.append(SolutionProject(name, rel, full_path(rel, solution.parent)))
    return projects


def _slnx_paths(solution: Path) -> list[str]:
    tree = ET.parse(solution)
    return [node.attrib["Path"] for node in tree.iter() if node.tag == "Project" and "Path" in node.attrib]


@dataclass
class ProjectInfo:
    path: Path
    assembly_name: str
    assembly_name_source: str  # "csproj" or "file-name"
    target_frameworks: list[str] = field(default_factory=list)


def read_project(project: Path) -> ProjectInfo:
    if not project.is_file():
        raise RgError.of("PROJECT_NOT_FOUND", f"Project listed in the solution does not exist: {project}")
    try:
        root = ET.parse(project).getroot()
    except ET.ParseError as exc:
        raise RgError.of("PROJECT_UNREADABLE", f"Cannot parse {project}: {exc}") from exc

    def values(tag: str) -> list[str]:
        return [(node.text or "").strip() for node in root.iter() if _local(node.tag) == tag and (node.text or "").strip()]

    names = values("AssemblyName")
    frameworks: list[str] = []
    for value in values("TargetFramework") + values("TargetFrameworks"):
        frameworks.extend(part.strip() for part in value.split(";") if part.strip())
    if names:
        name = names[-1]
        if "$(" in name:
            raise RgError.of(
                "ASSEMBLY_NAME_COMPUTED",
                f"{project.name} computes its AssemblyName from MSBuild properties ({name}).",
                "Add the evaluated name under [profiles.<name>.assembly_names] keyed by the project path.",
                project=str(project),
            )
        return ProjectInfo(project, name, "csproj", frameworks)
    return ProjectInfo(project, project.stem, "file-name", frameworks)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@dataclass(frozen=True)
class AssetPackage:
    id: str
    version: str
    sha512: str
    folder: Path | None
    runtime: tuple[str, ...]
    compile: tuple[str, ...]

    def asset_dirs(self) -> list[Path]:
        if self.folder is None:
            return []
        dirs = {(self.folder / rel).parent for rel in self.runtime + self.compile}
        return sorted(dirs, key=str)


@dataclass
class Assets:
    path: Path
    target_key: str
    packages: dict[str, AssetPackage]  # keyed by lower-case package ID
    package_folders: list[Path]


def assets_path(project: Path) -> Path:
    return project.parent / "obj" / "project.assets.json"


def select_target(keys: list[str], tfm: str, source: Path) -> str:
    candidates = [k for k in keys if "/" not in k and (k == tfm or k.startswith(tfm + "-"))]
    if len(candidates) != 1:
        raise RgError.of(
            "ASSETS_TARGET_AMBIGUOUS" if candidates else "ASSETS_TARGET_MISSING",
            f"{source} has {len(candidates)} restore targets matching '{tfm}': {candidates or keys}.",
            "Set target_framework in the profile to the framework the build actually used.",
        )
    return candidates[0]


def read_assets(path: Path, tfm: str) -> Assets:
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise RgError.of("ASSETS_NOT_FOUND", f"Restore output is missing: {path}", "Restore and build the solution first.") from exc
    target_key = select_target(list(document.get("targets", {})), tfm, path)
    folders = [Path(p) for p in document.get("packageFolders", {})]
    libraries = document.get("libraries", {})
    packages: dict[str, AssetPackage] = {}
    for key, entry in document["targets"][target_key].items():
        if entry.get("type") != "package":
            continue
        package_id, version = key.split("/", 1)
        library = libraries.get(key, {})
        folder = _locate(folders, library.get("path", ""))
        packages[package_id.lower()] = AssetPackage(
            package_id,
            version,
            library.get("sha512", ""),
            folder,
            tuple(_real_assets(entry.get("runtime", {}))),
            tuple(_real_assets(entry.get("compile", {}))),
        )
    return Assets(path, target_key, packages, folders)


def _real_assets(items: dict) -> list[str]:
    return sorted(k for k in items if not k.endswith("/_._"))


def _locate(folders: list[Path], library_path: str) -> Path | None:
    for folder in folders:
        candidate = folder / library_path
        if candidate.is_dir():
            return candidate
    return None
