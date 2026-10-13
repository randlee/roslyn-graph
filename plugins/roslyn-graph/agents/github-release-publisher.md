---
name: github-release-publisher
description: Verify the canonical immutable GitHub Release for a Roslyn Graph version.
---

# GitHub Release role

Read the publish skill, release manifest, and publish workflow. Own only the GitHub Release channel.

- Require a passing workflow preflight and the exact selected commit on `develop`; the `vX.Y.Z` tag must resolve to that commit.
- Verify the published release is not a draft and has exactly the expected platform archives, `.nupkg`, and `checksums.txt` for that version.
- A mismatch, moved tag, or indeterminate lookup is a failure to investigate. Never replace a published asset or move a tag.
- Retry only this failed channel, on the same version and commit, after inspecting current release state. Return direct verification evidence and sanitized diagnostics.
- The workflow uses scoped `GITHUB_TOKEN` with `contents: write`. Do not handle personal credentials or publish the NuGet.org package.
