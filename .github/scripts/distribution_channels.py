#!/usr/bin/env python3
"""Verify published GitHub release inputs and render distribution metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request


ARCHIVE_PREFIX = "roslyn-graph"
IDENTIFIER = "Randlee.RoslynToRdf"
HOMEPAGE = "https://github.com/randlee/roslyn-graph"
DESCRIPTION = "Extract .NET assembly type graphs to RDF"
LICENSE = "MIT"


def api_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "roslyn-graph-distribution-workflow",
        },
    )
    token = os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "roslyn-graph-distribution-workflow"})
    token = os.environ.get("GH_TOKEN")
    if token and "api.github.com" in url:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def expected_names(version: str) -> list[str]:
    return [
        f"{ARCHIVE_PREFIX}_{version}_win-x64.zip",
        f"{ARCHIVE_PREFIX}_{version}_osx-x64.tar.gz",
        f"{ARCHIVE_PREFIX}_{version}_osx-arm64.tar.gz",
        f"RoslynToRdf.{version}.nupkg",
        "checksums.txt",
    ]


def verify(repo: str, tag: str, output: Path) -> dict:
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ValueError("tag must be a stable vMAJOR.MINOR.PATCH release tag")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("repository must be owner/name")
    version = tag[1:]
    release = api_json(f"https://api.github.com/repos/{repo}/releases/tags/{tag}")
    if release.get("tag_name") != tag or release.get("draft") is not False or release.get("prerelease") is not False:
        raise ValueError(f"{tag} is not a published stable GitHub Release")
    required_names = expected_names(version)
    assets = {item.get("name"): item for item in release.get("assets", [])}
    if set(assets) != set(required_names):
        raise ValueError(f"release assets do not match the archive and checksum contract: expected {sorted(required_names)}")
    names = sorted(assets)
    output.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}
    for name in names:
        asset = assets[name]
        api_digest = asset.get("digest")
        if not isinstance(api_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", api_digest):
            raise ValueError(f"GitHub API has no SHA-256 digest for release asset {name}")
        path = output / name
        download(asset["browser_download_url"], path)
        with path.open("rb") as downloaded:
            local_digest = hashlib.file_digest(downloaded, "sha256").hexdigest()
        if api_digest != f"sha256:{local_digest}":
            raise ValueError(f"downloaded asset digest differs from GitHub API for {name}")
        digests[name] = local_digest

    checksum_entries: dict[str, str] = {}
    for line in (output / "checksums.txt").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})\s+\*?([^\s]+)", line.strip())
        if not match:
            raise ValueError("checksums.txt contains a malformed entry")
        digest, name = match.groups()
        if name in checksum_entries:
            raise ValueError(f"checksums.txt contains duplicate entry for {name}")
        checksum_entries[name] = digest
    if checksum_entries != {name: digests[name] for name in names if name != "checksums.txt"}:
        raise ValueError("checksums.txt does not exactly match the verified release assets")

    result = {"repo": repo, "tag": tag, "version": version, "assets": digests}
    (output / "verified-release.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def load_verified(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", data.get("tag", "")):
        raise ValueError("verified-release.json is invalid")
    if data.get("version") != data["tag"][1:]:
        raise ValueError("verified release tag and version disagree")
    return data


def formula(data: dict, output: Path) -> None:
    base = f"https://github.com/{data['repo']}/releases/download/{data['tag']}/"
    x64 = f"{ARCHIVE_PREFIX}_{data['version']}_osx-x64.tar.gz"
    arm = f"{ARCHIVE_PREFIX}_{data['version']}_osx-arm64.tar.gz"
    text = f'''class RoslynToRdf < Formula
  desc "{DESCRIPTION}"
  homepage "{HOMEPAGE}"
  depends_on :macos
  url "{base}{x64}"
  sha256 "{data['assets'][x64]}"
  version "{data['version']}"
  license "{LICENSE}"

  on_arm do
    url "{base}{arm}"
    sha256 "{data['assets'][arm]}"
  end

  def install
    bin.install "RoslynToRdf.Cli" => "roslyn2rdf"
  end

  test do
    assert_match "roslyn2rdf", shell_output("#{{bin}}/roslyn2rdf --help")
  end
end
'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def scoop(data: dict, output: Path) -> None:
    name = f"{ARCHIVE_PREFIX}_{data['version']}_win-x64.zip"
    manifest = {
        "version": data["version"],
        "description": DESCRIPTION,
        "homepage": HOMEPAGE,
        "license": LICENSE,
        "architecture": {
            "64bit": {
                "url": f"https://github.com/{data['repo']}/releases/download/{data['tag']}/{name}",
                "hash": data["assets"][name],
            }
        },
        "bin": [["RoslynToRdf.Cli.exe", "roslyn2rdf"]],
        "checkver": {"github": HOMEPAGE},
        "autoupdate": {
            "architecture": {
                "64bit": {
                    "url": f"https://github.com/{data['repo']}/releases/download/v$version/{ARCHIVE_PREFIX}_$version_win-x64.zip"
                }
            }
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def winget(data: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    version = data["version"]
    base = f"https://github.com/{data['repo']}/releases/download/{data['tag']}/"
    installer = f"{ARCHIVE_PREFIX}_{version}_win-x64.zip"
    common = f"PackageIdentifier: {IDENTIFIER}\nPackageVersion: {version}\n"
    files = {
        f"{IDENTIFIER}.yaml": (
            "PackageIdentifier: " + IDENTIFIER + "\n"
            "PackageVersion: " + version + "\n"
            "PackageLocale: en-US\n"
            "Publisher: Rand Lee\n"
            "PackageName: RoslynToRdf\n"
            "License: MIT\n"
            "ShortDescription: " + DESCRIPTION + "\n"
            "ManifestType: defaultLocale\n"
            "ManifestVersion: 1.6.0\n"
        ),
        f"{IDENTIFIER}.installer.yaml": (
            common +
            "Architecture: x64\n"
            "InstallerType: zip\n"
            "NestedInstallerType: portable\n"
            "NestedInstallerFiles:\n"
            "  - RelativeFilePath: RoslynToRdf.Cli.exe\n"
            "    PortableCommandAlias: roslyn2rdf.exe\n"
            "InstallerUrl: " + base + installer + "\n"
            "InstallerSha256: " + data["assets"][installer] + "\n"
            "ManifestType: installer\n"
            "ManifestVersion: 1.6.0\n"
        ),
        f"{IDENTIFIER}.version.yaml": (
            common + "ManifestType: version\nManifestVersion: 1.6.0\n"
        ),
    }
    for name, content in files.items():
        (output / name).write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--repo", required=True)
    verify_parser.add_argument("--tag", required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    for command in ("homebrew", "scoop", "winget"):
        item = commands.add_parser(command)
        item.add_argument("--verified", type=Path, required=True)
        item.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "verify":
        print(json.dumps(verify(args.repo, args.tag, args.output), indent=2))
    else:
        data = load_verified(args.verified)
        {"homebrew": formula, "scoop": scoop, "winget": winget}[args.command](data, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
