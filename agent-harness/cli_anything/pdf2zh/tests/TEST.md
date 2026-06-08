# TEST Plan — cli-anything-pdf2zh

## 1. Test inventory (planned)

| File | Class | Count | Purpose |
|------|-------|-------|---------|
| `test_core.py` | `TestBackendExe`     | 4 | EXE resolution & arg builder |
| `test_core.py` | `TestTranslateOptions` | 5 | Session/Options dataclasses, project file round-trip |
| `test_core.py` | `TestConfig`         | 6 | Config file read/write, translator env upsert, masking |
| `test_core.py` | `TestCache`          | 4 | SQLite cache summary / list / clear (uses temp DB) |
| `test_core.py` | `TestInspect`        | 4 | PDF magic-byte + page count validation |
| `test_core.py` | `TestServices`       | 3 | Service catalog + bundle discovery |
| `test_core.py` | `TestPatch`          | 5 | Xiaomi MiMo patch install/uninstall idempotency |
| `test_core.py` | `TestReplSkin`       | 3 | ReplSkin prints without crashing |
| `test_core.py` | `TestTranslateIO`    | 2 | `run_translate` builds the right argv |
| `test_full_e2e.py` | `TestE2EGoogle`  | 2 | Translate a synthetic PDF with `--service google` (requires network) |
| `test_full_e2e.py` | `TestE2EMiMo` | 2 | Translate a synthetic PDF with `--service mimo` (uses stored API key, requires network) |
| `test_full_e2e.py` | `TestCLISubprocess` | 6 | Run the installed `cli-anything-pdf2zh` command via `subprocess.run` for `--help`, `info`, `services list`, `patch status`, `config show-translator`, `cache summary` |

**Planned total: ~46 tests.**

## 2. Unit test plan

### `TestBackendExe`
- `find_pdf2zh_exe` returns the canonical `C:\Program Files\pdf2zh\build\pdf2zh.exe` on this host
- `find_pdf2zh_exe` honours `PDF2ZH_EXE_PATH` env override
- `find_pdf2zh_exe` raises `RuntimeError` when given a missing explicit path
- `build_translate_args` produces the expected argv for a minimal call (no optional flags)

### `TestTranslateOptions`
- `TranslateOptions.to_dict()` is JSON-serializable
- `Session.to_dict()` / `from_dict()` round-trips
- `save_project` / `load_project` round-trips a Session to a JSON file
- `load_project` rejects an unknown `_format` marker
- `load_project` raises `FileNotFoundError` for missing files

### `TestConfig`
- `set_translator_key` upserts and round-trips
- `set_translator_env` replaces the env dict
- `delete_translator` removes a translator entry
- `get` falls back to env var when key not in file
- `all_entries` returns a dict
- masking in `config_show_translator` doesn't leak secret values to stdout

### `TestCache`
- `summary` works on a fresh (missing) cache
- `summary` returns top_engines when rows exist
- `clear` deletes by engine
- `list_entries` filters by engine

The cache tests use a temporary SQLite database to avoid touching the user's
real `~/.cache/pdf2zh/cache.v1.db`. We monkey-patch `cache_mod.CACHE_PATH`
per-test.

### `TestInspect`
- `inspect_pdf` returns `is_valid_pdf=True` for a known-good PDF
- `inspect_pdf` returns `is_valid_pdf=False` for a non-PDF file
- `inspect_pdf` returns page_count for a multi-page PDF
- `inspect_outputs` computes the right mono/dual paths

### `TestServices`
- `list_services` returns 23 entries
- `describe_service("google")` returns the right `kind="free"`
- `discover_from_bundle` finds MiMo after a patch install (live bundle check)

### `TestPatch`
- `is_installed` is False before install
- `install` is idempotent (running twice is a no-op)
- `uninstall` is idempotent (running twice is a no-op)
- `install` adds the class marker to `translator.py`
- `install` adds the import + registration lines to `pdf2zh.py`

These tests **temporarily install and uninstall the patch on the real
bundle** because we are not running under a fake filesystem. The test
restores state in a `finally` block.

### `TestReplSkin`
- `ReplSkin.print_banner()` runs without raising
- `ReplSkin.prompt()` returns a non-empty string
- `ReplSkin.table()` formats headers + rows

### `TestTranslateIO`
- `run_translate` builds argv with the right positional + flags
- `parse_babeldoc_output` extracts mono/dual paths from a known stdout

## 3. E2E test plan

### `TestE2EGoogle`
1. Generate a synthetic 1-page English PDF with `pymupdf` to a temp dir.
2. Invoke `run_translate([pdf], output=tmp/out, service="google", lang_in="en", lang_out="zh", ignore_cache=True, env_overrides=...)` with a 120s timeout.
3. Assert: exit_code == 0
4. Assert: `*-mono.pdf` and `*-dual.pdf` exist in tmp/out
5. Assert: each is at least 5 bytes and starts with `b"%PDF-"`
6. Assert: `dual_size > mono_size` (sanity)

**Skipped when:** `pymupdf` not importable, or the user disabled Google by
setting `PDF2ZH_SKIP_GOOGLE=1` (e.g. CI without network).

