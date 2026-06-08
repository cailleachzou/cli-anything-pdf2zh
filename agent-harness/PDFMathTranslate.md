# PDFMathTranslate — Agent-Harness SOP

> Software-specific Standard Operating Procedure for building a CLI harness
> around the PDFMathTranslate Windows EXE bundle located at
> `C:\Program Files\pdf2zh\build\pdf2zh.exe`.

---

## 1. What this software does

PDFMathTranslate (`pdf2zh`) is a Python library + GUI + CLI that **translates
PDF files** while preserving the original layout, math formulas, figures and
tables. The deliverable for a single input is two PDFs:

| Output | Description |
|--------|-------------|
| `<name>-mono.pdf` | Monolingual — translated text only, original layout |
| `<name>-dual.pdf`  | Bilingual — original + translated side by side |

Upstream version: **1.9.11** (June 2025 lineage).

---

## 2. Architecture map

The user installed PDFMathTranslate as a **PyStand-style Windows bundle**:

```
C:\Program Files\pdf2zh\
├── __init__.py              # Re-exports translate, translate_stream
├── pdf2zh.py                # argparse CLI entry point
├── high_level.py            # translate() / translate_stream() APIs
├── converter.py             # PDF → translated PDF (pdfminer + pymupdf)
├── translator.py            # 20+ translator classes (Google, OpenAI, ...)
├── doclayout.py             # ONNX layout detection
├── cache.py                 # SQLite translation cache
├── config.py                # ~/.config/PDFMathTranslate/config.json
├── mcp_server.py            # FastMCP server (translate_pdf tool)
├── gui.py                   # Gradio GUI
├── backend.py               # Flask / Celery workers
└── build/
    ├── pdf2zh.exe           # Standalone entry point (PyStand)
    ├── _pystand_static.int  # PyStand bootstrap
    ├── runtime/             # Bundled Python interpreter (.pyd / .dll)
    └── site-packages/       # ALL Python packages including pdf2zh/
        ├── pdf2zh/          # ← the actual code the EXE runs
        ├── babeldoc/        # experimental alternative backend
        ├── openai/, ...     # third-party deps
```

**Critical insight for the harness:** the EXE at `build/pdf2zh.exe` resolves
`pdf2zh.*` modules from `build/site-packages/`. **Editing files in
`build/site-packages/pdf2zh/` changes the EXE's runtime behavior.** This is how
we add a custom translator (Xiaomi MiMo) without rebuilding the bundle.

---

## 3. Backend engine (the "real software")

The backend is the `pdf2zh` Python package invoked via two surfaces:

| Surface | Entry point | Usage |
|---------|-------------|-------|
| CLI EXE | `pdf2zh.exe --files foo.pdf --service openai --lang-in en --lang-out zh --output out/` | One-shot translation, scriptable |
| Python API | `from pdf2zh.high_level import translate` | Programmatic; needs pip install |
| MCP | `pdf2zh.exe --mcp` (stdio) or `--mcp --sse` | Agent-native tool surface |
| Gradio GUI | `pdf2zh.exe --interactive` | Browser UI |

**Harness strategy: CLI EXE black-box mode.** The harness shells out to
`pdf2zh.exe` and parses stdout / exit code. We do not import `pdf2zh` as a
Python package, so no `pip install pdf2zh` is required — only `click` for the
Click-based CLI itself.

**Why black-box:**
- The user's environment has the EXE installed but no Python package
- The EXE has a known, documented CLI surface
- We don't need internal Python APIs (cache, config) at runtime — we can read
  the SQLite cache and JSON config directly as files

---

## 4. Translation services (the 20+ translators)

`build/site-packages/pdf2zh/translator.py` defines 20+ subclasses of
`BaseTranslator`. Each translator has:

```python
class OpenAITranslator(BaseTranslator):
    name = "openai"          # service id used on CLI
    envs = {                 # required env vars / defaults
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "OPENAI_API_KEY": None,
        "OPENAI_MODEL": "gpt-4o-mini",
    }
    CustomPrompt = True      # whether the engine accepts prompt templates
    def do_translate(self, text) -> str: ...
```

List of services (from `pdf2zh.py:yadt_main`):

| Service | Engine type | Requires API key |
|---------|-------------|------------------|
| `google` | Google Translate web | No (free tier) |
| `bing` | Bing | Yes |
| `deepl` | DeepL | Yes |
| `deeplx` | DeepLX (self-hosted) | Optional |
| `ollama` | Ollama local | No (local) |
| `xinference` | Xinference | Optional |
| `azure-openai` | Azure OpenAI | Yes |
| `openai` | OpenAI | Yes |
| `zhipu` | Zhipu GLM | Yes |
| `modelscope` | ModelScope | Yes |
| `silicon` | SiliconFlow | Yes |
| `gemini` | Gemini (OpenAI-compat) | Yes |
| `azure` | Azure Translator | Yes |
| `tencent` | Tencent TMT | Yes |
| `dify` | Dify | Yes |
| `anythingllm` | AnythingLLM | Yes |
| `argos` | Argos | No |
| `grok` | Grok | Yes |
| `groq` | Groq | Yes |
| `deepseek` | Deepseek | Yes |
| `openailiked` | OpenAI-compatible | Yes |
| `qwenmt` | QwenMT (DashScope) | Yes |
| **`mimo`** *(added by harness patch)* | **Xiaomi MiMo (OpenAI-compat)** | **Yes** |

