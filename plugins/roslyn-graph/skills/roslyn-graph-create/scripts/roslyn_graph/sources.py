"""Source locator: the files that declare exported types, resolved on export from the build that made the store.

For each source project behind the exported types:

1. the component manifest gives the repository, commit and build (project, solution, configuration, target
   framework, platform);
2. the checkout must still be at that commit, without new changes (``SOURCE_CHECKOUT_DRIFT`` unless allowed);
3. MSBuild lists the Compile items and the preprocessor symbols, evaluated with the solution context and the
   SDK's implicit symbols, exactly as the build saw them;
4. the extractor's ``declarations`` command parses those files with Roslyn and lists every declared named type,
   named as the extractor names compiled types;
5. the index is cached by repository, commit, project and build, because a clean commit's index never changes.

See the explore skill's reference/records.md (Source locations).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import extractor, gitinfo
from .result import RgError
from .util import run, sha256_text

CACHE_VERSION = "source-index/v1"
STATUSES = ("found", "compiler-generated", "generated", "nuget")  # priority when a logical type has several versions
MSBUILD_JOBS = 4
MSBUILD_TIMEOUT = 600
PROPERTIES = ("DefineConstants", "FinalDefineConstants", "LangVersion", "Language", "RootNamespace")


def msbuild_command() -> list[str]:
    """ROSLYN_GRAPH_MSBUILD: an MSBuild executable, or a dotnet executable (then `dotnet msbuild`)."""
    value = os.environ.get("ROSLYN_GRAPH_MSBUILD", "")
    if not value:
        return ["dotnet", "msbuild"]
    return [value, "msbuild"] if Path(value).stem.lower() == "dotnet" else [value]


# ---- names ----------------------------------------------------------------------------------


def segments(full: str) -> list[str]:
    """Dot-separated name segments, ignoring dots inside generic argument lists."""
    out, depth, current = [], 0, ""
    for ch in full:
        depth += ch == "<"
        depth -= ch == ">"
        if ch == "." and depth == 0:
            out.append(current)
            current = ""
        else:
            current += ch
    out.append(current)
    return out


def compiler_generated(full: str) -> bool:
    """A segment starting with '<': display classes, state machines, <PrivateImplementationDetails>."""
    return any(s.startswith("<") for s in segments(full))


def source_owner(full: str) -> str:
    """The named type enclosing a compiler-generated type (empty when there is none)."""
    keep = []
    for s in segments(full):
        if s.startswith("<"):
            break
        keep.append(s)
    return ".".join(keep)


# ---- projects -------------------------------------------------------------------------------


@dataclass
class Project:
    """One source component's project, as built for the store."""

    graph: str
    repository_id: str
    repository: Path  # the checkout, after --repo-root
    recorded_repository: str
    commit: str
    dirty_hash: str
    relative: str  # repository-relative project path
    build: dict[str, Any]
    solution: Path | None = None
    drift: str | None = None
    index: dict[str, list[str]] = field(default_factory=dict)  # full name -> repo-relative files
    cached: bool = False
    language_version: str = ""
    symbols: list[str] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return self.repository / self.relative

    def to_json(self) -> dict[str, Any]:
        return {"repository": self.repository_id, "project": self.relative, "checkout": str(self.repository), "commit": self.commit,
                "drift": self.drift, "cached": self.cached, "declaredTypes": len(self.index), "languageVersion": self.language_version}


def _locate(repository: Path, recorded: str, relative: str) -> Path | None:
    """A profile-root-relative path (assembly/v2) or a repository-relative one: the first that exists.

    Profile-root paths start with the recorded checkout's folder name, which a moved checkout (--repo-root) may
    not share, so that prefix is stripped rather than resolved against the new checkout's parent.
    """
    prefix = Path(recorded).name + "/"
    candidates = [repository / relative[len(prefix):]] if relative.startswith(prefix) else []
    if repository == Path(recorded):
        candidates.insert(0, repository.parent / relative)
    for candidate in candidates + [repository / relative]:
        if candidate.is_file():
            return candidate
    return None


def project_for(graph: str, component: dict[str, Any], relative: str, repo_roots: dict[str, Path]) -> Project:
    """relative: the project's repository-relative path, computed from the component as recorded (records.project_path)."""
    origin = component["origin"]
    recorded = origin["repository"]
    repository = repo_roots.get(origin["id"], Path(recorded))
    build = component.get("build") or {}
    solution = _locate(repository, recorded, build["solution"].replace("\\", "/")) if build.get("solution") else None
    return Project(graph, origin["id"], repository, recorded, origin.get("commit", ""), origin.get("dirtyHash", ""), relative, build,
                   solution)


