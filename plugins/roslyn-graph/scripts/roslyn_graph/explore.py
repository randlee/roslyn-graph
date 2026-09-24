"""Query published stores, export bounded subgraphs and render them with a registered visualizer."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from . import artifacts, oxigraph
from .result import RgError
from .util import DT, RDF_TYPE, RG

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
VISUALIZERS = PLUGIN_ROOT / "visualizers"
MAX_ROWS = 2000
_NT_LINE = re.compile(r'^(<[^>]*>|_:\S+) (<[^>]*>) (.*) \.$')


def store_for(manifest_path: Path) -> tuple[Path, dict[str, Any]]:
    manifest = artifacts.read_manifest(manifest_path)
    if artifacts.manifest_kind(manifest) not in {"assembly", "solution", "view"}:
        raise RgError.of("MANIFEST_UNSUPPORTED", f"{manifest_path} is not a schema-{artifacts.MANIFEST_SCHEMA} artifact manifest.",
                         "Point at manifest.json of a solution or view published by the create skill.")
    store = manifest_path.parent / "store.oxigraph"
    if not store.is_dir():
        raise RgError.of("STORE_NOT_FOUND", f"{store} does not exist.")
    return store, manifest


_PARAM = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def read_query(query: str | None, query_file: str | None, params: list[str] | None = None) -> str:
    """Load a query and substitute {{NAME}} placeholders from NAME=VALUE parameters.

    Placeholders sit inside SPARQL string literals, so values are escaped as literal content.
    """
    if bool(query) == bool(query_file):
        raise RgError.of("QUERY_ARGUMENT", "Pass exactly one of --query or --query-file.")
    if query_file:
        try:
            text = Path(query_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise RgError.of("QUERY_FILE", f"Cannot read {query_file}: {exc}") from exc
    else:
        text = query  # type: ignore[assignment]
    values: dict[str, str] = {}
    for item in params or []:
        name, sep, value = item.partition("=")
        if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise RgError.of("QUERY_PARAM_INVALID", f"--param {item!r} is not NAME=VALUE with an upper-case NAME.")
        values[name] = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    missing = sorted({m for m in _PARAM.findall(text) if m not in values})
    if missing:
        raise RgError.of("QUERY_PARAM_MISSING", f"The query needs parameters {missing}.",
                         "Pass each as --param NAME=VALUE; the query file's comments describe them.", missing=missing)
    return _PARAM.sub(lambda m: values[m.group(1)], text)


def query(manifest_path: Path, text: str, union: bool, limit: int = MAX_ROWS) -> dict[str, Any]:
    store, manifest = store_for(manifest_path)
    rows = oxigraph.select(store, text, union=union)
    return {"type": "query", "manifest": str(manifest_path), "kind": manifest["kind"], "rowCount": len(rows),
            "truncated": len(rows) > limit, "rows": rows[:limit]}


def logical_map(store: Path, manifest: dict[str, Any]) -> dict[str, str]:
    if manifest.get("kind") != "view":
        raise RgError.of("LOGICAL_NEEDS_VIEW", "--logical needs a view manifest; solutions have no logical-type projection.")
    rows = oxigraph.select(store, f"PREFIX rg: <{RG}> SELECT ?t ?l WHERE {{ GRAPH <{manifest['logicalGraphIri']}> {{ ?t rg:logicalType ?l }} }}")
    return {r["t"]: r["l"] for r in rows}


def collapse(lines: list[str], mapping: dict[str, str]) -> list[str]:
    """Rewrite physical type IRIs to their logical IRI and drop duplicate triples."""
    wrapped = {f"<{k}>": f"<{v}>" for k, v in mapping.items()}
    out: dict[str, None] = {}
    for line in lines:
        match = _NT_LINE.match(line.strip())
        if not match:
            continue
        subject, predicate, obj = match.groups()
        subject = wrapped.get(subject, subject)
        if obj.startswith("<"):
            obj = wrapped.get(obj, obj)
        out[f"{subject} {predicate} {obj} ."] = None
    return list(out)


def summarize(lines: list[str]) -> dict[str, Any]:
    kinds: dict[str, int] = {}
    edges = {"implements": 0, "inherits": 0}
    for line in lines:
        match = _NT_LINE.match(line)
        if not match:
            continue
        _, predicate, obj = match.groups()
        if predicate == f"<{RDF_TYPE}>" and obj.startswith(f"<{DT}"):
            kind = obj[len(DT) + 1 : -1]
            kinds[kind] = kinds.get(kind, 0) + 1
        elif predicate == f"<{DT}implements>":
            edges["implements"] += 1
        elif predicate == f"<{DT}inherits>":
            edges["inherits"] += 1
    return {"triples": len(lines), "nodesByKind": kinds, "edges": edges}


def export(manifest_path: Path, text: str, output: Path, union: bool, logical: bool) -> dict[str, Any]:
    if not re.search(r"\bCONSTRUCT\b", text, re.IGNORECASE):
        raise RgError.of("EXPORT_NEEDS_CONSTRUCT", "Exports use a CONSTRUCT query.", "See reference/query-design.md for the viewer-ready CONSTRUCT patterns.")
    store, manifest = store_for(manifest_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = output.with_suffix(".raw.nt")
    oxigraph.construct(store, text, raw, union=union)
    lines = [line.strip() for line in raw.read_text(encoding="utf-8").splitlines() if line.strip()]
    raw.unlink()
    collapsed = 0
    if logical:
        before = len(lines)
        lines = collapse(lines, logical_map(store, manifest))
        collapsed = before - len(lines)
    else:
        lines = list(dict.fromkeys(lines))
    if not lines:
        raise RgError.of("EXPORT_EMPTY", "The CONSTRUCT query produced no triples.", "Run the WHERE clause as a SELECT with the query command to debug it.")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"type": "export", "manifest": str(manifest_path), "output": str(output), "logical": logical,
            "duplicatesCollapsed": collapsed, "summary": summarize(lines)}


def registry() -> dict[str, Any]:
    return json.loads((VISUALIZERS / "registry.json").read_text(encoding="utf-8"))


def render(visualizer: str, data: Path, output: Path, title: str) -> dict[str, Any]:
    entries = registry()
    if visualizer not in entries:
        raise RgError.of("VISUALIZER_UNKNOWN", f"Unknown visualizer '{visualizer}'.", f"Registered: {', '.join(sorted(entries))}.")
    entry = entries[visualizer]
    if entry["render"] != "embed-rdf":
        raise RgError.of("VISUALIZER_UNSUPPORTED", f"Visualizer '{visualizer}' uses render mode {entry['render']!r}, which this version cannot build.")
    folder = VISUALIZERS / visualizer
    page = (folder / entry["template"]).read_text(encoding="utf-8")
    for script in entry.get("inlineScripts", []):
        tag = f'<script src="{script}"></script>'
        if tag not in page:
            raise RgError.of("VISUALIZER_TEMPLATE", f"{entry['template']} no longer contains {tag}.")
        page = page.replace(tag, "<script>\n" + (folder / script).read_text(encoding="utf-8") + "\n</script>")
    rdf = data.read_text(encoding="utf-8")
    if "</script" in rdf.lower():
        raise RgError.of("EXPORT_UNSAFE", "The exported RDF contains '</script', which cannot be embedded.")
    block = f'<script type="text/turtle" id="roslyn-graph-data" data-title="{html.escape(title, quote=True)}">\n{rdf}</script>\n'
    if "</body>" not in page:
        raise RgError.of("VISUALIZER_TEMPLATE", f"{entry['template']} has no </body>.")
    page = page.replace("</body>", block + "</body>", 1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8", newline="\n")
    return {"type": "page", "visualizer": visualizer, "output": str(output), "dataTriples": sum(1 for l in rdf.splitlines() if l.strip()),
            "limits": entry.get("limits", "")}
