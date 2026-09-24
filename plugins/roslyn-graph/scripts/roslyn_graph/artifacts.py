"""Artifact identity, layout, publication and inventory.

Identity strings are built from manifest fields only, so validation can recompute every artifact ID
from its manifest. See reference/artifact-layout.md.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .result import RgError
from .util import sha256_text

MANIFEST_SCHEMA = 2
PROJECTION_VERSION = "logical-types/v2"  # v2: domain = own, fully extracted types only
MAX_CURRENT_PATH = 240


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def artifact_root(data_root: str | Path | None) -> Path:
    value = str(data_root) if data_root else os.environ.get("ROSLYN_GRAPH_DATA_ROOT", "")
    if not value:
        raise RgError.of(
            "DATA_ROOT_MISSING",
            "No data root: pass --data-root or set ROSLYN_GRAPH_DATA_ROOT.",
            "Artifacts are written beneath <data-root>/.roslyn-graph.",
        )
    return Path(os.path.abspath(value)) / ".roslyn-graph"


# ---- identity -------------------------------------------------------------------------------


def assembly_identity(m: dict[str, Any]) -> str:
    extractor = m["extraction"]["extractorId"]
    if m["origin"]["kind"] == "source":
        o, b = m["origin"], m["build"]
        parts = ["assembly/v2", "source", o["id"], o["commit"], o.get("dirtyHash", ""), b["fingerprint"], b["targetFramework"]]
    else:
        p = m["package"]
        parts = ["assembly/v2", "nuget", p["id"].lower(), p["version"], p["nupkgSha256"], p["asset"], p["dependenciesHash"], p["targetFramework"]]
    return "|".join(parts + [m["assembly"]["sha256"], extractor])


def solution_identity(m: dict[str, Any]) -> str:
    s = m["solution"]
    parts = [
        "solution/v2", s["profile"], s["repository"], s["relativePath"], s["commit"], s.get("dirtyHash", ""),
        s["fingerprint"], s["targetFramework"], s["configuration"], s["platform"],
    ]
    return "|".join(parts + sorted(c["artifactId"] for c in m["components"]))


def view_identity(m: dict[str, Any]) -> str:
    v = m["view"]
    parts = ["view/v2", v["baseSolutionArtifactId"], v["policy"], ",".join(sorted(v["policyAssemblies"])), v["projectionVersion"]]
    return "|".join(parts + sorted(c["artifactId"] for c in m["overlayComponents"]))


IDENTITY = {"assembly": assembly_identity, "solution": solution_identity, "view": view_identity}


def artifact_id(identity: str) -> str:
    return sha256_text(identity)


def graph_iri(kind: str, artifact_id_value: str) -> str:
    return f"urn:roslyn-graph:{kind}:{artifact_id_value[:32]}"


# ---- layout ---------------------------------------------------------------------------------

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def segment(value: str) -> str:
    cleaned = _UNSAFE.sub("_", value).strip(" .")
    if not cleaned:
        raise RgError.of("PATH_SEGMENT_EMPTY", f"Cannot build a directory name from {value!r}.")
    return cleaned


def base_dir(root: Path, kind: str, **keys: str) -> Path:
    if kind == "assembly-source":
        return root / "assemblies" / "source" / segment(keys["origin"])
    if kind == "assembly-nuget":
        return root / "assemblies" / "nuget" / segment(keys["package"]) / segment(keys["version"])
    if kind == "solution":
        return root / "solutions" / segment(keys["repository"]) / segment(keys["name"])
    if kind == "view":
        return root / "views"
    raise ValueError(kind)


def resolve_destination(base: Path, full_id: str) -> tuple[Path, bool]:
    """Return (directory, exists). Prefix lengths 20, 32, 64; a directory owned by another ID moves on."""
    for length in (20, 32, 64):
        candidate = base / full_id[:length]
        if not candidate.exists():
            return candidate, False
        manifest = candidate / "manifest.json"
        if not manifest.is_file():
            raise RgError.of(
                "ARTIFACT_DIR_WITHOUT_MANIFEST",
                f"{candidate} exists but has no manifest.json.",
                "It is not a published artifact. Inspect it, then remove it by hand; the skill never deletes unknown directories.",
                path=str(candidate),
            )
        if read_manifest(manifest).get("artifactId") == full_id:
            return candidate, True
    raise RgError.of("ARTIFACT_ID_COLLISION", f"Prefixes of {full_id} are all taken by other artifacts under {base}.")


def check_path_length(destination: Path) -> None:
    current = destination / "store.oxigraph" / "CURRENT"
    if len(str(current)) > MAX_CURRENT_PATH:
        raise RgError.of(
            "ARTIFACT_PATH_TOO_LONG",
            f"{current} is {len(str(current))} characters; RocksDB cannot reopen stores beyond {MAX_CURRENT_PATH} on Windows.",
            "Use a shorter data root.",
        )


def new_staging(root: Path, label: str) -> Path:
    path = root / "staging" / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{segment(label)[:40]}-{uuid.uuid4().hex[:8]}"
    (path / "artifact").mkdir(parents=True)
    return path


def publish(root: Path, staging: Path, destination: Path, full_id: str) -> bool:
    """Move staging/artifact to destination. Returns False when an identical artifact won the race."""
    locks = root / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    lock = locks / f"{full_id}.lock"
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RgError.of(
            "ARTIFACT_LOCKED",
            f"Another run is publishing {full_id[:20]} (lock {lock}).",
            "Wait for it to finish. If no run is active the lock is stale: delete the lock file.",
            lock=str(lock),
        ) from exc
    try:
        os.write(handle, f"{os.getpid()} {utc_now()}".encode())
        os.close(handle)
        if destination.exists():
            if (destination / "manifest.json").is_file() and read_manifest(destination / "manifest.json").get("artifactId") == full_id:
                shutil.rmtree(staging)
                return False
            raise RgError.of("ARTIFACT_DESTINATION_TAKEN", f"{destination} appeared during the run and is not this artifact.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.rename(staging / "artifact", destination)
        shutil.rmtree(staging)
        return True
    finally:
        lock.unlink(missing_ok=True)


# ---- manifests ------------------------------------------------------------------------------


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RgError.of("MANIFEST_UNREADABLE", f"Cannot read {path}: {exc}", path=str(path)) from exc


def write_manifest(directory: Path, manifest: dict[str, Any]) -> Path:
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def iter_manifests(root: Path) -> Iterator[tuple[Path, dict[str, Any]]]:
    for area in ("assemblies", "solutions", "views"):
        base = root / area
        if base.is_dir():
            for path in sorted(base.rglob("manifest.json")):
                yield path, read_manifest(path)


def manifest_kind(m: dict[str, Any]) -> str:
    if m.get("schemaVersion") != MANIFEST_SCHEMA:
        return "legacy"
    return m.get("kind", "unknown")


def relative(root: Path, path: Path) -> str:
    return Path(os.path.relpath(path, root)).as_posix()
