# cli-anything-pdf2zh

> CLI harness for **PDFMathTranslate** — translate PDFs (with layout preserved) from scripts and AI agents.

## About the upstream software

The core translation engine is **PDFMathTranslate** (`pdf2zh`), an open-source
project by [Byaidu](https://github.com/Byaidu). This repo provides a CLI
harness wrapper around it.

| Resource | Link |
|----------|------|
| Original repo | <https://github.com/PDFMathTranslate/PDFMathTranslate> |
| Releases (EXE bundle) | <https://github.com/PDFMathTranslate/PDFMathTranslate/releases> |
| Docs | <https://pdf2zh.readthedocs.io/> |

### The `build/` directory

The `build/` directory (git-ignored) contains the **Windows EXE bundle**
downloaded from the upstream releases. It includes:

- `pdf2zh.exe` — standalone entry point (PyStand)
- `runtime/` — bundled Python interpreter
- `site-packages/` — all Python packages including `pdf2zh`

To obtain it, download a release from
[PDFMathTranslate/releases](https://github.com/PDFMathTranslate/PDFMathTranslate/releases)
and extract into `build/`.

---

## What this harness adds

- **One-shot translation** — `cli-anything-pdf2zh translate paper.pdf -o out/`
- **Interactive REPL** with `pdf / lang / use / translate / save` commands
- **JSON output** for agent consumption (`--json`)
- **23 translator services** listed and configured
- **Config management** for `~/.config/PDFMathTranslate/config.json`
- **SQLite cache inspection** for `~/.cache/pdf2zh/cache.v1.db`
- **MiniMax translator patch** — install / uninstall / status

---

## Quick start

```bash
# 1. Install the harness
cd agent-harness
pip install -e .

# 2. (Optional) Install MiniMax translator patch
cli-anything-pdf2zh patch install

# 3. Translate a PDF
cli-anything-pdf2zh translate paper.pdf -o out/ --service google
```

See [`agent-harness/cli_anything/pdf2zh/README.md`](agent-harness/cli_anything/pdf2zh/README.md)
for full documentation.

---

## License

MIT.
