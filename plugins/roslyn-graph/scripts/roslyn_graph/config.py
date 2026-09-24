"""workspace.toml schema version 1: load, validate and resolve paths.

Relative paths are resolved against the directory that contains workspace.toml; project-keyed
tables (outputs, assembly_names) and collect lists use paths relative to the profile root.
See reference/workspace-toml.md for the full schema.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .result import ProblemList, RgError
from .util import full_path, sha256_file

SCHEMA_VERSION = 1
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_VERSION = re.compile(r"^\d+(\.\d+){1,3}(-[0-9A-Za-z.-]+)?$")


@dataclass
class SolutionProfile:
    name: str
    root: Path
    solution: Path
    output_dir: Path
    configuration: str
    target_framework: str
    platform: str
    fingerprint_files: list[Path]
    search_dirs: list[Path]
    all_solution_projects: bool
    projects: list[str]
    exclude: list[str]
    packages: list[str]
    outputs: dict[str, Path]
    assembly_names: dict[str, str]
    kind: str = "solution"


@dataclass
class NugetProfile:
    name: str
    package: str
    version: str
    target_framework: str
    source: str
    dependency_sources: list[str]
    credential_env: str
    sha256: str
    kind: str = "nuget"


@dataclass
class Collection:
    name: str
    base: str
    overlays: list[str]
    policy: str


@dataclass
class Workspace:
    path: Path
    sha256: str
    oxigraph: str
    profiles: dict[str, SolutionProfile | NugetProfile]
    collections: dict[str, Collection]
    policies: dict[str, list[str]] = field(default_factory=dict)

    @property
    def directory(self) -> Path:
        return self.path.parent


class _Reader:
    """Typed accessors that record a problem instead of raising, so one run reports every mistake."""

    def __init__(self, problems: ProblemList, source: Path):
        self.problems = problems
        self.source = source

    def _bad(self, key: str, message: str, hint: str) -> None:
        self.problems.add("TOML_INVALID", f"{key}: {message}", hint, file=str(self.source), key=key)

    def table(self, data: dict, key: str, path: str, required: bool = False) -> dict:
        value = data.get(key)
        if value is None:
            if required:
                self._bad(f"{path}.{key}".lstrip("."), "required table is missing", f"Add a [{path}.{key}] table.".replace("[.", "["))
            return {}
        if not isinstance(value, dict):
            self._bad(f"{path}.{key}", "must be a table", "Use a [table] header.")
            return {}
        return value

    def string(self, data: dict, key: str, path: str, required: bool = True, default: str = "") -> str:
        value = data.get(key)
        if value is None:
            if required:
                self._bad(f"{path}.{key}", "required string is missing", f"Add {key} = \"...\" to [{path}].")
            return default
        if not isinstance(value, str) or not value.strip():
            self._bad(f"{path}.{key}", "must be a non-empty string", "Quote the value.")
            return default
        return value.strip()

    def boolean(self, data: dict, key: str, path: str, default: bool = False) -> bool:
        value = data.get(key, default)
        if not isinstance(value, bool):
            self._bad(f"{path}.{key}", "must be true or false", "")
            return default
        return value

    def strings(self, data: dict, key: str, path: str) -> list[str]:
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            self._bad(f"{path}.{key}", "must be an array of non-empty strings", 'Example: ["a", "b"].')
            return []
        return [v.strip() for v in value]

    def string_map(self, data: dict, key: str, path: str) -> dict[str, str]:
        value = self.table(data, key, path)
        result = {}
        for k, v in value.items():
            if not isinstance(v, str) or not v.strip():
                self._bad(f"{path}.{key}.\"{k}\"", "must be a non-empty string", "")
            else:
                result[k.replace("\\", "/")] = v.strip()
        return result

    def unknown(self, data: dict, allowed: set[str], path: str) -> None:
        for key in sorted(set(data) - allowed):
            self._bad(f"{path}.{key}".lstrip("."), "unknown key", f"Allowed keys: {', '.join(sorted(allowed))}.")


def load(path: Path) -> Workspace:
    path = full_path(path)
    if not path.is_file():
        raise RgError.of(
            "WORKSPACE_NOT_FOUND",
            f"workspace.toml does not exist: {path}",
            "Create one with the design-toml workflow.",
        )
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise RgError.of("TOML_SYNTAX", f"{path}: {exc}", "Fix the TOML syntax at the reported line and column.") from exc
    return parse(data, path)


def parse(data: dict[str, Any], path: Path) -> Workspace:
    problems = ProblemList()
    r = _Reader(problems, path)
    base_dir = path.parent

    r.unknown(data, {"schema_version", "tools", "profiles", "collections", "policies"}, "")
    if data.get("schema_version") != SCHEMA_VERSION:
        problems.add(
            "TOML_SCHEMA_VERSION",
            f"schema_version must be {SCHEMA_VERSION}, found {data.get('schema_version')!r}.",
            "Rewrite the file with the design-toml workflow; reference/workspace-toml.md documents every key.",
            file=str(path),
        )

    tools = r.table(data, "tools", "", required=True)
    r.unknown(tools, {"oxigraph"}, "tools")
    oxigraph = r.string(tools, "oxigraph", "tools")

    profiles: dict[str, SolutionProfile | NugetProfile] = {}
    for name, raw in r.table(data, "profiles", "", required=True).items():
        where = f"profiles.{name}"
        if not _NAME.match(name):
            problems.add("TOML_INVALID", f"{where}: profile names use letters, digits, '_' and '-'", "", key=where)
            continue
        if not isinstance(raw, dict):
            problems.add("TOML_INVALID", f"{where}: must be a table", "", key=where)
            continue
        kind = raw.get("kind", "solution")
        if kind == "nuget":
            profiles[name] = _nuget(r, raw, name, where)
        elif kind == "solution":
            profiles[name] = _solution(r, raw, name, where, base_dir)
        else:
            problems.add("TOML_INVALID", f"{where}.kind must be \"solution\" or \"nuget\", found {kind!r}", "", key=f"{where}.kind")

    policies: dict[str, list[str]] = {}
    for name, raw in r.table(data, "policies", "").items():
        where = f"policies.{name}"
        if not isinstance(raw, dict):
            problems.add("TOML_INVALID", f"{where}: must be a table", "", key=where)
            continue
        r.unknown(raw, {"assemblies"}, where)
        assemblies = r.strings(raw, "assemblies", where)
        if not assemblies:
            problems.add("TOML_INVALID", f"{where}.assemblies must list at least one assembly name", "", key=where)
        policies[name] = assemblies

    collections: dict[str, Collection] = {}
    for name, raw in r.table(data, "collections", "").items():
        where = f"collections.{name}"
        if not isinstance(raw, dict):
            problems.add("TOML_INVALID", f"{where}: must be a table", "", key=where)
            continue
        r.unknown(raw, {"base", "overlays", "logical_type_policy"}, where)
        collection = Collection(
            name, r.string(raw, "base", where), r.strings(raw, "overlays", where), r.string(raw, "logical_type_policy", where, required=False)
        )
        _check_collection(problems, collection, profiles, policies, where)
        collections[name] = collection

    for profile in profiles.values():
        if isinstance(profile, SolutionProfile):
            repeated = sorted({p for p in profile.packages if profile.packages.count(p) > 1})
            if repeated:
                problems.add("TOML_INVALID", f"profiles.{profile.name}.collect.packages lists {repeated} more than once", "List each package once.",
                             key=f"profiles.{profile.name}.collect.packages")
            for package in profile.packages:
                target = profiles.get(package)
                if not isinstance(target, NugetProfile):
                    problems.add(
                        "TOML_INVALID",
                        f"profiles.{profile.name}.collect.packages references '{package}', which is not a nuget profile",
                        "List the names of [profiles.<name>] tables with kind = \"nuget\".",
                        key=f"profiles.{profile.name}.collect.packages",
                    )

    problems.raise_if_any()
    return Workspace(path, sha256_file(path), oxigraph, profiles, collections, policies)


def _solution(r: _Reader, raw: dict, name: str, where: str, base_dir: Path) -> SolutionProfile:
    r.unknown(
        raw,
        {"kind", "root", "solution", "output_dir", "fingerprint_files", "search_dirs", "build", "collect", "outputs", "assembly_names"},
        where,
    )
    root = full_path(r.string(raw, "root", where, default="."), base_dir)
    build = r.table(raw, "build", where, required=True)
    r.unknown(build, {"configuration", "target_framework", "platform"}, f"{where}.build")
    collect = r.table(raw, "collect", where, required=True)
    r.unknown(collect, {"all_solution_projects", "projects", "exclude", "packages"}, f"{where}.collect")
    all_projects = r.boolean(collect, "all_solution_projects", f"{where}.collect")
    projects = [p.replace("\\", "/") for p in r.strings(collect, "projects", f"{where}.collect")]
    if all_projects == bool(projects):
        r._bad(
            f"{where}.collect",
            "set exactly one of all_solution_projects = true or projects = [...]",
            "Every profile needs an explicit collection scope.",
        )
    return SolutionProfile(
        name=name,
        root=root,
        solution=full_path(r.string(raw, "solution", where, default="."), root),
        output_dir=full_path(r.string(raw, "output_dir", where, default="."), root),
        configuration=r.string(build, "configuration", f"{where}.build"),
        target_framework=r.string(build, "target_framework", f"{where}.build"),
        platform=r.string(build, "platform", f"{where}.build", required=False),
        fingerprint_files=[full_path(p, root) for p in r.strings(raw, "fingerprint_files", where)],
        search_dirs=[full_path(p, root) for p in r.strings(raw, "search_dirs", where)],
        all_solution_projects=all_projects,
        projects=projects,
        exclude=[p.replace("\\", "/") for p in r.strings(collect, "exclude", f"{where}.collect")],
        packages=r.strings(collect, "packages", f"{where}.collect"),
        outputs={k: full_path(v, root) for k, v in r.string_map(raw, "outputs", where).items()},
        assembly_names=r.string_map(raw, "assembly_names", where),
    )


def _nuget(r: _Reader, raw: dict, name: str, where: str) -> NugetProfile:
    r.unknown(raw, {"kind", "package", "version", "target_framework", "source", "dependency_sources", "credential_env", "sha256"}, where)
    version = r.string(raw, "version", where)
    if version and not _VERSION.match(version):
        r._bad(f"{where}.version", f"'{version}' is not an exact package version", "Ranges and floating versions are not allowed.")
    sha = r.string(raw, "sha256", where, required=False).lower()
    if sha and not re.fullmatch(r"[0-9a-f]{64}", sha):
        r._bad(f"{where}.sha256", "must be 64 hexadecimal characters", "Copy the value the generate report printed.")
    credential = r.string(raw, "credential_env", where, required=False)
    if credential and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", credential):
        r._bad(f"{where}.credential_env", "must be an environment variable name, never the secret itself", "")
    return NugetProfile(
        name=name,
        package=r.string(raw, "package", where),
        version=version,
        target_framework=r.string(raw, "target_framework", where),
        source=r.string(raw, "source", where),
        dependency_sources=r.strings(raw, "dependency_sources", where),
        credential_env=credential,
        sha256=sha,
    )


def _check_collection(problems: ProblemList, c: Collection, profiles: dict, policies: dict, where: str) -> None:
    if c.base and c.base not in profiles:
        problems.add("TOML_INVALID", f"{where}.base '{c.base}' is not a profile", f"Known profiles: {', '.join(sorted(profiles))}.", key=where)
    for overlay in c.overlays:
        if overlay not in profiles:
            problems.add("TOML_INVALID", f"{where}.overlays '{overlay}' is not a profile", "", key=where)
        if overlay == c.base:
            problems.add("TOML_INVALID", f"{where}: '{overlay}' is both base and overlay", "", key=where)
    if c.overlays and not c.policy:
        problems.add(
            "TOML_INVALID",
            f"{where}: a collection with overlays needs logical_type_policy",
            "Name a [policies.<name>] table listing the assemblies whose versions may be reconciled.",
            key=where,
        )
    if c.policy and c.policy not in policies:
        problems.add("TOML_INVALID", f"{where}.logical_type_policy '{c.policy}' is not defined under [policies]", "", key=where)
