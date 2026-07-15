#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
ADDONS=(
    repository.oste
    plugin.video.tubelink
    plugin.video.onepace
    plugin.audio.mp3streams-remastered
)

echo "Building Oste Repository..."
echo "Add-ons: ${ADDONS[*]}"
echo ""

python3 "$REPO_DIR/create_repository.py" \
    --datadir="$REPO_DIR/zips" \
    "${ADDONS[@]}"

echo ""
echo "Build complete. Generated files in zips/"
echo "  addons.xml      - Repository catalog"
echo "  addons.xml.md5  - Catalog checksum"
