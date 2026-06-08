#!/usr/bin/env bash
# Translate a single PDF using the Xiaomi MiMo service.
# Usage: ./translate-one.sh path/to/paper.pdf

set -euo pipefail

PDF="${1:?usage: $0 <pdf>}"
OUT_DIR="./out/$(basename "${PDF%.*}")"
mkdir -p "$OUT_DIR"

cli-anything-pdf2zh translate "$PDF" -o "$OUT_DIR" \
    --service mimo \
    --lang-in en --lang-out zh \
    --ignore-cache

echo "Done. mono: $OUT_DIR/$(basename "${PDF%.*}")-mono.pdf"
echo "      dual: $OUT_DIR/$(basename "${PDF%.*}")-dual.pdf"
