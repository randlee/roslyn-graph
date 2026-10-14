---
name: roslyn-graph-publish
description: Prepare, publish, verify, or recover a Roslyn Graph release across its independent distribution channels.
---

# Publish Roslyn Graph

Use the repository's `release/release-manifest.json` as the authority for package identity, version source, archive targets, registry, and enabled channels. Read it and `.github/workflows/publish.yml` before any release action. Do not infer that a channel is enabled from these instructions.

## Channel boundaries

- **GitHub Release** is the canonical versioned release with platform archives, NuGet package file, and checksums. The workflow creates or verifies an immutable `vX.Y.Z` release on the selected `develop` commit.
- **GitHub Packages** is an independent NuGet feed publication performed by the release workflow. Its package is not the NuGet.org listing.
- **NuGet.org** is disabled (`nugetOrgPublish: false`). Never publish there automatically, including on the first release. Any future NuGet.org release is a separately approved manual action after the initial public release and an explicit manifest/process change.
- **Homebrew, Scoop, and WinGet** are separate downstream channels. They are not enabled by the current manifest/workflow. Report them as `not_configured` until a reviewed integration and destination are declared; do not improvise a tap, bucket, or package submission.

## Gate and evidence

Before publishing, require the requested version to match `Directory.Build.props` and the manifest, the workflow preflight to pass on the exact selected commit, and the release tag to resolve to that commit in `develop`. A preflight run validates/builds/tests but publishes nothing. A release run has side effects.

Track each channel independently as `passed`, `failed`, `blocked`, or `not_configured`. A channel passes only with direct destination evidence: GitHub Release tag and exact expected asset set; GitHub Packages package/version; or, for a future downstream channel, its public formula/manifest/package and expected version/hash. Report the version, commit/tag, channel, observed evidence, and sanitized failure reason. Never describe an unobserved result as success.

Published artifacts are immutable. If a channel fails, inspect current remote state first. Retry only that failed channel against the same version and release commit after the cause is understood. Never move/recreate a tag, replace successful assets, or rerun unrelated channels as a shortcut. An existing release with an unexpected asset set or an indeterminate API result fails closed for investigation.

## Credentials and prerequisites

The current workflow uses its scoped `GITHUB_TOKEN`: `contents: write` for the GitHub Release and `packages: write` for GitHub Packages. Do not request, print, inspect, or substitute credentials. Manual downstream channels require their own declared destination, maintainer permissions, and narrowly scoped repository secret or approved submission mechanism before they can be enabled. Missing prerequisites mean `blocked` or `not_configured`, never a reason to use a personal token.

For role procedures, read the matching file under `agents/`. Keep channel work isolated and return its evidence to the release coordinator.
