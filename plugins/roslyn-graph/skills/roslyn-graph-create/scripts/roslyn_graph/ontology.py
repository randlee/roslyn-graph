"""Parse the plugin's ontology files and generate the ontology reference.

The ontology files use one subject per statement with ``;``-separated predicates. This parser
supports exactly that shape and fails loudly on anything else, so the generated reference can never
silently drop a term.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .result import RgError
from .util import resource

FILES = ["dotnet-types.ttl", "roslyn-graph.ttl"]
_PREFIX = re.compile(r"^@prefix\s+(\w*):\s+<([^>]+)>\s*\.$")


@dataclass
class Term:
    prefix: str
    name: str
    kind: str = ""  # "class" or "property"
    label: str = ""
    comment: str = ""
    domain: str = ""
    range: str = ""
    subclass_of: str = ""
    extra: list[str] = field(default_factory=list)

    @property
    def curie(self) -> str:
        return f"{self.prefix}:{self.name}"


def _statements(text: str, source: str) -> list[str]:
    """Split into statements. Only full-line comments are supported; a statement ends with '.' at end of line."""
    statements, current = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        current.append(line)
        if line.endswith(".") and line.count('"') % 2 == 0:
            statements.append(" ".join(current))
            current = []
    if current:
        raise RgError.of("ONTOLOGY_PARSE", f"{source}: unterminated statement: {' '.join(current)[:80]}")
    return statements


def _split(body: str, sep: str) -> list[str]:
    parts, current, quoted = [], [], False
    for char in body:
        if char == '"':
            quoted = not quoted
        if char == sep and not quoted:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return [p for p in parts if p]


def parse(text: str, source: str) -> tuple[dict[str, str], list[Term]]:
    prefixes: dict[str, str] = {}
    terms: list[Term] = []
    for statement in _statements(text, source):
        prefix = _PREFIX.match(statement)
        if prefix:
            prefixes[prefix.group(1)] = prefix.group(2)
            continue
        body = statement[:-1].strip()
        subject, _, rest = body.partition(" ")
        if ":" not in subject:
            raise RgError.of("ONTOLOGY_PARSE", f"{source}: unsupported subject {subject!r}")
        term_prefix, term_name = subject.split(":", 1)
        term = Term(term_prefix, term_name)
        for pair in _split(rest, ";"):
            predicate, _, obj = pair.partition(" ")
            obj = obj.strip()
            if predicate == "a":
                term.kind = {"rdfs:Class": "class", "rdf:Property": "property", "owl:Ontology": "ontology"}.get(obj, obj)
            elif predicate == "rdfs:label":
                term.label = obj.strip('"')
            elif predicate == "rdfs:comment":
                term.comment = obj.strip('"')
            elif predicate == "rdfs:domain":
                term.domain = obj
            elif predicate == "rdfs:range":
                term.range = obj
            elif predicate == "rdfs:subClassOf":
                term.subclass_of = obj
            else:
                term.extra.append(pair)
        if term.kind not in {"class", "property", "ontology"}:
            raise RgError.of("ONTOLOGY_PARSE", f"{source}: {subject} has unsupported type {term.kind!r}")
        terms.append(term)
    return prefixes, terms


def load(directory: Path | None = None) -> tuple[dict[str, str], list[Term]]:
    directory = directory or resource("ontology")
    prefixes: dict[str, str] = {}
    terms: list[Term] = []
    for name in FILES:
        p, t = parse((directory / name).read_text(encoding="utf-8"), name)
        prefixes.update(p)
        terms.extend(t)
    return prefixes, terms


def declared(directory: Path | None = None, prefix: str = "dt") -> set[str]:
    return {t.name for t in load(directory)[1] if t.prefix == prefix and t.kind != "ontology" and t.name}


def markdown(directory: Path | None = None) -> str:
    prefixes, terms = load(directory)
    out = [
        "# Ontology reference",
        "",
        "<!-- Generated from the ontology/ files beside this skill by `python scripts/rg.py ontology-doc` (repository: python scripts/check_plugin_sync.py --fix). Do not edit by hand. -->",
        "",
        "## Prefixes",
        "",
        "| Prefix | IRI |",
        "|---|---|",
    ]
    out += [f"| `{p}:` | `{iri}` |" for p, iri in sorted(prefixes.items())]
    for prefix, title in [("dt", "Physical .NET facts (`dt:`)"), ("rg", "Artifacts, solutions and logical types (`rg:`)")]:
        classes = sorted((t for t in terms if t.prefix == prefix and t.kind == "class"), key=lambda t: t.name)
        props = [t for t in terms if t.prefix == prefix and t.kind == "property"]
        out += ["", f"## {title}", "", "### Classes", "", "| Class | Subclass of | Notes |", "|---|---|---|"]
        out += [f"| `{t.curie}` | {f'`{t.subclass_of}`' if t.subclass_of else ''} | {t.comment} |" for t in classes]
        out += ["", "### Properties", "", "| Property | Domain | Range | Notes |", "|---|---|---|---|"]
        for t in sorted(props, key=lambda t: (t.domain or "~", t.name)):
            out.append(f"| `{t.curie}` | {f'`{t.domain}`' if t.domain else ''} | {f'`{t.range}`' if t.range else ''} | {t.comment} |")
    return "\n".join(out) + "\n"