### `TestE2EMiMo`
1. Generate a 1-page English PDF.
2. Read the API key from `~/.config/PDFMathTranslate/config.json` (set via
   the `config set-key` command earlier) or from `ANTHROPIC_AUTH_TOKEN` env var.
3. Invoke `run_translate` with `service="mimo"`, threading through the
   stored envs as `env_overrides`.
4. Assert: exit_code == 0, outputs exist, sizes pass.

**Skipped when:** no `MIMO_API_KEY` / `ANTHROPIC_AUTH_TOKEN` configured OR `PDF2ZH_SKIP_MIMO=1`.

### `TestCLISubprocess`
- `_resolve_cli("cli-anything-pdf2zh")` works (installed or dev fallback)
- `cli-anything-pdf2zh --help` exits 0
- `cli-anything-pdf2zh --version` exits 0
- `cli-anything-pdf2zh --json services list` returns valid JSON
- `cli-anything-pdf2zh --json patch status` returns valid JSON
- `cli-anything-pdf2zh --json info <synthetic.pdf>` returns valid JSON
- `cli-anything-pdf2zh --json config show-translator mimo` works (masks
  the secret)

The subprocess tests use `CLI_ANYTHING_FORCE_INSTALLED=1` env to verify
the installed command works (falls back to `python -m` when not installed
in dev mode).

## 4. Realistic workflow scenarios

1. **Single-file English→Chinese with Google** — the everyday case
2. **Single-file English→Chinese with MiMo** — premium-quality case
3. **Multi-page PDF with --pages 1-3** — partial translation
4. **PDF/A compatibility mode** — `--compatible` flag
5. **Cache reuse** — re-translate, verify cache is hit (no `exit_code=1`)
6. **Project save/load** — save a session, restore it, re-translate

## 5. Coverage gaps

- We do **not** unit-test `babeldoc` translation (requires babeldoc runtime
  and a paid API)
- We do **not** test the GUI / Flask / Celery modes
- We do **not** test `--share` (Gradio share requires outbound tunnel)
- The `mcp` subcommand is tested only as a no-op in unit tests; real MCP
  testing would need an MCP client

---

## 6. Test results

Run on **2026-06-03** with Python 3.14.3, pytest 9.0.3 on Windows 11:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Program Files\pdf2zh\agent-harness
plugins: anyio-4.13.0
collecting ... collected 47 items

