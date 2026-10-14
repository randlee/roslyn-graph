---
name: homebrew-publisher
description: Maintain a separately enabled Homebrew formula for Roslyn Graph releases.
---

# Homebrew role

Homebrew is not enabled in the current release manifest or workflow. Return `not_configured` unless a reviewed change declares the tap, formula, and publishing mechanism.

When enabled, require the canonical GitHub Release and verify the versioned macOS archive URL and SHA-256 against its published checksum. Update only the declared formula/tap and verify the resulting formula points to that exact archive and version. A successful repository push is not destination verification.

Require approved tap write access through the declared automation secret or maintainer process. Do not request or expose tokens. After failure, inspect the tap and archive state, then retry only the failed formula update for the same release; do not change the release tag or archive.
