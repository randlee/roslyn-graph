"""Resolve a nuget profile by restoring it in isolation.

A throwaway project with one exact PackageReference is restored against a generated nuget.config
that lists only the profile source and its declared dependency sources, into a private packages folder under the data root. Nothing
depends on the machine's global package cache or configured feeds.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from .config import NugetProfile
from .msbuild import AssetPackage, read_assets
from .result import RgError
from .util import run, sha256_file, sha256_text

SOURCE_KEY = "roslyngraph"
_RESTORE_PROPERTIES = [
    "-p:ImportDirectoryBuildProps=false",
    "-p:ImportDirectoryBuildTargets=false",
    "-p:ImportDirectoryPackagesProps=false",
    "-p:ManagePackageVersionsCentrally=false",
]


@dataclass
class ResolvedPackage:
    profile: str
    id: str
    version: str
    target_framework: str
    source: str
    restored_from: str
    nupkg: Path
    nupkg_sha256: str
    folder: Path
    assets: list[str]  # package-relative runtime DLL paths
    dependencies: list[dict]
    dependencies_hash: str
    search_dirs: list[Path]
    signed: bool

    def to_json(self) -> dict:
        return {
            "profile": self.profile,
            "id": self.id,
            "version": self.version,
            "targetFramework": self.target_framework,
            "source": self.source,
            "restoredFrom": self.restored_from,
            "nupkg": str(self.nupkg),
            "nupkgSha256": self.nupkg_sha256,
            "assets": self.assets,
            "dependencies": self.dependencies,
            "dependenciesHash": self.dependencies_hash,
            "signed": self.signed,
        }


def restore_dir(artifact_root: Path, profile: NugetProfile) -> Path:
    sources = "|".join([profile.source, *profile.dependency_sources])
    key = sha256_text(f"{profile.package.lower()}|{profile.version}|{profile.target_framework}|{sources}")[:16]
    return artifact_root / "cache" / "nuget" / key


def _project_xml(profile: NugetProfile) -> str:
    return f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>{escape(profile.target_framework)}</TargetFramework>
    <RestorePackagesPath>packages</RestorePackagesPath>
    <DisableImplicitNuGetFallbackFolder>true</DisableImplicitNuGetFallbackFolder>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="{escape(profile.package)}" Version="[{escape(profile.version)}]" />
  </ItemGroup>
</Project>
"""


def _nuget_config(profile: NugetProfile) -> str:
    """Only the profile's source and its declared dependency sources; nothing from machine configuration."""
    extra = [s for s in dict.fromkeys(profile.dependency_sources) if s.rstrip("/") != profile.source.rstrip("/")]
    lines = [f'    <add key="{SOURCE_KEY}" value="{escape(profile.source, {chr(34): "&quot;"})}" />']
    lines += [f'    <add key="dependencies{i}" value="{escape(url, {chr(34): "&quot;"})}" />' for i, url in enumerate(extra)]
    body = "\n".join(lines)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
{body}
  </packageSources>
