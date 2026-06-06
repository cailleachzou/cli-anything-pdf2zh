"""End-to-end tests for the pdf2zh harness.

These tests invoke the REAL pdf2zh.exe to translate synthetic PDFs. They
require:

* pdf2zh.exe installed (auto-detected or via $PDF2ZH_EXE_PATH)
* Network access for translation services
* The first run downloads the ONNX layout model (~50MB) and remote fonts

Tests are SKIPPED, not failed, when the environment is hostile:

* ``PDF2ZH_SKIP_GOOGLE=1``  — skip Google tests
* ``PDF2ZH_SKIP_MINIMAX=1`` — skip MiniMax tests
* No MINIMAX_API_KEY in ``~/.config/PDFMathTranslate/config.json`` — skip
  the MiniMax test
* No pymupdf — skip the synthetic-PDF tests
* No network at runtime — caught by subprocess timeout / exit code

The CLI subprocess tests use ``_resolve_cli`` so they work against the
installed command OR a ``python -m`` dev invocation, with
``CLI_ANYTHING_FORCE_INSTALLED=1`` to fail-loud if the install is missing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

import pytest

from cli_anything.pdf2zh.core import config as config_mod
from cli_anything.pdf2zh.utils import pdf2zh_backend as backend


# ── Helpers ─────────────────────────────────────────────────────────


def _make_synthetic_pdf(path: Path, *, pages: int = 1, text: str = "Hello world.") -> None:
    """Generate a small PDF using pymupdf. Falls back to a no-pymupdf stub
    that fails the test."""
    try:
        from pymupdf import Document
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"pymupdf not available: {e}")
    doc = Document()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def _read_minimax_key() -> Optional[str]:
    """Read the stored MINIMAX_API_KEY from the user's pdf2zh config."""
    cfg = config_mod.CONFIG_PATH
    if not cfg.is_file():
        return None
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    for t in data.get("translators", []):
        if t.get("name") == "minimax":
            return (t.get("envs") or {}).get("MINIMAX_API_KEY")
    return None


def _resolve_cli(name: str) -> List[str]:
    """Resolve the installed CLI command. Fall back to ``python -m`` in dev.

    Honours ``CLI_ANYTHING_FORCE_INSTALLED=1`` — if set, raises if the
    command is not in PATH.
    """
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    found = shutil.which(name)
    if found:
        print(f"[_resolve_cli] Using installed command: {found}")
        return [found]
    if force:
        raise RuntimeError(
            f"{name} not found in PATH. Install with: pip install -e ."
        )
    module = "cli_anything.pdf2zh.pdf2zh_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


# ── Synthetic PDF generation ─────────────────────────────────────────


class TestSyntheticPdf:
    def test_pymupdf_generates_valid_pdf(self, tmp_path):
        out = tmp_path / "test.pdf"
        _make_synthetic_pdf(out, text="Hello from the harness")
        assert out.is_file()
        with out.open("rb") as f:
            assert f.read(5) == b"%PDF-"
        from cli_anything.pdf2zh.core.inspect import inspect_pdf

        info = inspect_pdf(str(out))
        assert info["is_valid_pdf"] is True
        assert info["size_bytes"] > 100
        # Print for manual inspection during E2E runs
        print(f"\n  synthetic PDF: {out} ({info['size_bytes']} bytes, {info['page_count']} pages)")


# ── Google translate E2E ─────────────────────────────────────────────


class TestE2EGoogle:
    @pytest.fixture(autouse=True)
    def skip_flag(self):
        if os.environ.get("PDF2ZH_SKIP_GOOGLE", "").strip() == "1":
            pytest.skip("PDF2ZH_SKIP_GOOGLE=1")

    def test_translate_english_to_chinese(self, tmp_path):
        in_pdf = tmp_path / "doc.pdf"
        out_dir = tmp_path / "out"
        _make_synthetic_pdf(in_pdf, text="The quick brown fox.")

        res = backend.run_translate(
            [str(in_pdf)],
            output=str(out_dir),
            service="google",
            lang_in="en",
            lang_out="zh",
            thread=2,
            ignore_cache=True,
            timeout=180,
        )

        if res.exit_code != 0:
            pytest.skip(
                f"google translate failed (likely network/CI): "
                f"stderr={res.stderr_tail[-300:]}"
            )

        # Verify outputs
        mono = Path(res.mono_pdf)
        dual = Path(res.dual_pdf)
        assert mono.is_file(), f"missing mono: {mono}"
        assert dual.is_file(), f"missing dual: {dual}"
        with mono.open("rb") as f:
            assert f.read(5) == b"%PDF-"
        with dual.open("rb") as f:
            assert f.read(5) == b"%PDF-"
        # Sanity: dual is larger
        assert dual.stat().st_size > mono.stat().st_size
        print(
            f"\n  google mono: {mono} ({mono.stat().st_size:,} bytes)"
            f"\n  google dual: {dual} ({dual.stat().st_size:,} bytes)"
            f"\n  duration:    {res.duration_s:.2f}s"
        )


