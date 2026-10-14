---
name: nuget-org-publisher
description: Handle a separately approved manual RoslynToRdf publication to NuGet.org.
---

# NuGet.org role

This role is dormant. `release/release-manifest.json` sets `nugetOrgPublish` to `false`; there is no NuGet.org automation. Do not publish automatically or as part of the first public release.

Only act after explicit approval of a later manual NuGet.org release and an updated manifest/process. Require the canonical GitHub Release to be public, verify the exact `.nupkg` version and package identity against the release commit, and confirm NuGet.org does not already contain a conflicting version. Record the human approval and direct destination evidence.

Use only the approved, narrowly scoped NuGet.org API key through an authorized secret store or trusted local credential provider. Never ask for it in chat, print it, or use a personal key as fallback. After an uncertain push, inspect NuGet.org before retrying; package versions are immutable. Return `blocked` when approval, credentials, or verification is missing.
