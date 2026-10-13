"""openwiki-scope: turn openwiki-type records into an OpenWiki scope for one repository.

OpenWiki (0.7.2) takes scope from two files in the repository:

* ``.openwikiignore`` (enforced: every read, ls, glob, grep and write is checked; gitignore rules, last match
  wins, case-insensitive). A managed block at the top denies everything, then re-opens each declaring file and
  every ancestor directory of it, one level at a time. The user's own lines after the block still apply.
* ``openwiki/INSTRUCTIONS.md`` (advisory: read on every run). A managed block lists the types to document.

Nothing here runs OpenWiki. See the explore skill's reference/openwiki-scope.md.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from . import records, sources
from .result import ProblemList, RgError

BEGIN = "BEGIN roslyn-graph openwiki-scope"
END = "END roslyn-graph openwiki-scope"
IGNORE_FILE = ".openwikiignore"
BRIEF_FILE = "openwiki/INSTRUCTIONS.md"
MAX_LISTED_TYPES = 400
UNSUPPORTED = set("*?!")
OPENED = ("found", "compiler-generated")
ROOT_DIR = records.ROOT_DIR


# ---- ignore chain ---------------------------------------------------------------------------


def check_path(path: str) -> str:
    """A repository-relative POSIX path the chain can open exactly; a trailing '/' marks a directory."""
    posix = PurePosixPath(path.rstrip("/"))
    bad = (not path or path != path.strip() or path.startswith("/") or "\\" in path or ":" in posix.parts[0]
           or any(p in ("", ".", "..") for p in path.rstrip("/").split("/")) or UNSUPPORTED & set(path) or path.startswith("#"))
    if bad:
        raise RgError.of("OPENWIKI_PATH_UNSUPPORTED", f"{path!r} cannot be opened exactly by an .openwikiignore rule.",
                         "Paths must be repository-relative with '/' separators, without '*', '?', '!', '..' or surrounding spaces.",
                         path=path)
    return path


def chain(paths: list[str]) -> list[str]:
    """Rules that deny everything except these files and directories (directories end with '/').

    Pure: duplicates are removed, paths inside an opened directory are dropped, and the result is sorted, so the
    same set of paths always gives the same lines.
    """
    problems = ProblemList()
    for p in paths:
        try:
            check_path(p)
        except RgError as exc:
            problems.extend(exc)
    problems.raise_if_any()
    # OpenWiki matches case-insensitively, so 'Common/' and 'common/' are one directory to it: every comparison
    # uses a lowered key, and each directory keeps the first spelling in sorted order. str.lower, not casefold:
    # JavaScript's /i folds simply, so 'Straße' and 'STRASSE' stay different to it.
    spelling: dict[str, str] = {}

    def canonical(path: str) -> str:
        parts = path.rstrip("/").split("/")
        out = []
        for i in range(len(parts)):
            out.append(spelling.setdefault("/".join(parts[:i + 1]).lower(), parts[i]))
        return "/".join(out) + ("/" if path.endswith("/") else "")

    targets = sorted({canonical(p).lower(): canonical(p) for p in sorted(paths)}.values(), key=str.lower)
    directories = [t.lower() for t in targets if t.endswith("/")]
    targets = [t for t in targets if not any(t.lower() != d and t.lower().startswith(d) for d in directories)]
    lines = ["*", "!/openwiki/"]
    opened: set[str] = set()
    for t in targets:
        parts = t.rstrip("/").split("/")
        for i in range(1, len(parts)):
            ancestor = "/".join(parts[:i])
            if ancestor.lower() not in opened:
                lines += [f"!/{ancestor}/", f"/{ancestor}/*"]
                opened.add(ancestor.lower())
        lines.append(f"!/{t}")
    return lines


# ---- managed blocks -------------------------------------------------------------------------


def _read_existing(path: Path) -> str | None:
    """The current text of a file that gets a managed block, or None when it does not exist."""
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RgError.of("OPENWIKI_FILE_UNREADABLE", f"Cannot read {path} as UTF-8 text: {exc}",
                         "Fix or re-save the file as UTF-8; openwiki-scope keeps its lines and only replaces its own block.",
                         path=str(path)) from exc


def merge_block(existing: str | None, body: list[str], markdown: bool, where: str) -> str:
    """Replace the managed block in place, or put a new one at the top; every other line is kept."""
    begin, end = (f"<!-- {BEGIN} (generated; edit outside this block) -->", f"<!-- {END} -->") if markdown else \
        (f"# {BEGIN} (generated; edit below the END line)", f"# {END}")
    block = [begin, *body, end]
    lines = (existing or "").replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    starts = [i for i, line in enumerate(lines) if BEGIN in line]
    ends = [i for i, line in enumerate(lines) if END in line]
    if len(starts) > 1 or len(ends) > 1 or len(starts) != len(ends) or (starts and ends[0] < starts[0]):
        raise RgError.of("OPENWIKI_BLOCK_BROKEN", f"{where} has a damaged roslyn-graph block (BEGIN and END lines do not pair up).",
                         "Delete the block's lines by hand, keep your own, and run openwiki-scope again.", path=where)
    if starts:
        merged = lines[:starts[0]] + block + lines[ends[0] + 1:]
    else:
        merged = block + ([""] if markdown and lines else []) + lines
    return "\n".join(merged) + "\n"


# ---- records --------------------------------------------------------------------------------


def read_records(path: Path, schema: records.Schema) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Records of one JSONL or JSON file, validated against openwiki-type, and its context sidecar (or {})."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RgError.of("OPENWIKI_RECORDS_NOT_FOUND", f"Cannot read {path}: {exc}", "Pass a file written by rg.py records.",
                         path=str(path)) from exc
    except UnicodeDecodeError as exc:
        raise RgError.of("OPENWIKI_RECORDS_INVALID", f"{path} is not UTF-8: {exc}", "Pass a file written by rg.py records.",
                         path=str(path)) from exc
    try:
        if text.lstrip().startswith("["):
            items = list(enumerate(json.loads(text), 1))
        else:
            items = [(n, json.loads(line)) for n, line in enumerate(text.splitlines(), 1) if line.strip()]
    except json.JSONDecodeError as exc:
        raise RgError.of("OPENWIKI_RECORDS_INVALID", f"{path} is not JSON lines or a JSON array: {exc}", path=str(path)) from exc
    invalid = [{"record": n, "problems": problems} for n, r in items if (problems := records.validate_value(r, schema.data))]
    if invalid:
        raise RgError.of("OPENWIKI_RECORDS_INVALID", f"{len(invalid)} record(s) in {path} do not match openwiki-type.",
                         "Export with: rg.py records --schema openwiki-type", path=str(path), invalid=invalid[:20], invalidCount=len(invalid))
    context_file = path.with_suffix(".context.json")
    context = {}
    if context_file.is_file():
        try:
            context = json.loads(context_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            context = {}
    return [r for _, r in items], context


def merge(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """One record per (name, repository); duplicates from several exports are merged. Returns (records, duplicates)."""
    out: dict[tuple[str, str | None], dict[str, Any]] = {}
    duplicates = 0
    for r in rows:
        key = (r["name"], r["repository"])
        if key not in out:
            out[key] = {**r, "files": sorted(set(r["files"])), "projectDirs": sorted(set(r["projectDirs"]))}
            continue
        duplicates += 1
        kept = out[key]
        for name in ("files", "projectDirs", "assemblies"):
            if name in r or name in kept:
                kept[name] = sorted(set(kept.get(name, [])) | set(r.get(name, [])))
        kept["locationStatus"] = min(kept["locationStatus"], r["locationStatus"], key=sources.STATUSES.index)
        if kept["origin"] != r["origin"]:
            kept["origin"] = "mixed"
    return [out[k] for k in sorted(out, key=lambda k: (k[0], k[1] or ""))], duplicates


# ---- brief ----------------------------------------------------------------------------------


def _project_of(r: dict[str, Any]) -> str:
    return ", ".join("(repository root)" if d == ROOT_DIR else d for d in r["projectDirs"]) or "(no project)"


def _namespace_of(r: dict[str, Any]) -> str:
    return r.get("namespace") or (r["name"].rsplit(".", 1)[0] if "." in r["name"] else "") or "(global)"


def brief(repository: str, listed: list[dict[str, Any]], external: list[str], counts: dict[str, int], provenance: list[dict[str, Any]],
          max_listed: int) -> tuple[list[str], bool]:
    """The managed block of INSTRUCTIONS.md. Returns (lines, summarized)."""
    summarized = len(listed) > max_listed
    example = next((d for r in listed for d in r["projectDirs"] if d != ROOT_DIR), "src/")
    out = [
        "# Scope",
        "",
        f"Document the {len(listed)} types listed below from the `{repository}` repository, and how they work together.",
        "Do not describe other code. Types outside the list may be mentioned only where a listed type depends on them.",
        "",
        "Only the declaring files of these types (and their directories) can be read; everything else is ignored.",
        "To find files use `ls`, `grep`, or `glob` from the repository root with a directory-prefixed pattern",
        f"such as `{example}**/*`. A `glob` with a search directory returns nothing under this scope.",
    ]
    hidden = [f"{counts[s]} {text}" for s, text in (
        ("compiler-generated", "compiler-generated types (closures, state machines; their owners' files are open)"),
        ("generated", "generated types without source in the repository")) if counts.get(s)]
    if hidden:
        out += ["", "Not listed: " + " and ".join(hidden) + "."]
    by_project: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in listed:
        by_project[_project_of(r)][_namespace_of(r)].append(r)
    out += ["", "## Types" if not summarized else "## Namespaces", ""]
    if summarized:
        out += [f"{len(listed)} types are in scope, more than the {max_listed} listed in full; the namespaces follow with type counts.", ""]
    for project in sorted(by_project):
        out += [f"### {project}", ""]
        for ns in sorted(by_project[project]):
            types = sorted(by_project[project][ns], key=lambda r: r["name"])
            if summarized:
                out.append(f"- `{ns}`: {len(types)} types")
                continue
            out.append(f"#### {ns}")
            out.append("")
            out += [f"- `{r['name']}` ({r['kind'].lower()}): {', '.join(f'`{f}`' for f in r['files'])}" for r in types]
            out.append("")
        if summarized:
            out.append("")
    if external:
        out += ["## External dependencies (NuGet)", "", "No source in this repository; describe them only by how the listed types use them.", ""]
        out += [f"- `{name}`" for name in external]
        out.append("")
    if provenance:
        out += ["## Provenance", ""]
        for p in provenance:
            parts = [f"`{p['records']}`"] + [f"{k} {v}" for k, v in (("store", p.get("artifactId")), ("graph", p.get("graph")),
                                                                    ("commit", p.get("commit")), ("exported", p.get("exported"))) if v]
            out.append("- " + ", ".join(parts))
        out.append("")
    while out and out[-1] == "":
        out.pop()
    return out, summarized


def _provenance(path: Path, context: dict[str, Any], repository: str) -> dict[str, Any]:
    source = context.get("source") or {}
    graph = (context.get("input") or {}).get("path")
    commit = ((context.get("repositories") or {}).get(repository) or {}).get("commit")
    return {"records": path.name, "artifactId": source.get("artifactId"), "graph": Path(graph).stem if graph else None,
            "commit": commit[:12] if commit else None, "exported": context.get("createdUtc")}


def _checkout_from(contexts: list[dict[str, Any]], repository: str) -> str | None:
    for c in contexts:
        entry = (c.get("repositories") or {}).get(repository) or {}
        if entry.get("checkout") or entry.get("repository"):
            return entry.get("checkout") or entry.get("repository")
    return None


# ---- command --------------------------------------------------------------------------------


def run(record_files: list[str], repository: str | None, repo_root: str | None, max_listed: int = MAX_LISTED_TYPES,
        dry_run: bool = False) -> dict[str, Any]:
    if not record_files:
        raise RgError.of("USAGE", "Pass at least one --records file.")
    if max_listed < 0:
        raise RgError.of("USAGE", "--max-listed-types must be 0 or more.")
    schema = records.load_schema("openwiki-type")
    rows, contexts, paths = [], [], [Path(f) for f in record_files]
    for path in paths:
        found, context = read_records(path, schema)
        rows += found
        contexts.append(context)
    merged, duplicates = merge(rows)

    repositories = sorted({r["repository"] for r in merged if r["repository"]})
    if repository is None:
        if len(repositories) != 1:
            raise RgError.of("OPENWIKI_REPOSITORY_REQUIRED", f"The records span {len(repositories)} repositories; OpenWiki runs on one.",
                             "Pass --repository with one of 'repositories'.", repositories=repositories)
        repository = repositories[0]
    mine = [r for r in merged if r["repository"] == repository]
    if not mine:
        raise RgError.of("OPENWIKI_REPOSITORY_EMPTY", f"No record belongs to repository {repository!r}.",
                         "Pass one of 'repositories'.", repositories=repositories)
    other = Counter(r["repository"] for r in merged if r["repository"] and r["repository"] != repository)
    external = sorted({r["name"] for r in merged if r["repository"] is None})

    root_text = repo_root or _checkout_from(contexts, repository)
    if not root_text:
        raise RgError.of("OPENWIKI_REPO_ROOT_REQUIRED", f"No checkout of {repository!r} is recorded beside the records.",
                         "Pass --repo-root with the repository's checkout.")
    root = Path(root_text)
    if not root.is_dir():
        raise RgError.of("OPENWIKI_REPO_ROOT_MISSING", f"{root} is not a directory.", "Pass --repo-root with the repository's checkout.",
                         repoRoot=str(root))

    counts = Counter(r["locationStatus"] for r in mine)
    warnings: list[dict[str, Any]] = []
    paths_to_open: set[str] = set()
    fallback = sorted({d for r in mine if r["locationStatus"] in OPENED and not r["files"] for d in r["projectDirs"]})
    for r in mine:
        if r["locationStatus"] in OPENED:
            paths_to_open.update(r["files"] or [d for d in r["projectDirs"] if d != ROOT_DIR])
    if ROOT_DIR in fallback:
        fallback.remove(ROOT_DIR)
        warnings.append({"code": "OPENWIKI_ROOT_PROJECT", "types": sorted(r["name"] for r in mine if r["locationStatus"] in OPENED
                                                                          and not r["files"] and ROOT_DIR in r["projectDirs"]),
                         "message": "Some types without declaring files belong to a project at the repository root; opening the "
                                    "root would open the whole repository, so they stay out of scope."})
    if fallback:
        warnings.append({"code": "OPENWIKI_DIRECTORY_FALLBACK", "directories": fallback,
                         "message": "Some types have no declaring files; their whole project directories are opened."})
    missing = sorted(p for p in paths_to_open if not (root / p).exists())
    if missing:
        warnings.append({"code": "OPENWIKI_FILE_MISSING", "files": missing[:50], "count": len(missing),
                         "message": "Some opened paths are not in this checkout; is --repo-root the checkout the records came from?"})

    ignore_lines = chain(sorted(paths_to_open))
    listed = [r for r in mine if r["locationStatus"] == "found"]
    provenance = [_provenance(p, c, repository) for p, c in zip(paths, contexts) if c]
    brief_lines, summarized = brief(repository, listed, external, counts, provenance, max_listed)
    if summarized:
        warnings.append({"code": "OPENWIKI_BRIEF_SUMMARIZED", "types": len(listed), "maxListedTypes": max_listed,
                         "message": "The brief lists namespaces with type counts instead of every type; the ignore file still opens every file."})

    ignore_path, brief_path = root / IGNORE_FILE, root / BRIEF_FILE
    ignore_text = merge_block(_read_existing(ignore_path), ignore_lines, False, str(ignore_path))
    brief_text = merge_block(_read_existing(brief_path), brief_lines, True, str(brief_path))
    if not dry_run:
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        ignore_path.write_text(ignore_text, encoding="utf-8", newline="\n")
        brief_path.write_text(brief_text, encoding="utf-8", newline="\n")

    result: dict[str, Any] = {
        "type": "openwiki-scope",
        "repository": repository,
        "repoRoot": str(root),
        "dryRun": dry_run,
        "types": {"inScope": len(mine), "listed": len(listed), **{s: counts.get(s, 0) for s in sources.STATUSES}},
        "files": len([p for p in paths_to_open if not p.endswith("/")]),
        "directories": sorted(p for p in paths_to_open if p.endswith("/")),
        "duplicates": duplicates,
        "excluded": {"otherRepositories": dict(sorted(other.items())), "external": len(external)},
        "ignore": {"path": str(ignore_path), "rules": len(ignore_lines)},
        "brief": {"path": str(brief_path), "summarized": summarized},
        "warnings": warnings,
    }
    if dry_run:
        result["ignore"]["text"] = ignore_text
        result["brief"]["text"] = brief_text
    return result