def check_checkout(p: Project) -> None:
    """Sets p.drift when the checkout is not the one the store was built from."""
    if not p.repository.is_dir():
        raise RgError.of("SOURCE_CHECKOUT_MISSING", f"Repository '{p.repository_id}' is not at {p.repository}.",
                         f"Pass --repo-root {p.repository_id}=<path> if the checkout has moved.", repository=p.repository_id)
    state = gitinfo.repo_state(p.repository)
    if state.commit != p.commit:
        p.drift = f"checkout is at {state.commit[:12]}, the store was built from {p.commit[:12]}"
    elif state.dirty_hash != p.dirty_hash:
        p.drift = "the checkout has uncommitted changes" if not p.dirty_hash else "the checkout's uncommitted changes differ from the build's"


def msbuild_args(p: Project) -> list[str]:
    b = p.build
    args = [*msbuild_command(), str(p.path), "-nologo", "-getItem:Compile", *(f"-getProperty:{n}" for n in PROPERTIES),
            "-t:AddImplicitDefineConstants"]
    for name, key in (("Configuration", "configuration"), ("TargetFramework", "targetFramework"), ("Platform", "platform")):
        if b.get(key):
            args.append(f"-p:{name}={b[key]}")
    if p.solution:
        # Solution builds set these, and projects import files through them ($(SolutionDir)Common.targets).
        s = p.solution
        args += [f"-p:SolutionDir={s.parent}{os.sep}", f"-p:SolutionPath={s}", f"-p:SolutionName={s.stem}",
                 f"-p:SolutionFileName={s.name}", f"-p:SolutionExt={s.suffix}"]
    return args


def _parse_msbuild(stdout: str) -> dict[str, Any]:
    start = stdout.find("{")
    if start < 0:
        raise ValueError("no JSON in the output")
    return json.loads(stdout[start:])


def evaluate(p: Project) -> tuple[list[Path], dict[str, str]]:
    """The project's Compile items (absolute) and evaluated properties."""
    args = msbuild_args(p)
    try:
        completed = run(args, cwd=p.path.parent, timeout=MSBUILD_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise RgError.of("MSBUILD_FAILED", f"MSBuild did not finish within {MSBUILD_TIMEOUT} s for {p.relative}.", project=str(p.path)) from exc
    output = (completed.stdout + completed.stderr).splitlines()
    if completed.returncode != 0 and any("MSB4057" in line for line in output):
        # A project without the SDK has no AddImplicitDefineConstants target; it has no implicit symbols either.
        args = [a for a in args if a != "-t:AddImplicitDefineConstants"]
        completed = run(args, cwd=p.path.parent, timeout=MSBUILD_TIMEOUT)
        output = (completed.stdout + completed.stderr).splitlines()
    try:
        if completed.returncode != 0:
            raise ValueError(f"exit {completed.returncode}")
        document = _parse_msbuild(completed.stdout)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RgError.of("MSBUILD_FAILED", f"MSBuild could not evaluate {p.relative} ({exc}).",
                         "Read 'output'. The project must restore and build in this checkout; ROSLYN_GRAPH_MSBUILD selects MSBuild "
                         "(Visual Studio MSBuild 17.8+ for non-SDK projects).",
                         project=str(p.path), args=args, output=output[-25:]) from exc
    items = [Path(i.get("FullPath") or (p.path.parent / i["Identity"])) for i in document.get("Items", {}).get("Compile", [])]
    return items, {k: str(v) for k, v in document.get("Properties", {}).items()}


def language_of(p: Project, properties: dict[str, str]) -> str:
    language = properties.get("Language", "")
    if language:
        return "VB" if language.upper() in {"VB", "VISUALBASIC"} else "C#"
    return "VB" if p.path.suffix.lower() == ".vbproj" else "C#"


def symbols_of(language: str, properties: dict[str, str]) -> list[str]:
    """C#: DefineConstants names. VB: FinalDefineConstants (CONFIG, DEBUG, TRACE, _MyType, PLATFORM and the project's), NAME=value."""
    if language == "VB":
        raw = properties.get("FinalDefineConstants") or properties.get("DefineConstants", "")
        return [s.strip() for s in _split_vb(raw) if s.strip()]
    return sorted({s.strip() for s in properties.get("DefineConstants", "").replace(",", ";").split(";") if s.strip()})


def _split_vb(raw: str) -> list[str]:
    out, current, quoted = [], "", False
    for ch in raw:
        if ch == '"':
            quoted = not quoted
        if ch in ",;" and not quoted:
            out.append(current)
            current = ""
        else:
            current += ch
    out.append(current)
    return out


def declarations(request: dict[str, Any]) -> dict[str, Any]:
    """Run the extractor's declarations command on one request."""
    tool = extractor.resolve()
    with tempfile.TemporaryDirectory(prefix="rg-declarations-") as tmp:
        req, out = Path(tmp) / "request.json", Path(tmp) / "response.json"
        req.write_text(json.dumps(request), encoding="utf-8")
        completed = run(["dotnet", str(tool.entry), "declarations", "--request", str(req), "--output", str(out)])
        if completed.returncode != 0 or not out.is_file():
            text = completed.stdout + completed.stderr
            if "Unrecognized command or argument" in text or "Assembly not found" in text or "'--request'" in text:
                raise RgError.of("DECLARATIONS_UNSUPPORTED", "The installed RoslynToRdf extractor has no declarations command.",
                                 "Update the extractor to this roslyn-graph version. " + extractor.INSTALL_HINT, extractor=str(tool.entry))
            raise RgError.of("DECLARATIONS_FAILED", f"roslyn2rdf declarations failed (exit {completed.returncode}).",
                             "Read 'stderr'.", stderr=completed.stderr.splitlines()[-20:])
        return json.loads(out.read_text(encoding="utf-8"))


def cache_key(p: Project, extractor_id: str) -> str:
    b = p.build
    return sha256_text(json.dumps([CACHE_VERSION, extractor_id, p.repository_id, p.commit, p.dirty_hash, p.relative,
                                   b.get("configuration"), b.get("targetFramework"), b.get("platform"), b.get("solution")]))


def index_project(p: Project, cache_dir: Path | None) -> None:
    """Fill p.index (full name -> repo-relative declaring files), from the cache when possible."""
    extractor_id = extractor.resolve().id
    # Only a clean checkout at the recorded commit is cached: the dirty hash cannot see edits to untracked files.
    cacheable = cache_dir is not None and p.drift is None and not p.dirty_hash
    cache = cache_dir / f"{cache_key(p, extractor_id)}.json" if cacheable else None
    if cache and cache.is_file():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            p.index, p.language_version, p.symbols, p.cached = data["index"], data["languageVersion"], data["symbols"], True
            return
        except (OSError, json.JSONDecodeError, KeyError):
            pass  # rebuilt below
    items, properties = evaluate(p)
    language = language_of(p, properties)
    response = declarations({"language": language, "langVersion": properties.get("LangVersion", ""),
                             "preprocessorSymbols": symbols_of(language, properties), "files": [str(i) for i in items],
                             "rootNamespace": properties.get("RootNamespace", "") if language == "VB" else ""})
    repo = p.repository.resolve()
    generated = (p.path.parent / "obj").resolve()
    index: dict[str, set[str]] = {}
    for t in response.get("types", []):
        path = Path(t["file"]).resolve()
        if not path.is_relative_to(repo) or path.is_relative_to(generated):
            continue  # NuGet-provided items and build output under obj/ are not the repository's source
        index.setdefault(t["name"], set()).add(path.relative_to(repo).as_posix())
    p.index = {name: sorted(files) for name, files in sorted(index.items())}
    p.language_version, p.symbols = response.get("languageVersion", ""), symbols_of(language, properties)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"format": CACHE_VERSION, "project": p.to_json(), "languageVersion": p.language_version,
                                     "symbols": p.symbols, "index": p.index}, ensure_ascii=False), encoding="utf-8", newline="\n")


