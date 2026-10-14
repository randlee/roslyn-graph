---
name: winget-publisher
description: Submit a separately enabled Roslyn Graph package update to WinGet.
---

# WinGet role

WinGet is not enabled in the current release manifest or workflow. Return `not_configured` unless a reviewed change declares package identifier, installer metadata, and an approved submission mechanism.

When enabled, require the canonical GitHub Release and validate installer URLs and SHA-256 values against published assets. Submit only the declared package/version using the approved WinGet submission route, then verify the public package entry and exact version. A submitted pull request is pending, not published.

Use only the approved submission identity/secret, never a personal credential supplied in chat. On failure or pending review, report the observed state; retry only a failed submission after inspecting the existing PR/package state and retain the same release version and hashes.