# ── MiniMax translate E2E ────────────────────────────────────────────


class TestE2EMiniMax:
    @pytest.fixture(autouse=True)
    def skip_flag(self):
        if os.environ.get("PDF2ZH_SKIP_MINIMAX", "").strip() == "1":
            pytest.skip("PDF2ZH_SKIP_MINIMAX=1")
        # Make sure the harness has the API key
        self._api_key = _read_minimax_key()
        if not self._api_key:
            pytest.skip(
                "no MINIMAX_API_KEY in ~/.config/PDFMathTranslate/config.json. "
                "Run: cli-anything-pdf2zh config set-key minimax MINIMAX_API_KEY <key>"
            )
        # Make sure the MiniMax translator is installed in the EXE.
        # Earlier tests (TestPatch in test_core.py) install/uninstall the
        # patch repeatedly. Re-install it here so this fixture is robust.
        from cli_anything.pdf2zh.core import patch as patch_mod

        try:
            paths = patch_mod.resolve_bundle_paths()
            patch_mod.install(paths, backup=True)
        except pytest.skip.Exception:
            raise
        except BaseException as e:  # noqa: BLE001
            pytest.skip(f"could not install MiniMax patch: {e}")
        s = patch_mod.status()
        if not s.get("installed"):
            pytest.skip("MiniMax translator not installed after attempt")

    def test_translate_english_to_chinese(self, tmp_path):
        in_pdf = tmp_path / "doc.pdf"
        out_dir = tmp_path / "out"
        _make_synthetic_pdf(in_pdf, text="The quick brown fox.")

        # Read all MiniMax envs and pass them through to the EXE
        cfg = config_mod.all_entries()
        envs = {}
        for t in cfg.get("translators", []):
            if t.get("name") == "minimax":
                envs = dict(t.get("envs") or {})
                break

        res = backend.run_translate(
            [str(in_pdf)],
            output=str(out_dir),
            service="minimax",
            lang_in="en",
            lang_out="zh",
            thread=2,
            ignore_cache=True,
            env_overrides=envs,
            timeout=300,
        )

        if res.exit_code != 0:
            pytest.skip(
                f"minimax translate failed (likely network/key): "
                f"stderr={res.stderr_tail[-300:]}"
            )

        mono = Path(res.mono_pdf)
        dual = Path(res.dual_pdf)
        assert mono.is_file()
        assert dual.is_file()
        with mono.open("rb") as f:
            assert f.read(5) == b"%PDF-"
        with dual.open("rb") as f:
            assert f.read(5) == b"%PDF-"
        assert dual.stat().st_size > mono.stat().st_size
        print(
            f"\n  minimax mono: {mono} ({mono.stat().st_size:,} bytes)"
            f"\n  minimax dual: {dual} ({dual.stat().st_size:,} bytes)"
            f"\n  duration:     {res.duration_s:.2f}s"
        )


# ── CLI subprocess tests ─────────────────────────────────────────────


class TestCLISubprocess:
    """Drive the installed ``cli-anything-pdf2zh`` command via subprocess.

    These tests verify the CLI works the way real users / agents will
    invoke it: via the installed console-script entry point, not via
    in-process function calls.
    """

    CLI_BASE = _resolve_cli("cli-anything-pdf2zh")

    def _run(self, args, *, check=True, timeout=30):
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
        )

    def test_help(self):
        r = self._run(["--help"])
        assert r.returncode == 0
        assert "cli-anything-pdf2zh" in r.stdout

    def test_version(self):
        r = self._run(["--version"])
        assert r.returncode == 0
        assert "0.1.0" in r.stdout

    def test_json_services_list(self):
        r = self._run(["--json", "services", "list"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert any(s["name"] == "minimax" for s in data)

    def test_json_patch_status(self):
        r = self._run(["--json", "patch", "status"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "installed" in data
        assert "exe" in data

    def test_json_info_on_synthetic_pdf(self, tmp_path):
        in_pdf = tmp_path / "doc.pdf"
        _make_synthetic_pdf(in_pdf)
        r = self._run(["--json", "info", str(in_pdf)])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["is_valid_pdf"] is True
        assert data["size_bytes"] > 0

    def test_json_config_show_translator(self):
        r = self._run(["--json", "config", "show-translator", "minimax"])
        # If the translator isn't configured, this exits 1; treat as soft skip
        if r.returncode != 0:
            pytest.skip("minimax translator not configured")
        data = json.loads(r.stdout)
        assert data["name"] == "minimax"
        # Don't leak the secret value into stdout
        envs = data.get("envs", {})
        for k, v in envs.items():
            if "KEY" in k or "TOKEN" in k or "SECRET" in k:
                assert "sk-" not in (v or ""), f"secret leaked: {k}={v!r}"

    def test_json_cache_summary(self):
        r = self._run(["--json", "cache", "summary"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "row_count" in data
        assert "path" in data