def locate(p: Project | None, full_name: str) -> tuple[str, list[str]]:
    """(locationStatus, files) of one physical type; p is None for NuGet components."""
    if p is None:
        return "nuget", []
    if compiler_generated(full_name):
        owner = source_owner(full_name)
        files = p.index.get(owner, []) if owner else []
        return ("compiler-generated", files) if files else ("generated", [])
    files = p.index.get(full_name, [])
    return ("found", files) if files else ("generated", [])


def index_all(projects: list[Project], cache_dir: Path | None, allow_drift: bool) -> list[dict[str, Any]]:
    """Check every checkout, then index the projects in parallel. Returns drift warnings."""
    for p in projects:
        check_checkout(p)
    drifted = [p for p in projects if p.drift]
    if drifted and not allow_drift:
        raise RgError.of("SOURCE_CHECKOUT_DRIFT", f"{len(drifted)} checkout(s) differ from the build the store was made from.",
                         "Check out the recorded commit, or pass --allow-drift to resolve files from the current checkout anyway.",
                         drift=[{"repository": p.repository_id, "checkout": str(p.repository), "problem": p.drift} for p in drifted])
    for p in projects:
        if not p.path.is_file():
            raise RgError.of("SOURCE_PROJECT_MISSING", f"{p.relative} is not in the checkout of '{p.repository_id}' ({p.repository}).",
                             "The checkout does not match the build; check out the recorded commit.", project=str(p.path))
    extractor.resolve()  # fail once, before starting MSBuild
    with ThreadPoolExecutor(MSBUILD_JOBS) as pool:
        list(pool.map(lambda p: index_project(p, cache_dir), projects))
    return [{"code": "SOURCE_CHECKOUT_DRIFT", "repository": p.repository_id, "message": p.drift} for p in drifted]
