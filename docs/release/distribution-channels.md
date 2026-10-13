# Distribution channel workflows

Homebrew, Scoop, and WinGet are separate, manual post-release workflows. None
has a `release` or tag-push trigger. Dispatch the desired workflow with the
published `vMAJOR.MINOR.PATCH` tag after the GitHub Release is complete.

Every workflow checks GitHub's release API for the exact tag, requires a
published stable release, requires the exact archive set from
`release/release-manifest.json` plus its NuGet package and `checksums.txt`, and
downloads each asset. It compares the bytes to GitHub's API SHA-256 digest and
then compares every asset digest to `checksums.txt`. Unknown, incomplete, or
inconsistent release state fails closed. The workflows do not alter release
assets or create a release; use only the canonical, completed release tag for
which the release process has frozen its assets.

## Homebrew

Set repository variable `HOMEBREW_TAP_REPOSITORY` to the owner/repository for
the tap. Optionally set `HOMEBREW_FORMULA_PATH` (default
`Formula/roslyn-to-rdf.rb`) and secret `HOMEBREW_TAP_TOKEN` with write access to
that repository. The formula uses the x64
and arm64 macOS release archives; there is no Linux release target today.

The workflow validates formula syntax, commits only that formula, and retries
pushes by fetching and rebasing. If the remote formula already matches the
release, it exits successfully without a new commit.

## Scoop

Set `SCOOP_BUCKET_REPOSITORY`; optionally set `SCOOP_MANIFEST_PATH` (default
`bucket/roslyn-to-rdf.json`) and `SCOOP_BUCKET_TOKEN`. The manifest references
the Windows x64 ZIP and its verified SHA-256. The workflow validates JSON,
commits only the configured manifest, and safely retries a rejected push. An
already matching remote manifest is a successful no-op.

## WinGet

Every run prepares and validates the three WinGet manifests and uploads them as
`winget-manifests-v<tag>`. This works on the first run without any submission
credential. To also upsert a pull request, set `WINGET_FORK_REPOSITORY` to an
existing fork of `microsoft/winget-pkgs` and secret `WINGET_GITHUB_TOKEN` with
write access to that fork and permission to open PRs in `microsoft/winget-pkgs`.
The workflow uses a deterministic version branch. It treats an existing open
PR as success, an already merged PR as complete, and a closed unmerged PR or
indeterminate API response as an error for maintainer inspection. It never
pushes directly to Microsoft's repository. The PR is a pending submission,
not proof that WinGet has published the package.

## Retry and failure behavior

Runs are serialized per channel and tag. Re-dispatching the same version
verifies the same immutable inputs and performs a no-op when the destination
already contains the rendered version. A missing repository, token required
for a private destination, rejected conflict, malformed destination state, or
incomplete API response is not interpreted as success. Inspect remote state
before retrying a failed update.