cli_anything/pdf2zh/tests/test_core.py::TestBackendExe::test_find_exe_returns_canonical_path PASSED [  2%]
cli_anything/pdf2zh/tests/test_core.py::TestBackendExe::test_find_exe_honours_env_override PASSED [  4%]
cli_anything/pdf2zh/tests/test_core.py::TestBackendExe::test_find_exe_raises_for_missing_explicit PASSED [  6%]
cli_anything/pdf2zh/tests/test_core.py::TestBackendExe::test_build_translate_args_minimal PASSED [  8%]
cli_anything/pdf2zh/tests/test_core.py::TestBackendExe::test_build_translate_args_rejects_empty_files PASSED [ 10%]
cli_anything/pdf2zh/tests/test_core.py::TestBackendExe::test_build_translate_args_rejects_missing_output PASSED [ 12%]
cli_anything/pdf2zh/tests/test_core.py::TestTranslateOptions::test_options_to_dict_is_jsonable PASSED [ 14%]
cli_anything/pdf2zh/tests/test_core.py::TestTranslateOptions::test_session_round_trip PASSED [ 17%]
cli_anything/pdf2zh/tests/test_core.py::TestTranslateOptions::test_project_save_load PASSED [ 19%]
cli_anything/pdf2zh/tests/test_core.py::TestTranslateOptions::test_project_load_rejects_unknown_format PASSED [ 21%]
cli_anything/pdf2zh/tests/test_core.py::TestTranslateOptions::test_project_load_missing_file PASSED [ 23%]
cli_anything/pdf2zh/tests/test_core.py::TestConfig::test_set_translator_key_upserts PASSED [ 25%]
cli_anything/pdf2zh/tests/test_core.py::TestConfig::test_set_translator_env_replaces PASSED [ 27%]
cli_anything/pdf2zh/tests/test_core.py::TestConfig::test_delete_translator PASSED [ 29%]
cli_anything/pdf2zh/tests/test_core.py::TestConfig::test_get_falls_back_to_env PASSED [ 31%]
cli_anything/pdf2zh/tests/test_core.py::TestConfig::test_all_entries_returns_dict PASSED [ 34%]
cli_anything/pdf2zh/tests/test_core.py::TestConfig::test_set_top_and_delete_top PASSED [ 36%]
cli_anything/pdf2zh/tests/test_core.py::TestCache::test_summary_on_existing PASSED [ 38%]
cli_anything/pdf2zh/tests/test_core.py::TestCache::test_summary_on_missing PASSED [ 40%]
cli_anything/pdf2zh/tests/test_core.py::TestCache::test_clear_by_engine PASSED [ 42%]
cli_anything/pdf2zh/tests/test_core.py::TestCache::test_clear_all PASSED [ 44%]
cli_anything/pdf2zh/tests/test_core.py::TestInspect::test_inspect_valid_pdf PASSED [ 46%]
cli_anything/pdf2zh/tests/test_core.py::TestInspect::test_inspect_non_pdf PASSED [ 48%]
cli_anything/pdf2zh/tests/test_core.py::TestInspect::test_inspect_missing_file PASSED [ 51%]
cli_anything/pdf2zh/tests/test_core.py::TestInspect::test_inspect_outputs PASSED [ 53%]
cli_anything/pdf2zh/tests/test_core.py::TestServices::test_list_services_has_mimo PASSED [ 55%]
cli_anything/pdf2zh/tests/test_core.py::TestServices::test_describe_mimo PASSED [ 57%]
cli_anything/pdf2zh/tests/test_core.py::TestServices::test_describe_unknown PASSED [ 59%]
cli_anything/pdf2zh/tests/test_core.py::TestPatch::test_status_returns_installed_field PASSED [ 61%]
cli_anything/pdf2zh/tests/test_core.py::TestPatch::test_install_then_uninstall_round_trip PASSED [ 63%]
cli_anything/pdf2zh/tests/test_core.py::TestPatch::test_uninstall_when_not_installed PASSED [ 65%]
cli_anything/pdf2zh/tests/test_core.py::TestReplSkin::test_banner_runs PASSED [ 68%]
cli_anything/pdf2zh/tests/test_core.py::TestReplSkin::test_prompt_non_empty PASSED [ 70%]
cli_anything/pdf2zh/tests/test_core.py::TestReplSkin::test_table_renders PASSED [ 72%]
cli_anything/pdf2zh/tests/test_core.py::TestTranslateIO::test_parse_babeldoc_output PASSED [ 74%]
cli_anything/pdf2zh/tests/test_core.py::TestTranslateIO::test_parse_babeldoc_output_handles_missing_block PASSED [ 76%]
cli_anything/pdf2zh/tests/test_core.py::TestMcpPassthrough::test_mcp_invokes_exe PASSED [ 78%]
cli_anything/pdf2zh/tests/test_full_e2e.py::TestSyntheticPdf::test_pymupdf_generates_valid_pdf PASSED [ 80%]
cli_anything/pdf2zh/tests/test_full_e2e.py::TestE2EGoogle::test_translate_english_to_chinese PASSED [ 82%]
cli_anything/pdf2zh/tests/test_full_e2e.py::TestE2EMiMo::test_translate_english_to_chinese PASSED [ 85%]
cli_anything/pdf2zh/tests/test_full_e2e.py::TestCLISubprocess::test_help PASSED [ 87%]
cli_anything/pdf2zh/tests/test_full_e2e.py::TestCLISubprocess::test_version PASSED [ 89%]
cli_anything/pdf2zh/tests/test_full_e2e.py::TestCLISubprocess::test_json_services_list PASSED [ 91%]
cli_anything/pdf2zh/tests/test_full_e2e.py::TestCLISubprocess::test_json_patch_status PASSED [ 93%]
cli_anything/pdf2zh/tests/test_full_e2e.py::TestCLISubprocess::test_json_info_on_synthetic_pdf PASSED [ 95%]
cli_anything/pdf2zh/tests/test_full_e2e.py::TestCLISubprocess::test_json_config_show_translator PASSED [ 97%]
cli_anything/pdf2zh/tests/test_full_e2e.py::TestCLISubprocess::test_json_cache_summary PASSED [100%]

============================= 47 passed in 22.50s =============================
```

### Summary

| Metric | Value |
|--------|-------|
| Total tests | 47 |
| Passed | **47** |
| Failed | 0 |
| Skipped | 0 |
| Pass rate | **100%** |
| Wall time | 22.5s (incl. one real Google + one real MiMo E2E translate) |

The MiMo E2E (`TestE2EMiMo::test_translate_english_to_chinese`) is the
most important test — it makes a real HTTPS call to
`https://token-plan-cn.xiaomimimo.com/v1/chat/completions` with the stored API key
and verifies both `*-mono.pdf` and `*-dual.pdf` are produced with valid
PDF magic bytes and that `dual > mono` in size.

### Test environment

* PDFMathTranslate EXE: `C:\Program Files\pdf2zh\build\pdf2zh.exe` v1.9.11
* MiMo patch: installed (idempotent re-install verified)
* MiMo API key: available via `ANTHROPIC_AUTH_TOKEN` env var or stored in `~/.config/PDFMathTranslate/config.json`
* pymupdf: used for synthetic PDF generation and page-count verification
* pdfminer.six: used as fallback page counter

### Notes

* `TestPatch::test_install_then_uninstall_round_trip` exercises the real
  bundle — it temporarily mutates the EXE's site-packages and restores
  from `.harness.bak` files in a `finally`-style teardown.
* The subprocess tests fall back to `python -m cli_anything.pdf2zh`
  when the `cli-anything-pdf2zh.exe` shim is not on `PATH`. The shim is
  installed at `C:\Users\59620\AppData\Local\Python\pythoncore-3.14-64\Scripts\`
  which is not on the default Windows PATH for this user.

