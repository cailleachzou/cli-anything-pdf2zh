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
        "translate",
        str(PDF),
        "-o",
        str(OUT),
        "--service",
        "minimax",
        "--lang-in",
        "en",
        "--lang-out",
        "zh",
        "--ignore-cache",
    ],
    capture_output=True,
    text=True,
    check=False,
)

if result.returncode != 0:
    raise SystemExit(f"translate failed: {result.stderr}")

payload = json.loads(result.stdout)
print(f"mono: {payload['mono_pdf']}")
print(f"dual: {payload['dual_pdf']}")
print(f"duration: {payload['duration_s']:.2f}s")
