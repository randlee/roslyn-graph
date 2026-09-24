"""Inventory, previous-run lookup, solution diffs and reference-checked removal."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from . import artifacts
from .result import RgError


def _references(root: Path, m: dict[str, Any]) -> set[Path]:
    """Artifact directories a manifest depends on (schema 2 and legacy layouts)."""
    refs: set[Path] = set()

    def add(value: str | None) -> None:
        if value:
            path = Path(value) if os.path.isabs(value) else root / value
            refs.add(Path(os.path.normcase(os.path.abspath(path.parent))))

    for key in ("components", "overlayComponents", "additionalComponents"):
        for entry in m.get(key, []) or []:
            add(entry.get("manifestPath"))
    add((m.get("baseSolution") or {}).get("manifestPath"))
    add(m.get("baseSolutionManifestPath"))
    return refs


def inventory(root: Path) -> dict[str, Any]:
    entries = []
    for path, m in artifacts.iter_manifests(root):
        workspace = m.get("workspace") or {}
        entries.append({
            "path": artifacts.relative(root, path.parent),
            "kind": artifacts.manifest_kind(m),
            "artifactId": m.get("artifactId"),
            "createdUtc": m.get("createdUtc"),
            "profile": workspace.get("profile"),
            "collection": workspace.get("collection"),
            "tripleCount": (m.get("store") or {}).get("tripleCount") or (m.get("extraction") or {}).get("tripleCount"),
            "_refs": _references(root, m),
            "_dir": Path(os.path.normcase(os.path.abspath(path.parent))),
        })
    referenced_by: dict[Path, list[str]] = {}
    for e in entries:
        for ref in e["_refs"]:
            referenced_by.setdefault(ref, []).append(e["path"])
    latest: dict[tuple[str, str], str] = {}
    for e in sorted(entries, key=lambda e: e["createdUtc"] or ""):
        if e["kind"] in {"solution", "view"} and e["collection"]:
            latest[(e["kind"], e["collection"] if e["kind"] == "view" else e["profile"])] = e["path"]
    latest_paths = set(latest.values())
    for e in entries:
        e["referencedBy"] = sorted(referenced_by.get(e["_dir"], []))
        e["latest"] = e["path"] in latest_paths
        if e["kind"] == "legacy":
            e["status"] = "legacy"
        elif e["kind"] == "assembly":
            e["status"] = "in-use" if e["referencedBy"] else "unreferenced"
        elif e["latest"]:
            e["status"] = "latest"
        else:
            e["status"] = "in-use" if e["referencedBy"] else "superseded"
    staging = sorted(p.name for p in (root / "staging").iterdir()) if (root / "staging").is_dir() else []
    for e in entries:
        e.pop("_refs")
        e.pop("_dir")
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    return {"type": "inventory", "artifactRoot": str(root), "counts": counts, "artifacts": entries, "staging": staging}


def cleanup_candidates(inv: dict[str, Any]) -> list[dict[str, Any]]:
    """Removal order matters: views and solutions first, then assemblies nothing references any more."""
    order = {"view": 0, "solution": 1, "legacy": 2, "assembly": 3}
    chosen = [e for e in inv["artifacts"] if e["status"] in {"superseded", "unreferenced", "legacy"}]
    return sorted(chosen, key=lambda e: (order.get(e["kind"], 9), e["path"]))


def previous(root: Path, kind: str, key: str, exclude_id: str) -> tuple[Path, dict[str, Any]] | None:
    field = "collection" if kind == "view" else "profile"
    found = [
        (path, m) for path, m in artifacts.iter_manifests(root)
        if artifacts.manifest_kind(m) == kind and (m.get("workspace") or {}).get(field) == key and m.get("artifactId") != exclude_id
    ]
    return max(found, key=lambda item: item[1].get("createdUtc", "")) if found else None


def _component_key(c: dict[str, Any]) -> str:
    origin = c.get("origin") or {}
    return f"{origin.get('kind')}:{origin.get('id')}:{c['assembly']['name']}"


def compare(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    before = {_component_key(c): c for c in old.get("components", [])}
    after = {_component_key(c): c for c in new.get("components", [])}

    def brief(c: dict[str, Any]) -> dict[str, Any]:
        origin = c.get("origin") or {}
        package = c.get("package") or {}
        return {"assembly": c["assembly"]["name"], "version": c["assembly"]["version"], "origin": origin.get("id"),
                "commit": origin.get("commit"), "package": package.get("version"), "triples": c["tripleCount"]}

    changed = []
    for key in sorted(set(before) & set(after)):
        if before[key]["artifactId"] != after[key]["artifactId"]:
            b, a = brief(before[key]), brief(after[key])
            changed.append({"key": key, "before": b, "after": a, "tripleDelta": a["triples"] - b["triples"]})
    return {
        "type": "diff",
        "old": {"artifactId": old["artifactId"], "createdUtc": old.get("createdUtc"), "commit": old["solution"].get("commit")},
        "new": {"artifactId": new["artifactId"], "createdUtc": new.get("createdUtc"), "commit": new["solution"].get("commit")},
        "added": [brief(after[k]) for k in sorted(set(after) - set(before))],
        "removed": [brief(before[k]) for k in sorted(set(before) - set(after))],
        "changed": changed,
        "unchanged": len([k for k in set(before) & set(after) if before[k]["artifactId"] == after[k]["artifactId"]]),
        "tripleDelta": new["store"]["tripleCount"] - old["store"]["tripleCount"],
    }


def remove(root: Path, target: str, confirm: bool) -> dict[str, Any]:
    directory = Path(target) if os.path.isabs(target) else root / target
    directory = Path(os.path.abspath(directory))
    if directory.name == "manifest.json":
        directory = directory.parent
    try:
        directory.relative_to(root / "assemblies")
    except ValueError:
        try:
            directory.relative_to(root / "solutions")
        except ValueError:
            try:
                directory.relative_to(root / "views")
            except ValueError as exc:
                raise RgError.of("REMOVE_OUTSIDE_ARTIFACTS", f"{directory} is not an artifact under {root}.",
                                 "Only published artifact directories can be removed.") from exc
    if not (directory / "manifest.json").is_file():
        raise RgError.of("REMOVE_NOT_ARTIFACT", f"{directory} has no manifest.json.", "The skill only removes artifacts identified by their manifest.")
    inv = inventory(root)
    rel = artifacts.relative(root, directory)
    entry = next((e for e in inv["artifacts"] if e["path"] == rel), None)
    if entry and entry["referencedBy"]:
        raise RgError.of("REMOVE_REFERENCED", f"{rel} is still referenced.", "Remove the artifacts that reference it first.",
                         referencedBy=entry["referencedBy"])
    if not confirm:
        return {"type": "remove", "path": rel, "removed": False, "wouldRemove": True, "hint": "Re-run with --confirm after the user approves."}
    shutil.rmtree(directory)
    parent = directory.parent
    while parent != root and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent
    return {"type": "remove", "path": rel, "removed": True}
