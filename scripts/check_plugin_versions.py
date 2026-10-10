#!/usr/bin/env python3
"""Keep the shipped Claude and Codex plugin manifests on the NuGet package version."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROPS = REPO / "Directory.Build.props"
MANIFESTS = [
    REPO / "plugins/roslyn-graph/.codex-plugin/plugin.json",
    REPO / "plugins/roslyn-graph/.claude-plugin/plugin.json",
]


def package_version() -> str:
    match = re.search(r"<Version>([^<]+)</Version>", PROPS.read_text(encoding="utf-8"))
    if not match:
        raise ValueError("Directory.Build.props must define <Version>.")
    return match.group(1).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="Update manifests to the package version.")
    args = parser.parse_args()
    version = package_version()
    mismatches = []
    for manifest in MANIFESTS:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("version") != version:
            if args.fix:
                data["version"] = version
                manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            else:
                mismatches.append({"manifest": str(manifest.relative_to(REPO)), "actual": data.get("version"), "expected": version})
    print(json.dumps({"type": "plugin-version", "version": version, "inSync": not mismatches, "fixed": args.fix}, indent=2))
    if mismatches:
        print(json.dumps({"type": "error", "errors": mismatches}, indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
