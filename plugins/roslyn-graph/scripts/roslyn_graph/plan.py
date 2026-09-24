"""Resolve a workspace collection into an exact, reviewable plan.

The plan names every DLL, its provenance, search directories, artifact ID and destination. Solution
profiles are checked against their build output (build check); nuget profiles are restored in
isolation. The only write is the NuGet restore cache under <artifact-root>/cache.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import artifacts, extractor, gitinfo, msbuild, nuget, oxigraph
from .config import Collection, NugetProfile, SolutionProfile, Workspace
from .result import ProblemList, RgError
from .util import full_path, rel_posix, sha256_file, sha256_text

SOURCE_EXTENSIONS = {".cs", ".csproj", ".props", ".targets", ".resx", ".xaml", ".settings", ".config", ".json", ".editorconfig"}
SKIP_DIRS = {"bin", "obj", ".git", ".vs", "node_modules", "TestResults"}


@dataclass
class Component:
    profile: str
    role: str  # "base" or "overlay"
    assembly_path: Path
    expected_name: str
    search_dirs: list[Path]
    manifest: dict[str, Any]  # partial manifest: origin/build or package, assembly.sha256, extraction.extractorId
    artifact_id: str = ""
    destination: Path | None = None
    exists: bool = False

    def to_json(self, root: Path) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "role": self.role,
            "assemblyPath": str(self.assembly_path),
            "expectedName": self.expected_name,
            "artifactId": self.artifact_id,
            "destination": artifacts.relative(root, self.destination) if self.destination else None,
            "exists": self.exists,
            "searchDirs": [str(d) for d in self.search_dirs],
            "origin": self.manifest.get("origin"),
            "package": self.manifest.get("package"),
        }


@dataclass
class Plan:
    workspace: Workspace
    collection: Collection
    root: Path
    extractor: extractor.Extractor
    oxigraph_version: str
    components: list[Component] = field(default_factory=list)
    solution: dict[str, Any] = field(default_factory=dict)
    view: dict[str, Any] | None = None
    packages: list[nuget.ResolvedPackage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def base_components(self) -> list[Component]:
        return [c for c in self.components if c.role == "base"]

    def overlay_components(self) -> list[Component]:
        return [c for c in self.components if c.role == "overlay"]

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "plan",
            "workspace": {"path": str(self.workspace.path), "sha256": self.workspace.sha256},
            "collection": self.collection.name,
            "artifactRoot": str(self.root),
            "extractor": self.extractor.to_json(),
            "oxigraph": self.oxigraph_version,
            "summary": {
                "components": len(self.components),
                "new": sum(not c.exists for c in self.components),
                "reused": sum(c.exists for c in self.components),
                "solutionExists": self.solution.get("exists"),
                "viewExists": self.view.get("exists") if self.view else None,
            },
            "solution": {k: v for k, v in self.solution.items() if k != "manifest"} | {"identityFields": self.solution["manifest"]["solution"]},
            "view": ({k: v for k, v in self.view.items() if k != "manifest"} if self.view else None),
            "packages": [p.to_json() for p in self.packages],
            "components": [c.to_json(self.root) for c in self.components],
            "warnings": self.warnings,
        }


def build_plan(workspace: Workspace, collection_name: str, data_root: str | None, allow_dirty: bool = False) -> Plan:
    collection = workspace.collections.get(collection_name)
    if collection is None:
        raise RgError.of(
            "COLLECTION_NOT_FOUND",
            f"Collection '{collection_name}' is not defined in {workspace.path}.",
            f"Known collections: {', '.join(sorted(workspace.collections)) or '(none)'}.",
        )
    root = artifacts.artifact_root(data_root)
    problems = ProblemList()

    ox_version = oxigraph.version()
    if ox_version != workspace.oxigraph:
        problems.add(
            "OXIGRAPH_VERSION_MISMATCH",
            f"Oxigraph {ox_version} is installed; workspace.toml requires {workspace.oxigraph}.",
            "Install the required version (cargo install oxigraph-cli --version <v>) or update [tools].oxigraph deliberately.",
        )
    tool = extractor.resolve()
    plan = Plan(workspace, collection, root, tool, ox_version)

    resolved: dict[str, nuget.ResolvedPackage] = {}

    def package(name: str) -> nuget.ResolvedPackage | None:
        if name not in resolved:
            try:
                resolved[name] = nuget.restore(workspace.profiles[name], root)
                plan.packages.append(resolved[name])
            except RgError as exc:
                problems.extend(exc)
                return None
        return resolved[name]

    for role, profile_name in [("base", collection.base)] + [("overlay", o) for o in collection.overlays]:
        profile = workspace.profiles[profile_name]
        try:
            if isinstance(profile, SolutionProfile):
                plan.components += _solution_components(profile, role, tool, allow_dirty, problems)
                for package_name in profile.packages:
                    pkg = package(package_name)
                    if pkg:
                        _check_consumed(profile, workspace.profiles[package_name], pkg, problems)
                        plan.components += _package_components(pkg, role, tool)
            else:
                pkg = package(profile_name)
                if pkg:
                    plan.components += _package_components(pkg, role, tool)
        except RgError as exc:
            problems.extend(exc)

    problems.raise_if_any()
    _dedupe(plan)
    for component in plan.components:
        _finalize_component(root, component)
    _plan_solution(plan)
    if collection.overlays:
        _plan_view(plan, problems)
    problems.raise_if_any()
    return plan


# ---- solution profiles ---------------------------------------------------------------------


def fingerprint(profile: SolutionProfile) -> str:
    files = []
    for path in sorted(profile.fingerprint_files, key=lambda p: str(p).lower()):
        if not path.is_file():
            raise RgError.of("FINGERPRINT_FILE_MISSING", f"fingerprint_files entry does not exist: {path}", profile=profile.name)
        files.append(f"{rel_posix(path, profile.root)}:{sha256_file(path)}")
    digest = sha256_text("|".join(["fingerprint/v1", profile.configuration, profile.target_framework, profile.platform, *files]))[:16]
    readable = "-".join(p for p in [profile.configuration, profile.target_framework, profile.platform] if p).lower()
    return f"{readable}-{digest}"


def select_projects(profile: SolutionProfile, projects: list[msbuild.SolutionProject], problems: ProblemList) -> list[msbuild.SolutionProject]:
    by_rel = {rel_posix(p.path, profile.root): p for p in projects}
    if profile.all_solution_projects:
        chosen = dict(by_rel)
    else:
        chosen = {}
        for rel in profile.projects:
            if rel in by_rel:
                chosen[rel] = by_rel[rel]
            else:
                problems.add(
                    "PROJECT_NOT_IN_SOLUTION",
                    f"profiles.{profile.name}.collect.projects lists '{rel}', which is not in {profile.solution.name}.",
                    "Paths are relative to the profile root, with forward slashes.",
                    known=sorted(by_rel),
                )
    for rel in profile.exclude:
        if chosen.pop(rel, None) is None:
            problems.add("EXCLUDE_NOT_SELECTED", f"profiles.{profile.name}.collect.exclude lists '{rel}', which is not selected.", "")
    return [chosen[k] for k in sorted(chosen)]


def newest_input(project_dir: Path) -> tuple[float, Path | None]:
    newest, newest_path = 0.0, None
    for dirpath, dirnames, filenames in os.walk(project_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if Path(name).suffix.lower() in SOURCE_EXTENSIONS:
                path = Path(dirpath) / name
                mtime = path.stat().st_mtime
                if mtime > newest:
                    newest, newest_path = mtime, path
    return newest, newest_path


def _solution_components(profile: SolutionProfile, role: str, tool: extractor.Extractor, allow_dirty: bool, problems: ProblemList) -> list[Component]:
    projects = select_projects(profile, msbuild.read_solution(profile.solution), problems)
    fp = fingerprint(profile)
    fingerprint_mtime = max((p.stat().st_mtime for p in profile.fingerprint_files), default=0.0)
    components = []
    for project in projects:
        rel = rel_posix(project.path, profile.root)
        try:
            name = profile.assembly_names.get(rel) or msbuild.read_project(project.path).assembly_name
        except RgError as exc:
            problems.extend(exc)
            continue
        output_dir = profile.outputs.get(rel, profile.output_dir)
        dll = output_dir / f"{name}.dll"
        if not dll.is_file():
            problems.add(
                "BUILD_OUTPUT_MISSING",
                f"{rel}: expected build output {dll} does not exist.",
                "Build the solution successfully first. If this project writes elsewhere, add it under "
                f"[profiles.{profile.name}.outputs]; if it should not be collected, add it to collect.exclude.",
                project=rel,
            )
            continue
        dll_mtime = dll.stat().st_mtime
        newest, newest_path = newest_input(project.path.parent)
        if max(newest, fingerprint_mtime) > dll_mtime:
            stale_source = newest_path if newest >= fingerprint_mtime else "a fingerprint file"
            problems.add(
                "BUILD_OUTPUT_STALE",
                f"{rel}: {dll.name} is older than {stale_source}.",
                "Rebuild the solution; the skill only snapshots outputs built from the current sources.",
                dll=str(dll),
                dllTime=_iso(dll_mtime),
                sourceTime=_iso(max(newest, fingerprint_mtime)),
            )
            continue
        repo = gitinfo.repo_state(project.path.parent)
        if repo.dirty and not allow_dirty:
            problems.add(
                "SOURCE_DIRTY",
                f"{repo.name} has uncommitted changes, so its commit does not describe {dll.name}.",
                "Commit or stash the changes and rebuild, or pass --allow-dirty to record a dirty-state hash in the identity.",
                repository=str(repo.root),
            )
            continue
        search = [dll.parent, profile.output_dir, *profile.search_dirs]
        assets_file = msbuild.assets_path(project.path)
        if assets_file.is_file():
            try:
                for pkg in msbuild.read_assets(assets_file, profile.target_framework).packages.values():
                    search.extend(pkg.asset_dirs())
            except RgError as exc:
                problems.extend(exc)
        manifest = {
            "origin": {
                "kind": "source", "id": repo.name, "repository": str(repo.root), "branch": repo.branch,
                "commit": repo.commit, "commitTime": repo.commit_time, "dirtyHash": repo.dirty_hash,
            },
            "build": {
                "profile": profile.name, "fingerprint": fp, "configuration": profile.configuration,
                "targetFramework": profile.target_framework, "platform": profile.platform,
                "project": rel, "solution": rel_posix(profile.solution, profile.root),
            },
            "assembly": {"inputPath": str(dll), "sha256": sha256_file(dll), "expectedName": name},
            "extraction": {"extractorId": tool.id},
        }
        components.append(Component(profile.name, role, dll, name, _unique(search), manifest))
    return components


def _check_consumed(profile: SolutionProfile, package_profile: NugetProfile, pkg: nuget.ResolvedPackage, problems: ProblemList) -> None:
    versions: dict[str, set[str]] = {}
    for project in msbuild.read_solution(profile.solution):
        path = msbuild.assets_path(project.path)
        if path.is_file():
            entry = msbuild.read_assets(path, profile.target_framework).packages.get(pkg.id.lower())
            if entry:
                versions.setdefault(entry.version, set()).add(project.name)
    if not versions:
        problems.add(
            "PACKAGE_NOT_CONSUMED",
            f"profiles.{profile.name} lists package '{package_profile.name}' but no project restored {pkg.id}.",
            "Remove it from collect.packages or restore the solution.",
        )
    elif set(versions) != {pkg.version}:
        problems.add(
            "PACKAGE_VERSION_DRIFT",
            f"{profile.name} restored {pkg.id} {sorted(versions)}; profile '{package_profile.name}' pins {pkg.version}.",
            "Update the nuget profile's version (and drop its sha256 pin) to match what the solution consumed.",
            consumers={v: sorted(p) for v, p in versions.items()},
        )
    for asset in pkg.assets:
        copied = profile.output_dir / Path(asset).name
        if copied.is_file() and sha256_file(copied) != sha256_file(pkg.folder / asset):
            problems.add(
                "PACKAGE_OUTPUT_DIFFERS",
                f"{copied} differs from {asset} in {pkg.id} {pkg.version}.",
                "The build output did not come from this package version; rebuild after restore.",
            )


# ---- nuget profiles ------------------------------------------------------------------------


def _package_components(pkg: nuget.ResolvedPackage, role: str, tool: extractor.Extractor) -> list[Component]:
    components = []
    for asset in pkg.assets:
        dll = pkg.folder / asset
        manifest = {
            "origin": {"kind": "nuget", "id": pkg.id},
            "package": {
                "profile": pkg.profile, "id": pkg.id, "version": pkg.version, "source": pkg.source,
                "nupkgSha256": pkg.nupkg_sha256, "asset": asset, "targetFramework": pkg.target_framework,
                "dependencies": pkg.dependencies, "dependenciesHash": pkg.dependencies_hash, "signed": pkg.signed,
            },
            "assembly": {"inputPath": str(dll), "sha256": sha256_file(dll), "expectedName": Path(asset).stem},
            "extraction": {"extractorId": tool.id},
        }
        components.append(Component(pkg.profile, role, dll, Path(asset).stem, _unique([dll.parent, *pkg.search_dirs]), manifest))
    return components


# ---- identities ----------------------------------------------------------------------------


def _dedupe(plan: Plan) -> None:
    seen: dict[str, Component] = {}
    unique = []
    for component in plan.components:
        key = f"{component.role}|{component.assembly_path}"
        if key not in seen:
            seen[key] = component
            unique.append(component)
    plan.components = unique


def _finalize_component(root: Path, c: Component) -> None:
    c.artifact_id = artifacts.artifact_id(artifacts.assembly_identity(c.manifest))
    if c.manifest["origin"]["kind"] == "source":
        base = artifacts.base_dir(root, "assembly-source", origin=c.manifest["origin"]["id"])
    else:
        base = artifacts.base_dir(root, "assembly-nuget", package=c.manifest["package"]["id"], version=c.manifest["package"]["version"])
    c.destination, c.exists = artifacts.resolve_destination(base, c.artifact_id)
    artifacts.check_path_length(c.destination)


def _plan_solution(plan: Plan) -> None:
    base = plan.workspace.profiles[plan.collection.base]
    comps = plan.base_components()
    if isinstance(base, SolutionProfile):
        repo = gitinfo.repo_state(base.solution.parent)
        fields = {
            "profile": base.name, "name": base.solution.stem, "repository": base.root.name,
            "relativePath": rel_posix(base.solution, base.root), "path": str(base.solution),
            "branch": repo.branch, "commit": repo.commit, "dirtyHash": repo.dirty_hash,
            "fingerprint": fingerprint(base), "targetFramework": base.target_framework,
            "configuration": base.configuration, "platform": base.platform,
            "fingerprintFiles": [rel_posix(p, base.root) for p in base.fingerprint_files],
        }
    else:
        pkg = next(p for p in plan.packages if p.profile == base.name)
        fields = {
            "profile": base.name, "name": pkg.id, "repository": "nuget", "relativePath": "", "path": "",
            "branch": "", "commit": "", "dirtyHash": "", "fingerprint": f"nuget-{pkg.version}",
            "targetFramework": pkg.target_framework, "configuration": "package", "platform": "",
            "fingerprintFiles": [],
        }
    manifest = {"solution": fields, "components": [{"artifactId": c.artifact_id} for c in comps]}
    full_id = artifacts.artifact_id(artifacts.solution_identity(manifest))
    destination, exists = artifacts.resolve_destination(
        artifacts.base_dir(plan.root, "solution", repository=fields["repository"], name=fields["name"]), full_id
    )
    artifacts.check_path_length(destination)
    plan.solution = {"artifactId": full_id, "destination": artifacts.relative(plan.root, destination), "exists": exists, "manifest": manifest}


def _plan_view(plan: Plan, problems: ProblemList) -> None:
    policy_assemblies = plan.workspace.policies[plan.collection.policy]
    overlays = plan.overlay_components()
    for c in overlays:
        if c.expected_name not in policy_assemblies:
            problems.add(
                "OVERLAY_NOT_IN_POLICY",
                f"Overlay assembly {c.expected_name} (profile {c.profile}) is not covered by policy '{plan.collection.policy}'.",
                f"Add it to [policies.{plan.collection.policy}].assemblies or remove the overlay.",
            )
    base_names = {c.expected_name for c in plan.base_components()}
    missing = [a for a in policy_assemblies if a not in base_names]
    if missing:
        plan.warnings.append(f"Policy assemblies not present in the base solution: {', '.join(missing)}.")
    manifest = {
        "view": {
            "baseSolutionArtifactId": plan.solution["artifactId"], "policy": plan.collection.policy,
            "policyAssemblies": sorted(policy_assemblies), "projectionVersion": artifacts.PROJECTION_VERSION,
        },
        "overlayComponents": [{"artifactId": c.artifact_id} for c in overlays],
    }
    full_id = artifacts.artifact_id(artifacts.view_identity(manifest))
    destination, exists = artifacts.resolve_destination(artifacts.base_dir(plan.root, "view"), full_id)
    artifacts.check_path_length(destination)
    plan.view = {"artifactId": full_id, "destination": artifacts.relative(plan.root, destination), "exists": exists, "manifest": manifest}


def _unique(paths: list[Path]) -> list[Path]:
    seen, result = set(), []
    for path in paths:
        key = str(full_path(path)).lower()
        if key not in seen and Path(path).is_dir():
            seen.add(key)
            result.append(full_path(path))
    return result


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
