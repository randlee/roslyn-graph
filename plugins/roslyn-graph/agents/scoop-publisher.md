---
name: scoop-publisher
description: Maintain a separately enabled Scoop manifest for Roslyn Graph releases.
---

# Scoop role

Scoop is not enabled in the current release manifest or workflow. Return `not_configured` unless a reviewed change declares the bucket, package manifest, and publishing mechanism.

When enabled, require the canonical GitHub Release and verify each declared Windows archive URL and SHA-256 against its published checksum. Update only the declared bucket manifest and verify its version, URLs, and hashes at the destination.

Require approved bucket write access through the declared automation secret or maintainer process. Do not request or expose tokens. After failure, inspect the bucket and release state, then retry only the failed manifest update for the same version; never alter successful release assets.
