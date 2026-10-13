#!/usr/bin/env bash
# Render roslyn2rdf CLI reference to site/cli/index.html via sibling docli checkout.
# Prefer scripts/regenerate-site.sh for the full Pages tree (static home + CLI docs).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=resolve-docli-root.sh
source "$(dirname "${BASH_SOURCE[0]}")/resolve-docli-root.sh"
DOCLI_ROOT="$(resolve_docli_root "$ROOT")"
DOCLI_BIN="${DOCLI_BIN:-$DOCLI_ROOT/target/release/docli}"
EXPORT="$ROOT/tools/RoslynToRdf.DocliExport/RoslynToRdf.DocliExport.csproj"

if [[ ! -x "$DOCLI_BIN" && "$DOCLI_BIN" == "$DOCLI_ROOT/target/release/docli" ]]; then
  (cd "$DOCLI_ROOT" && cargo build --release -q --bin docli)
fi

if [[ ! -f "$DOCLI_ROOT/dotnet/src/Docli.Tool/bin/Release/net10.0/Docli.Tool.dll" ]]; then
  (cd "$DOCLI_ROOT" && PATH="${HOME}/.dotnet:${PATH}" dotnet build dotnet/Docli.sln -c Release --nologo)
fi

mkdir -p "$ROOT/site/cli"
cd "$ROOT"
PATH="${HOME}/.dotnet:${PATH}" "$DOCLI_BIN" generate \
  --dotnet-project "$EXPORT" \
  --html site/cli \
  --json
test -f site/cli/index.html
echo "Wrote site/cli/index.html"
