#!/usr/bin/env bash
# Print the body of the "## [<version>]" section of CHANGELOG.md.
# Exits non-zero when the section is missing or empty.
set -euo pipefail

if [[ $# -ne 1 || -z "$1" ]]; then
    echo "Usage: $0 <version>   (e.g. 1.0.0)" >&2
    exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHANGELOG="${CHANGELOG:-$ROOT_DIR/CHANGELOG.md}"
VERSION="$1"

if [[ ! -f "$CHANGELOG" ]]; then
    echo "ERROR: $CHANGELOG not found" >&2
    exit 1
fi

notes="$(awk -v ver="$VERSION" '
    /^## \[/ {
        if (found) exit
        if (index($0, "## [" ver "]") == 1) { found = 1; next }
    }
    found { print }
' "$CHANGELOG")"

# Trim leading/trailing blank lines.
notes="$(printf '%s\n' "$notes" | sed -e '/./,$!d' | sed -e ':a' -e '/^\n*$/{$d;N;ba' -e '}')"

if [[ -z "${notes//[[:space:]]/}" ]]; then
    echo "ERROR: no CHANGELOG section for version $VERSION (or it is empty)" >&2
    exit 1
fi

printf '%s\n' "$notes"
