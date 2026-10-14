#!/usr/bin/env bash
# Resolve docli checkout for build/regenerate scripts (sourced, not executed).
resolve_docli_root() {
  local repo_root=$1
  if [[ -n "${DOCLI_ROOT:-}" ]]; then
    if [[ -f "$DOCLI_ROOT/Cargo.toml" && -d "$DOCLI_ROOT/dotnet/src/Docli" ]]; then
      printf '%s' "$(cd "$DOCLI_ROOT" && pwd)"
      return 0
    fi
    echo "DOCLI_ROOT is set but missing docli layout: $DOCLI_ROOT" >&2
    return 1
  fi
  local candidate
  for candidate in "$repo_root/docli" "$repo_root/../../../docli"; do
    if [[ -f "$candidate/Cargo.toml" && -d "$candidate/dotnet/src/Docli" ]]; then
      printf '%s' "$(cd "$candidate" && pwd)"
      return 0
    fi
  done
  echo "docli not found. Clone https://github.com/randlee/docli to $repo_root/docli or set DOCLI_ROOT." >&2
  return 1
}
