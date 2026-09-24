"""Oxigraph CLI wrapper.

``oxigraph load`` exits 0 even when the input fails to parse and only reports the parser error on
stderr. Every call therefore treats *any* stderr line that is not a known advisory as a failure.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

from .result import RgError
from .util import run

ADVISORY_PATTERNS = [
    re.compile(r"^Some files like Wikidata dumps contain invalid IRIs or language tags\."),
    re.compile(r"^If you plan to run a read-heavy workload, consider running `oxigraph optimize"),
    re.compile(r"^\s*\d+ (triples|quads) (loaded|dumped|written)\b"),
]


def command() -> str:
    return os.environ.get("ROSLYN_GRAPH_OXIGRAPH", "oxigraph")


def unexpected_stderr(stderr: str) -> list[str]:
    lines = [line.rstrip() for line in stderr.splitlines() if line.strip()]
    return [line for line in lines if not any(p.search(line) for p in ADVISORY_PATTERNS)]


READ_ONLY = {"query", "dump", "convert", "--version"}


def crashed(returncode: int) -> bool:
    """A native crash (Windows NTSTATUS such as 0xC0000005, or a POSIX signal), not an Oxigraph error exit."""
    return returncode < 0 or returncode >= 0xC0000000


def invoke(args: list[str], what: str, trace: str = "") -> str:
    started = time.monotonic()
    completed = run([command(), *args])
    if crashed(completed.returncode) and args[0] in READ_ONLY:
        completed = run([command(), *args])  # read-only commands are safe to retry once after a crash
    if os.environ.get("ROSLYN_GRAPH_TRACE"):
        detail = " ".join((trace or what).split())[:160]
        print(f"[oxigraph {time.monotonic() - started:7.2f}s] {args[0]}: {detail}", file=sys.stderr, flush=True)
    problems = unexpected_stderr(completed.stderr)
    if completed.returncode != 0 or problems:
        raise RgError.of(
            "OXIGRAPH_FAILED",
            f"oxigraph {args[0]} failed while {what} (exit {completed.returncode}).",
            "Read 'stderr'. Parser errors mean the input RDF is malformed; lock errors mean another process has the store open.",
            args=args,
            stderr=problems or completed.stderr.splitlines()[-20:],
        )
    return completed.stdout


def version() -> str:
    output = invoke(["--version"], "reading its version").strip()
    match = re.search(r"(\d+\.\d+\.\d+)", output)
    if not match:
        raise RgError.of("OXIGRAPH_VERSION_UNKNOWN", f"Cannot parse Oxigraph version from {output!r}.")
    return match.group(1)


def load(store: Path, file: Path, graph: str | None = None) -> None:
    args = ["load", "--location", str(store), "--file", str(file), "--non-atomic"]
    if graph:
        args += ["--graph", graph]
    invoke(args, f"loading {file.name}")


def dump(store: Path, file: Path, fmt: str, graph: str | None = None) -> None:
    args = ["dump", "--location", str(store), "--file", str(file), "--format", fmt]
    if graph:
        args += ["--graph", graph]
    invoke(args, f"dumping {store}")


def optimize(store: Path) -> None:
    invoke(["optimize", "--location", str(store)], f"optimizing {store}")


def convert(source: Path, target: Path) -> None:
    invoke(["convert", "--from-file", str(source), "--to-file", str(target)], f"converting {source.name}")


_INLINE_QUERY_LIMIT = 8000  # Windows command lines are limited to 32K characters


def _query_args(query: str, scratch: list[Path]) -> list[str]:
    if len(query) <= _INLINE_QUERY_LIMIT:
        return ["--query", query]
    handle = tempfile.NamedTemporaryFile("w", suffix=".rq", delete=False, encoding="utf-8")
    with handle:
        handle.write(query)
    scratch.append(Path(handle.name))
    return ["--query-file", handle.name]


def select(store: Path, query: str, union: bool = False) -> list[dict[str, str]]:
    scratch: list[Path] = []
    args = ["query", "--location", str(store), *_query_args(query, scratch), "--results-format", "json"]
    if union:
        args.append("--union-default-graph")
    try:
        output = invoke(args, "running a SELECT query", trace=query)
    finally:
        for path in scratch:
            path.unlink(missing_ok=True)
    try:
        document = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RgError.of("OXIGRAPH_BAD_JSON", f"Query output is not JSON: {exc}", query=query) from exc
    return [{name: term["value"] for name, term in row.items()} for row in document["results"]["bindings"]]


def construct(store: Path, query: str, target: Path, union: bool = False) -> None:
    scratch: list[Path] = []
    args = ["query", "--location", str(store), *_query_args(query, scratch), "--results-format", "nt", "--results-file", str(target)]
    if union:
        args.append("--union-default-graph")
    try:
        invoke(args, "running a CONSTRUCT query", trace=query)
    finally:
        for path in scratch:
            path.unlink(missing_ok=True)


def scalar(store: Path, query: str, union: bool = False) -> int:
    rows = select(store, query, union)
    if len(rows) != 1 or len(rows[0]) != 1:
        raise RgError.of("OXIGRAPH_BAD_SCALAR", "Expected one row with one value.", query=query, rows=rows[:5])
    return int(next(iter(rows[0].values())))


def graph_counts(store: Path) -> dict[str, int]:
    rows = select(store, "SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g")
    return {row["g"]: int(row["n"]) for row in rows}


def default_graph_count(store: Path) -> int:
    return scalar(store, "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }")
