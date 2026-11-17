#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGINS_DIR="$ROOT_DIR/moodle-plugins"
DIST_DIR="$ROOT_DIR/dist"

STAGING_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$STAGING_DIR"
}
trap cleanup EXIT

mkdir -p "$DIST_DIR"

build_zip() {
    local src_dir="$1"
    local zip_root="$2"
    local zip_name="$3"

    if [[ ! -d "$PLUGINS_DIR/$src_dir" ]]; then
        echo "ERROR: Missing plugin directory: $PLUGINS_DIR/$src_dir" >&2
        exit 1
    fi

    rm -rf "$STAGING_DIR/$zip_root"
    cp -R "$PLUGINS_DIR/$src_dir" "$STAGING_DIR/$zip_root"
    find "$STAGING_DIR/$zip_root" -name ".DS_Store" -delete

    local out_zip="$DIST_DIR/$zip_name"
    rm -f "$out_zip"
    (
        cd "$STAGING_DIR"
        zip -rq "$out_zip" "$zip_root"
    )

    local first_entry
    first_entry="$(unzip -Z1 "$out_zip" | sed -n '1p')"
    if [[ "$first_entry" != "$zip_root/"* ]]; then
        echo "ERROR: Unexpected archive root in $out_zip: $first_entry" >&2
        exit 1
    fi
    echo "Built $out_zip (root: $zip_root/)"
}

build_zip "mod_airagassign" "airagassign" "airagassign.zip"
build_zip "mod_airagmaterial" "airagmaterial" "airagmaterial.zip"
build_zip "local_assign_ai_rag" "assign_ai_rag" "local_assign_ai_rag.zip"
build_zip "aiprovider_rag" "rag" "aiprovider_rag.zip"

echo "All Moodle plugin packages written to $DIST_DIR"
