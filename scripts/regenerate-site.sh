#!/usr/bin/env bash
# Refresh generated GitHub Pages content under site/.
#
# Static (edit in git, not overwritten here):
#   site/index.html
#   site/announcements/
#
# Generated:
#   site/cli/index.html  — roslyn2rdf CLI reference via docli
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for path in site/index.html site/announcements/index.html; do
  if [[ ! -f "$ROOT/$path" ]]; then
    echo "missing static site file: $path" >&2
    exit 1
  fi
done

echo "Static site pages: site/index.html, site/announcements/ (unchanged)"
"$ROOT/scripts/regenerate-site-cli.sh"
echo "Site regenerate complete."
