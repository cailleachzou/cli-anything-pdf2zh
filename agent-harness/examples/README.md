# Examples

End-to-end usage examples for `cli-anything-pdf2zh`.

## 1. `translate-one.sh` — single-file translation

```bash
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
```

## 2. `batch-translate.sh` — directory batch

```bash
#!/usr/bin/env bash
# Translate every PDF in a directory tree.
# Usage: ./batch-translate.sh ./pdfs/ ./out/

set -euo pipefail

SRC="${1:?usage: $0 <src-dir> <out-dir>}"
DST="${2:?usage: $0 <src-dir> <out-dir>}"
SERVICE="${SERVICE:-mimo}"

cli-anything-pdf2zh batch "$SRC" -o "$DST" \
    --service "$SERVICE" \
    --lang-in en --lang-out zh \
    --thread 4

echo "Done. Output: $DST"
```

## 3. `python_translate.py` — Python agent flow

```python
"""Translate a PDF via subprocess + parse the JSON result.

Useful when you want to drive the translation from Python without
depending on the Click CLI surface (e.g. in a Jupyter notebook).
"""
import json
import subprocess
import sys
from pathlib import Path

PDF = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("paper.pdf")
OUT = Path("./out")
OUT.mkdir(exist_ok=True)

result = subprocess.run(
    [
        "cli-anything-pdf2zh",
        "--json",
        "translate", str(PDF),
        "-o", str(OUT),
        "--service", "mimo",
        "--lang-in", "en", "--lang-out", "zh",
        "--ignore-cache",
    ],
    capture_output=True, text=True, check=False,
)

if result.returncode != 0:
    raise SystemExit(f"translate failed: {result.stderr}")

payload = json.loads(result.stdout)
print(f"mono: {payload['mono_pdf']}")
print(f"dual: {payload['dual_pdf']}")
print(f"duration: {payload['duration_s']:.2f}s")
```

## 4. `repl_workflow.txt` — REPL session

Drop into a REPL with `cli-anything-pdf2zh` and paste:

```text
services
use mimo
lang en zh
pdf paper.pdf
out ./out
translate
status
save my-workflow.json
exit
```

## 5. `install-patch.ps1` — first-time setup (PowerShell)

```powershell
# Install the Xiaomi MiMo translator patch into the bundled EXE.
# Run once per machine.

$ErrorActionPreference = "Stop"

Write-Host "Installing Xiaomi MiMo translator patch..."
cli-anything-pdf2zh patch install

Write-Host "Setting up API key (paste your key when prompted)..."
$key = Read-Host -Prompt "MIMO_API_KEY" -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($key))

cli-anything-pdf2zh config set-key mimo MIMO_API_KEY $plain
cli-anything-pdf2zh config set-key mimo MIMO_BASE_URL https://token-plan-cn.xiaomimimo.com/v1
cli-anything-pdf2zh config set-key mimo MIMO_MODEL mimo-v2.5-pro

Write-Host "Verifying..."
cli-anything-pdf2zh config show-translator mimo
cli-anything-pdf2zh patch status
```