</configuration>
"""


def _restore_env(profile: NugetProfile) -> dict[str, str]:
    env = dict(os.environ)
    if profile.credential_env:
        token = os.environ.get(profile.credential_env)
        if not token:
            raise RgError.of(
                "NUGET_CREDENTIAL_MISSING",
                f"Profile '{profile.name}' needs the environment variable {profile.credential_env}, which is not set.",
                "Set it to a token that can read the feed (for GitHub Packages: a PAT with read:packages).",
                profile=profile.name,
            )
        env[f"NuGetPackageSourceCredentials_{SOURCE_KEY}"] = f"Username=roslyn-graph;Password={token}"
    return env


def restore(profile: NugetProfile, artifact_root: Path) -> ResolvedPackage:
    directory = restore_dir(artifact_root, profile)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "restore.csproj").write_text(_project_xml(profile), encoding="utf-8")
    (directory / "nuget.config").write_text(_nuget_config(profile), encoding="utf-8")
    completed = run(
        ["dotnet", "restore", str(directory / "restore.csproj"), "--configfile", str(directory / "nuget.config"), "--nologo", *_RESTORE_PROPERTIES],
        cwd=directory,
        env=_restore_env(profile),
    )
    nuget_messages = sorted(set(re.findall(r"(?:error|warning) (NU\d{4}): ([^\r\n\[]+)", completed.stdout + completed.stderr)))
    if completed.returncode != 0 or nuget_messages:
        raise RgError.of(
            "NUGET_RESTORE_FAILED",
            f"Isolated restore of {profile.package} {profile.version} did not complete cleanly (exit {completed.returncode}).",
            "NU1101/NU1102: the package, or one of its dependencies, is not on the configured sources; dependencies usually "
            "need dependency_sources (for example https://api.nuget.org/v3/index.json). NU1301/401: credentials. "
            "NU1603/NU1605: a dependency resolved to a different version than requested.",
            profile=profile.name,
            messages=[f"{code}: {text.strip()}" for code, text in nuget_messages] or completed.stdout.splitlines()[-15:],
        )
    return _resolve(profile, directory)


def _resolve(profile: NugetProfile, directory: Path) -> ResolvedPackage:
    assets = read_assets(directory / "obj" / "project.assets.json", profile.target_framework)
    package = assets.packages.get(profile.package.lower())
    if package is None or package.folder is None:
        raise RgError.of("NUGET_PACKAGE_MISSING", f"{profile.package} is not in the restore result.", profile=profile.name)
    if package.version != profile.version:
        raise RgError.of(
            "NUGET_VERSION_MISMATCH",
            f"Restore resolved {profile.package} {package.version}, the profile pins {profile.version}.",
            profile=profile.name,
        )
    runtime = [a for a in package.runtime if a.lower().endswith(".dll")]
    if not runtime:
        raise RgError.of(
            "NUGET_NO_RUNTIME_ASSETS",
            f"{profile.package} {profile.version} has no runtime DLL for {assets.target_key}.",
            "Check target_framework; the package may only ship other frameworks or be a meta-package.",
            profile=profile.name,
            compile=list(package.compile),
        )
    nupkg = package.folder / f"{profile.package.lower()}.{profile.version.lower()}.nupkg"
    nupkg_sha = sha256_file(nupkg)
    if profile.sha256 and nupkg_sha != profile.sha256:
        raise RgError.of(
            "NUGET_HASH_MISMATCH",
            f"{nupkg.name} has SHA-256 {nupkg_sha}; the profile pins {profile.sha256}.",
            "The feed now serves different bytes for the same version. Do not update the pin without investigating.",
            profile=profile.name,
        )
    _check_nuspec(package, profile)
    restored_from = _restored_from(package.folder)
    if restored_from.rstrip("/") != profile.source.rstrip("/"):
        raise RgError.of(
            "NUGET_SOURCE_MISMATCH",
            f"{profile.package} was restored from {restored_from}, not {profile.source}.",
            "Delete the restore cache directory and retry.",
            cache=str(directory),
        )
    dependencies = sorted(
        ({"id": p.id, "version": p.version, "sha512": p.sha512} for key, p in assets.packages.items() if key != profile.package.lower()),
        key=lambda d: d["id"].lower(),
    )
    search_dirs = {package.folder / Path(a).parent for a in runtime}
    for key, dep in assets.packages.items():
        if key != profile.package.lower():
            search_dirs.update(dep.asset_dirs())
    return ResolvedPackage(
        profile=profile.name,
        id=package.id,
        version=package.version,
        target_framework=assets.target_key,
        source=profile.source,
        restored_from=restored_from,
        nupkg=nupkg,
        nupkg_sha256=nupkg_sha,
        folder=package.folder,
        assets=runtime,
        dependencies=dependencies,
        dependencies_hash=sha256_text("\n".join(f"{d['id'].lower()}/{d['version']}:{d['sha512']}" for d in dependencies))[:16],
        search_dirs=sorted(search_dirs, key=str),
        signed=verify_signature(nupkg),
    )


def _check_nuspec(package: AssetPackage, profile: NugetProfile) -> None:
    nuspec = package.folder / f"{profile.package.lower()}.nuspec"
    try:
        metadata = next(n for n in ET.parse(nuspec).getroot().iter() if n.tag.rsplit("}", 1)[-1] == "metadata")
    except (OSError, ET.ParseError, StopIteration) as exc:
        raise RgError.of("NUGET_NUSPEC_UNREADABLE", f"Cannot read {nuspec}: {exc}", profile=profile.name) from exc
    fields = {n.tag.rsplit("}", 1)[-1]: (n.text or "").strip() for n in metadata}
    if fields.get("id", "").lower() != profile.package.lower() or fields.get("version") != profile.version:
        raise RgError.of(
            "NUGET_NUSPEC_MISMATCH",
            f"{nuspec.name} declares {fields.get('id')} {fields.get('version')}, expected {profile.package} {profile.version}.",
            profile=profile.name,
        )


def _restored_from(folder: Path) -> str:
    try:
        return json.loads((folder / ".nupkg.metadata").read_text(encoding="utf-8"))["source"]
    except (OSError, KeyError, json.JSONDecodeError):
        return ""


def verify_signature(nupkg: Path) -> bool:
    completed = run(["dotnet", "nuget", "verify", str(nupkg), "--all"])
    if completed.returncode == 0:
        return True
    if "NU3004" in completed.stdout + completed.stderr:
        return False  # unsigned: recorded, not an error
    raise RgError.of(
        "NUGET_SIGNATURE_INVALID",
        f"{nupkg.name} is signed but its signature does not verify.",
        "Do not snapshot this package until the signature problem is understood.",
        output=(completed.stdout + completed.stderr).splitlines()[-15:],
    )
