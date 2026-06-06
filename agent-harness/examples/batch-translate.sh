#!/usr/bin/env bash
# Translate every PDF in a directory tree.
# Usage: ./batch-translate.sh ./pdfs/ ./out/

set -euo pipefail

SRC="${1:?usage: $0 <src-dir> <out-dir>}"
DST="${2:?usage: $0 <src-dir> <out-dir>}"
SERVICE="${SERVICE:-minimax}"

cli-anything-pdf2zh batch "$SRC" -o "$DST" \
    --service "$SERVICE" \
    --lang-in en --lang-out zh \
    --thread 4

echo "Done. Output: $DST"