---

## 5. The Xiaomi MiMo translator (added by harness)

Xiaomi MiMo is an OpenAI-compatible chat-completions API. We add a new
`MiMoTranslator` class to the bundled `translator.py` that mirrors
`OpenAITranslator` with MiMo's specific defaults:

```python
class MiMoTranslator(OpenAITranslator):
    name = "mimo"
    envs = {
        "MIMO_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
        "MIMO_API_KEY":  None,
        "MIMO_MODEL":    "mimo-v2.5-pro",
    }
    CustomPrompt = True
```

The API key falls back to `ANTHROPIC_AUTH_TOKEN` env var if `MIMO_API_KEY` is not set.

The harness ships a `patch/install_patch.py` that:
1. Locates `build/site-packages/pdf2zh/translator.py`
2. Appends `MiMoTranslator` if not already present (idempotent)
3. Locates `build/site-packages/pdf2zh/pdf2zh.py` and registers
   `MiMoTranslator` in the `yadt_main` translator list (idempotent)

The patch is reversible (`patch uninstall` removes the class and unregisters it).

---

## 6. Data model

| Asset | Path | Format |
|-------|------|--------|
| Translation cache | `~/.cache/pdf2zh/cache.v1.db` | SQLite (peewee) |
| Translator config | `~/.config/PDFMathTranslate/config.json` | JSON |
| Input | `*.pdf` (user-supplied) | PDF |
| Output | `*-mono.pdf` + `*-dual.pdf` | PDF |
| ONNX model | cached at `doclayout.py` startup | `.onnx` |
| Fonts | remote download (`download_remote_fonts`) | `.ttf` |

The harness reads the cache and config directly (they're standard formats) and
treats the output PDFs as opaque blobs — the EXE writes them, the harness only
inspects them.

---

## 7. CLI command groups (designed)

| Group | Purpose |
|-------|---------|
| `info`     | Inspect a PDF (page count, size, lang) without translating |
| `translate`| Run the EXE to translate a PDF (or batch via `--dir`) |
| `services` | List available translators; show resolved env config |
| `config`   | Read/write/delete the `PDFMathTranslate/config.json` keys |
| `inspect`  | Inspect output `*-mono.pdf` / `*-dual.pdf` files |
| `cache`    | Query / clear the SQLite translation cache |
| `patch`    | Install / uninstall the Xiaomi MiMo translator into the EXE |
| `mcp`      | Launch the EXE's MCP server (pass-through) |
| `repl`     | Default interactive mode |

Each command supports `--json` for agent consumption.

---

## 8. State model

The REPL maintains a tiny in-memory state object:

```python
{
  "project": None,        # optional: a project file path
  "input_pdf": None,      # currently selected input PDF
  "output_dir": None,     # default output dir
  "service": "google",    # default translator
  "lang_in": "en",
  "lang_out": "zh",
  "thread": 4,
  "babeldoc": False,
  "modified": False,      # dirty flag for REPL prompt
}
```

State is session-only (not persisted). For long-lived workflows the user can
write a JSON project file with `project new -o project.json` and reload it
with `project open`.

---

## 9. Output verification

Every `translate` invocation produces two PDFs. The harness verifies:

1. **Both files exist** at the expected paths
2. **Magic bytes** = `b"%PDF-"` (1-4 byte)
3. **Size > 0** (not a 0-byte error stub)
4. **Page count > 0** (parse with `pymupdf` to confirm)
5. **Mono and dual differ in size** (proves translation actually ran — dual is
   always larger than mono because it embeds both languages)

These checks live in `core/inspect.py` and are run by the E2E tests against a
synthetic English PDF.

---

## 10. Known limitations

- **Google free tier** is unreliable (rate-limited, IP-banned occasionally).
  E2E tests use `--ignore-cache` + `google` for the smoke test, and skip
  Google-dependent tests when network is unavailable.
- **Babeldoc backend** requires a separate install; the harness exposes
  `--babeldoc` as a passthrough flag but does not unit-test the babeldoc path.
- **ONNX model** is ~50MB and downloaded on first run. E2E tests assume it's
  already cached at `~/.cache/pdf2zh/` or download it once.
- **Custom fonts** (Source Han Serif, GoNoto) are downloaded on demand from
  GitHub. If the test machine is offline, `--lang-out` for CJK will fail.
