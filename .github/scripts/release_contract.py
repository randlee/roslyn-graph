#!/usr/bin/env python3
"""Validate the version and publication contract used by the release workflow."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "release" / "release-manifest.json"


def load_contract() -> tuple[dict, str]:
    contract = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if contract.get("schemaVersion") != 1:
        raise ValueError("unsupported release manifest schemaVersion")
    props_path = ROOT / contract["versionSource"]
    props = ET.parse(props_path).getroot()
    property_name = contract["versionProperty"]
    version = next((node.text for node in props.iter(property_name) if node.text), None)
    if version is None:
        raise ValueError(f"{property_name} is missing from {props_path.relative_to(ROOT)}")
    if not re.fullmatch(contract["versionPattern"], version):
        raise ValueError(f"invalid project version in {props_path.relative_to(ROOT)}: {version}")
    for item in contract.get("additionalVersionSources", []):
        relative_path = item["path"]
        source_path = ROOT / relative_path
        source = json.loads(source_path.read_text(encoding="utf-8"))
        value = source
        for component in item.get("jsonPath", ["version"]):
            value = value[component]
        if value != version:
            raise ValueError(f"version in {relative_path} must match {props_path.relative_to(ROOT)} ({version})")
    if contract.get("nugetOrgPublish") is not False:
        raise ValueError("nugetOrgPublish must remain false")
    return contract, version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", help="requested release version; omit for contract-only validation")
    parser.add_argument("--github-output", help="append validated workflow outputs to this file")
    args = parser.parse_args()
    try:
        contract, version = load_contract()
        if args.version and args.version.removeprefix("v") != version:
            raise ValueError(f"requested version {args.version!r} does not match project version {version!r}")
        expected_runtimes = {"win-x64", "osx-x64", "osx-arm64"}
        actual_runtimes = {target["runtime"] for target in contract["releaseArchives"]}
        if actual_runtimes != expected_runtimes:
            raise ValueError(f"release archive runtimes must be {sorted(expected_runtimes)}")
        formats = {target["runtime"]: target["extension"] for target in contract["releaseArchives"]}
        expected_formats = {"win-x64": "zip", "osx-x64": "tar.gz", "osx-arm64": "tar.gz"}
        if formats != expected_formats:
            raise ValueError(f"release archive formats must be {expected_formats}")
        matrix = [{"runner": item["runner"], "rid": item["runtime"], "extension": item["extension"]} for item in contract["releaseArchives"]]
        result = {"version": version, "packageId": contract["packageId"], "runtimes": sorted(actual_runtimes), "matrix": matrix}
        if args.github_output:
            with Path(args.github_output).open("a", encoding="utf-8") as output:
                output.write(f"version={version}\n")
                output.write(f"archive_matrix={json.dumps(matrix, separators=(',', ':'))}\n")
        print(json.dumps(result))
        return 0
    except (OSError, KeyError, ValueError, json.JSONDecodeError, ET.ParseError) as exc:
        print(f"release contract error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
