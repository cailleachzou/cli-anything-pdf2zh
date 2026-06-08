# cli-anything-pdf2zh

> CLI harness for **PDFMathTranslate** — translate PDFs from scripts and AI agents.
>
> Built per the [cli-anything HARNESS methodology](https://github.com/HKUDS/CLI-Anything).

`cli-anything-pdf2zh` wraps the PDFMathTranslate Windows EXE bundle
(`pdf2zh.exe`) as a stateful, JSON-friendly command-line interface. It
also ships a **Xiaomi MiMo translator patch** that injects a new translator
class into the bundled `translator.py`, so the EXE accepts
`--service mimo` and consumes `MIMO_*` env vars.

---

## What you get

* **One-shot translation** — `cli-anything-pdf2zh translate paper.pdf -o out/`
* **Interactive REPL** — `cli-anything-pdf2zh` (no args) enters a session
  with `pdf / lang / use / translate / save` commands
* **JSON output for agents** — every command supports `--json`
* **23 translator services** listed and described (`services list`)
* **Config management** for `~/.config/PDFMathTranslate/config.json` (the
  pdf2zh standard config file)
* **SQLite cache inspection** for `~/.cache/pdf2zh/cache.v1.db`
* **PDF inspection** via pymupdf / pdfminer
* **Xiaomi MiMo translator patch** — install / uninstall / status

---

## Installation

### 1. Install PDFMathTranslate

If you don't already have it:

* Download a release from
  [PDFMathTranslate/releases](https://github.com/PDFMathTranslate/PDFMathTranslate/releases).
* The installer places `pdf2zh.exe` at
  `C:\Program Files\pdf2zh\build\pdf2zh.exe` by default.

Verify the EXE is found:

```bash
cli-anything-pdf2zh services list
# or
cli-anything-pdf2zh --exe "C:\Program Files\pdf2zh\build\pdf2zh.exe" patch status --json
```

If the EXE lives somewhere else, set `PDF2ZH_EXE_PATH`:

```bash
export PDF2ZH_EXE_PATH="D:/tools/pdf2zh/build/pdf2zh.exe"
```

### 2. Install the harness

```bash
cd "C:/Program Files/pdf2zh/agent-harness"
pip install -e .
```

The `cli-anything-pdf2zh` command will be on your PATH.

### 3. (Optional) Install the Xiaomi MiMo translator patch

```bash
cli-anything-pdf2zh patch install
```

The patch edits two files inside the EXE's `build/site-packages/pdf2zh/`
directory and creates `.harness.bak` backups. It's idempotent — running
it twice is a no-op.

### 4. (Optional) Configure your translator API keys

```bash
# For Xiaomi MiMo (API key falls back to ANTHROPIC_AUTH_TOKEN env var)
cli-anything-pdf2zh config set-key mimo MIMO_API_KEY <key>
cli-anything-pdf2zh config set-key mimo MIMO_BASE_URL https://token-plan-cn.xiaomimimo.com/v1
cli-anything-pdf2zh config set-key mimo MIMO_MODEL mimo-v2.5-pro

# For OpenAI
cli-anything-pdf2zh config set-key openai OPENAI_API_KEY sk-...
```

Use `config show-translator <name>` to verify (secret values are masked).

---

## Usage

### One-shot translation

```bash
# English to Chinese with Google (no API key needed)
cli-anything-pdf2zh translate paper.pdf -o out/ --service google

# English to Japanese with MiMo
cli-anything-pdf2zh translate paper.pdf -o out/ --service mimo --lang-in en --lang-out ja

# Translate pages 1-3 only
cli-anything-pdf2zh translate book.pdf -o out/ --pages 1-3

# Batch translate a directory
cli-anything-pdf2zh batch ./pdfs/ -o ./out/
```

### Interactive REPL

```bash
$ cli-anything-pdf2zh
◆  cli-anything-pdf2zh  v0.1.0  (PDFMathTranslate harness)

  pdf paper.pdf
  ✓ current_pdf = paper.pdf
  out ./translated
  ✓ output_dir = ./translated
  use mimo
  ✓ service = mimo
  lang en zh
  ✓ lang = en -> zh
  translate
  ✓ mono: ./translated/paper-mono.pdf  dual: ./translated/paper-dual.pdf
  save my-translation.json
  ✓ saved my-translation.json
  exit
```

### JSON output (for agents)

```bash
$ cli-anything-pdf2zh --json services list
[
  {"name": "google", "kind": "free", "key": "no", "desc": "Google Translate (web endpoint)"},
  ...
  {"name": "mimo", "kind": "key", "key": "yes", "desc": "Xiaomi MiMo (added by harness patch)"}
]

$ cli-anything-pdf2zh --json translate paper.pdf -o out/ --service google
{
  "mono_pdf": "...\\paper-mono.pdf",
  "dual_pdf": "...\\paper-dual.pdf",
  "exit_code": 0,
  "duration_s": 12.4,
  "inputs": ["paper.pdf"],
  ...
}
```

### Project files

Save a session to a JSON file and replay later:

```bash
# Save
cli-anything-pdf2zh translate paper.pdf -o out/ --service mimo --lang-in en --lang-out zh
# (in REPL): save project.json

# Load
cli-anything-pdf2zh project open project.json
# (in REPL): open project.json
```

### Inspect & cache

```bash
# Inspect a PDF
cli-anything-pdf2zh info paper.pdf

# Inspect the SQLite translation cache
cli-anything-pdf2zh cache summary
cli-anything-pdf2zh cache list --engine mimo --limit 10
cli-anything-pdf2zh cache clear --engine mimo
```

---

## Architecture

The harness is a **PEP 420 namespace package** under `cli_anything/`:

```
agent-harness/
├── PDFMathTranslate.md       # software-specific SOP
├── setup.py
├── cli_anything/
│   └── pdf2zh/               # ← this package
│       ├── __init__.py
│       ├── __main__.py       # `python -m cli_anything.pdf2zh`
│       ├── pdf2zh_cli.py     # main CLI entry
│       ├── core/             # business logic
│       │   ├── translate.py
│       │   ├── services.py
│       │   ├── config.py
│       │   ├── cache.py
│       │   ├── inspect.py
│       │   └── patch.py
│       ├── utils/
│       │   ├── pdf2zh_backend.py   # subprocess wrapper around pdf2zh.exe
│       │   └── repl_skin.py
│       ├── patch/
│       │   └── __init__.py   # MiMoTranslator source string
│       ├── skills/SKILL.md   # auto-generated AI-agent skill file
│       └── tests/
│           ├── TEST.md
│           ├── test_core.py
│           └── test_full_e2e.py
├── examples/
└── skills/cli-anything-pdf2zh/
    └── SKILL.md              # canonical repo-root skill
```

The harness **does not reimplement** PDF translation. It calls the real
`pdf2zh.exe` via `subprocess.run` and surfaces results. See
`PDFMathTranslate.md` for the full SOP.

---

## Running tests

```bash
cd "C:/Program Files/pdf2zh/agent-harness"
pip install -e ".[test]"

# Unit tests only (no EXE, no network)
py -3 -m pytest cli_anything/pdf2zh/tests/test_core.py -v

# E2E tests (invokes the real EXE — requires network + API keys)
py -3 -m pytest cli_anything/pdf2zh/tests/test_full_e2e.py -v

# Force the installed CLI to be used (CI mode)
CLI_ANYTHING_FORCE_INSTALLED=1 py -3 -m pytest cli_anything/pdf2zh/tests/ -v -s

# Skip network-dependent tests
PDF2ZH_SKIP_GOOGLE=1 PDF2ZH_SKIP_MIMO=1 py -3 -m pytest -v
```

---

## Security & secrets

The harness reads / writes `~/.config/PDFMathTranslate/config.json` and
the `MIMO_API_KEY` (or any other translator key) you put there. Secret
values are masked in `config show-translator` output.

**Never commit `config.json` to git.** Add it to your global `.gitignore`.

---

## License

MIT.
