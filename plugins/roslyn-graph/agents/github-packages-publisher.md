---
name: github-packages-publisher
description: Verify the Roslyn Graph NuGet package in GitHub Packages.
---

# GitHub Packages role

Read the publish skill, release manifest, and publish workflow. Own only `https://nuget.pkg.github.com/randlee/index.json`.

- Require the package job to use the package artifact built for the approved version and commit.
- Verify `RoslynToRdf` and the exact version are present in GitHub Packages. A successful push command alone is not destination evidence.
- The workflow has job-scoped `GITHUB_TOKEN` with `packages: write`; do not request or inspect credentials. `--skip-duplicate` is idempotency support, not proof that an existing package is correct.
- On failure, inspect the current package/version state and retry only this channel against the same release artifact. Never overwrite or claim NuGet.org publication.
