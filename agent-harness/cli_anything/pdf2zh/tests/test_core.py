"""Unit tests for the pdf2zh harness.

Pure synthetic data — no network, no real EXE translation calls. The
real EXE is exercised in ``test_full_e2e.py``.

Each test class groups tests by module:

* ``TestBackendExe``        — utils/pdf2zh_backend.py
* ``TestTranslateOptions``  — core/translate.py dataclasses & project file
* ``TestConfig``            — core/config.py
* ``TestCache``             — core/cache.py
* ``TestInspect``           — core/inspect.py
* ``TestServices``          — core/services.py
* ``TestPatch``             — core/patch.py (the Xiaomi MiMo patch)
* ``TestReplSkin``          — utils/repl_skin.py
* ``TestTranslateIO``       — utils/pdf2zh_backend.run_translate argv builder
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from cli_anything.pdf2zh.core import cache as cache_mod
from cli_anything.pdf2zh.core import config as config_mod
from cli_anything.pdf2zh.core import inspect as inspect_mod
from cli_anything.pdf2zh.core import patch as patch_mod
from cli_anything.pdf2zh.core import services as services_mod
from cli_anything.pdf2zh.core.translate import (
    Session,
    TranslateOptions,
    load_project,
    save_project,
    translate_files,
)
from cli_anything.pdf2zh.patch import (
    MIMO_CLASS_MARKER,
    MIMO_TRANSLATOR_SOURCE,
)
from cli_anything.pdf2zh.utils import pdf2zh_backend as backend
from cli_anything.pdf2zh.utils.repl_skin import ReplSkin


# ── TestBackendExe ─────────────────────────────────────────────────────


class TestBackendExe:
    def test_find_exe_returns_canonical_path(self):
        # On this host, the EXE is in C:\Program Files\pdf2zh\build\pdf2zh.exe
        exe = backend.find_pdf2zh_exe()
        assert exe.endswith("pdf2zh.exe")
        assert Path(exe).is_file()

    def test_find_exe_honours_env_override(self, tmp_path):
        # Create a fake EXE in tmp and point the env at it
        fake = tmp_path / "pdf2zh.exe"
        fake.write_bytes(b"")
        with mock.patch.dict(os.environ, {"PDF2ZH_EXE_PATH": str(fake)}):
            assert backend.find_pdf2zh_exe() == str(fake)

    def test_find_exe_raises_for_missing_explicit(self, tmp_path):
        with pytest.raises(RuntimeError):
            backend.find_pdf2zh_exe(str(tmp_path / "does-not-exist.exe"))

    def test_build_translate_args_minimal(self, tmp_path):
        pdf = tmp_path / "in.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        args = backend.build_translate_args(
            [str(pdf)],
            output=str(tmp_path / "out"),
            service="google",
            lang_in="en",
            lang_out="zh",
        )
        # Positional file comes first
        assert args[0] == str(pdf)
        assert "--service" in args
        assert "google" in args
        assert "--output" in args
        assert "--lang-in" in args
        assert "en" in args
        assert "--lang-out" in args
        assert "zh" in args

    def test_build_translate_args_rejects_empty_files(self, tmp_path):
        with pytest.raises(ValueError):
            backend.build_translate_args([], output=str(tmp_path / "out"))

    def test_build_translate_args_rejects_missing_output(self, tmp_path):
        with pytest.raises(ValueError):
            backend.build_translate_args(
                [str(tmp_path / "x.pdf")], output=""
            )


# ── TestTranslateOptions ──────────────────────────────────────────────


class TestTranslateOptions:
    def test_options_to_dict_is_jsonable(self):
        opts = TranslateOptions(service="openai", lang_in="en", lang_out="ja")
        json.dumps(opts.to_dict())  # must not raise

    def test_session_round_trip(self):
        s = Session(
            current_pdf="C:/tmp/a.pdf",
            options=TranslateOptions(service="mimo", lang_out="zh"),
        )
        data = s.to_dict()
        s2 = Session.from_dict(data)
        assert s2.current_pdf == s.current_pdf
        assert s2.options.service == "mimo"
        assert s2.options.lang_out == "zh"
        assert s2.modified is False

    def test_project_save_load(self, tmp_path):
        proj = tmp_path / "p.json"
        s = Session(current_pdf="C:/x.pdf", options=TranslateOptions(service="bing"))
        s.modified = True
        save_project(str(proj), s)
        s2 = load_project(str(proj))
        assert s2.current_pdf == "C:/x.pdf"
        assert s2.options.service == "bing"
        # save_project should clear the dirty flag
        assert s.modified is False

    def test_project_load_rejects_unknown_format(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"_format": "wrong", "session": {}}))
        with pytest.raises(ValueError):
            load_project(str(p))

    def test_project_load_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_project(str(tmp_path / "nope.json"))


# ── TestFallback ──────────────────────────────────────────────────────


def _fake_result(
    *, service: str, exit_code: int, stderr_tail: str = ""
) -> backend.TranslateResult:
    """Build a TranslateResult with just the fields the fallback logic reads."""
    return backend.TranslateResult(
        mono_pdf=None,
        dual_pdf=None,
        output_dir="",
        service=service,
        lang_in="en",
        lang_out="zh",
        thread=4,
        babeldoc=False,
        exit_code=exit_code,
        duration_s=0.1,
        stdout_tail="",
        stderr_tail=stderr_tail,
    )


class TestFallback:
    """Auto-fallback from mimo → google when the default service fails."""

    def test_fallback_when_default_fails(self, tmp_path, monkeypatch):
        pdf = tmp_path / "in.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        out = tmp_path / "out"
        calls: list[str] = []

        def fake_run(files, *, service, **_kwargs):
            calls.append(service)
            if service == "mimo":
                return _fake_result(
                    service="mimo",
                    exit_code=1,
                    stderr_tail="MIMO_API_KEY missing",
                )
            return _fake_result(
                service="google", exit_code=0,
            )

        monkeypatch.setattr(backend, "run_translate", fake_run)

        opts = TranslateOptions()  # default: service=mimo
        result = translate_files([str(pdf)], output_dir=str(out), options=opts)

        # Two attempts, in order
        assert calls == ["mimo", "google"]
        # Result is the successful fallback
        assert result["fallback_used"] is True
        assert result["fallback_from"] == "mimo"
        assert result["fallback_to"] == "google"
        assert "MIMO_API_KEY" in result["fallback_reason"]
        assert result["exit_code"] == 0

    def test_no_fallback_when_explicit_service_fails(self, tmp_path, monkeypatch):
        pdf = tmp_path / "in.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        out = tmp_path / "out"
        calls: list[str] = []

        def fake_run(files, *, service, **_kwargs):
            calls.append(service)
            return _fake_result(
                service=service,
                exit_code=1,
                stderr_tail=f"{service} down",
            )

        monkeypatch.setattr(backend, "run_translate", fake_run)

        opts = TranslateOptions(service="openai")
        result = translate_files([str(pdf)], output_dir=str(out), options=opts)

        # User picked openai — respect that, no swap
        assert calls == ["openai"]
        assert result.get("fallback_used", False) is False
        assert result["exit_code"] == 1

    def test_no_fallback_when_default_succeeds(self, tmp_path, monkeypatch):
        pdf = tmp_path / "in.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        out = tmp_path / "out"
        calls: list[str] = []

        def fake_run(files, *, service, **_kwargs):
            calls.append(service)
            return _fake_result(service=service, exit_code=0)

        monkeypatch.setattr(backend, "run_translate", fake_run)

        opts = TranslateOptions()  # default
        result = translate_files([str(pdf)], output_dir=str(out), options=opts)

        # Happy path — single attempt
        assert calls == ["mimo"]
        assert result.get("fallback_used", False) is False
        assert result["exit_code"] == 0

    def test_fallback_google_fails_returns_failure(self, tmp_path, monkeypatch):
        """If both mimo and google fail, return the google failure."""
        pdf = tmp_path / "in.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        out = tmp_path / "out"
        calls: list[str] = []

        def fake_run(files, *, service, **_kwargs):
            calls.append(service)
            return _fake_result(
                service=service,
                exit_code=1,
                stderr_tail=f"{service} unavailable",
            )

        monkeypatch.setattr(backend, "run_translate", fake_run)

        opts = TranslateOptions()
        result = translate_files([str(pdf)], output_dir=str(out), options=opts)

        # Both attempted
        assert calls == ["mimo", "google"]
        # Fallback ran but the second attempt also failed — return that
        assert result["fallback_used"] is True
        assert result["fallback_to"] == "google"
        assert result["exit_code"] == 1
        # fallback_reason captures WHY we fell back (the first attempt's error)
        assert "mimo" in result["fallback_reason"]


# ── TestConfig ────────────────────────────────────────────────────────


class TestConfig:
    @pytest.fixture
    def isolated_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "PDFMathTranslate" / "config.json"
        monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg)
        return cfg

    def test_set_translator_key_upserts(self, isolated_config):
        config_mod.set_translator_key("mimo", "MIMO_API_KEY", "sk-test")
        config_mod.set_translator_key("mimo", "MIMO_BASE_URL", "https://x")
        t = config_mod.get_translator("mimo")
        assert t is not None
        assert t["envs"]["MIMO_API_KEY"] == "sk-test"
        assert t["envs"]["MIMO_BASE_URL"] == "https://x"

    def test_set_translator_env_replaces(self, isolated_config):
        config_mod.set_translator_env("openai", {"OPENAI_API_KEY": "k1"})
        config_mod.set_translator_env("openai", {"OPENAI_API_KEY": "k2", "OPENAI_MODEL": "gpt-4o"})
        t = config_mod.get_translator("openai")
        assert t["envs"] == {"OPENAI_API_KEY": "k2", "OPENAI_MODEL": "gpt-4o"}

    def test_delete_translator(self, isolated_config):
        config_mod.set_translator_key("bing", "BING_KEY", "k")
        assert config_mod.delete_translator("bing") is True
        assert config_mod.get_translator("bing") is None
        assert config_mod.delete_translator("bing") is False

    def test_get_falls_back_to_env(self, isolated_config, monkeypatch):
        monkeypatch.setenv("PDF2ZH_TEST_KEY", "from_env")
        assert config_mod.get("PDF2ZH_TEST_KEY") == "from_env"

    def test_all_entries_returns_dict(self, isolated_config):
        config_mod.set_translator_key("deepl", "DEEPL_API_KEY", "k")
        d = config_mod.all_entries()
        assert "translators" in d

    def test_set_top_and_delete_top(self, isolated_config):
        config_mod.set_top("NOTO_FONT_PATH", "/some/path")
        assert config_mod.get("NOTO_FONT_PATH") == "/some/path"
        assert config_mod.delete_top("NOTO_FONT_PATH") is True
        assert config_mod.get("NOTO_FONT_PATH") is None


# ── TestCache ─────────────────────────────────────────────────────────


class TestCache:
    @pytest.fixture
    def temp_cache(self, tmp_path, monkeypatch):
        db = tmp_path / "cache.v1.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            """
            CREATE TABLE _translation_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                translate_engine VARCHAR(20),
                translate_engine_params TEXT,
                original_text TEXT,
                translation TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO _translation_cache (translate_engine, translate_engine_params, original_text, translation) VALUES (?, ?, ?, ?)",
            [
                ("google", "{}", "Hello", "你好"),
                ("google", "{}", "World", "世界"),
                ("mimo", "{}", "Foo", "酒吧"),
            ],
        )
        conn.commit()
        conn.close()
        monkeypatch.setattr(cache_mod, "CACHE_PATH", db)
        return db

    def test_summary_on_existing(self, temp_cache):
        s = cache_mod.summary()
        assert s["exists"] is True
        assert s["row_count"] == 3
        engines = {e["engine"] for e in s["top_engines"]}
        assert "google" in engines
        assert "mimo" in engines

    def test_summary_on_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache_mod, "CACHE_PATH", tmp_path / "absent.db")
        s = cache_mod.summary()
        assert s["exists"] is False
        assert s["row_count"] == 0

    def test_clear_by_engine(self, temp_cache):
        res = cache_mod.clear(engine="google")
        assert res["deleted"] == 2
        # mimo rows survive
        assert len(cache_mod.list_entries(engine="mimo")) == 1

    def test_clear_all(self, temp_cache):
        res = cache_mod.clear()
        assert res["deleted"] == 3


# ── TestInspect ──────────────────────────────────────────────────────


class TestInspect:
    def test_inspect_valid_pdf(self, tmp_path):
        from pymupdf import Document

        p = tmp_path / "in.pdf"
        doc = Document()
        doc.new_page(width=595, height=842)  # A4
        doc.save(str(p))
        doc.close()
        info = inspect_mod.inspect_pdf(str(p))
        assert info["is_valid_pdf"] is True
        assert info["size_bytes"] > 0
        # page count may be 1 or None depending on pymupdf version
        assert info["page_count"] in (1, None)

    def test_inspect_non_pdf(self, tmp_path):
        p = tmp_path / "not-a-pdf.txt"
        p.write_text("hello")
        info = inspect_mod.inspect_pdf(str(p))
        assert info["is_valid_pdf"] is False

    def test_inspect_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            inspect_mod.inspect_pdf(str(tmp_path / "missing.pdf"))

    def test_inspect_outputs(self, tmp_path):
        # Create fake output PDFs (just %PDF- header + padding)
        for kind in ("mono", "dual"):
            p = tmp_path / f"doc-{kind}.pdf"
            p.write_bytes(b"%PDF-1.4\n" + b"x" * (5000 if kind == "dual" else 2000))
        in_pdf = tmp_path / "doc.pdf"
        in_pdf.write_bytes(b"%PDF-1.4\n")
        result = inspect_mod.inspect_outputs(str(in_pdf), str(tmp_path))
        assert "mono" in result["files"]
        assert "dual" in result["files"]
        # dual should be larger than mono
        mono_size = result["files"]["mono"]["size_bytes"]
        dual_size = result["files"]["dual"]["size_bytes"]
        assert dual_size > mono_size
        assert result["verdict"] == "ok"


# ── TestServices ──────────────────────────────────────────────────────


class TestServices:
    def test_list_services_has_mimo(self):
        catalog = services_mod.list_services()
        names = [s["name"] for s in catalog]
        assert "mimo" in names
        assert "google" in names
        assert "openai" in names

    def test_describe_mimo(self):
        svc = services_mod.describe_service("mimo")
        assert svc is not None
        assert svc["kind"] == "key"
        assert svc["key"] == "yes"

    def test_describe_unknown(self):
        assert services_mod.describe_service("nope") is None


# ── TestPatch ─────────────────────────────────────────────────────────


class TestPatch:
    @pytest.fixture
    def paths(self):
        # Resolve real bundle paths. We *will* mutate the bundle, but
        # install() is idempotent and uninstall() restores .harness.bak.
        return patch_mod.resolve_bundle_paths()

    def teardown_method(self, method):
        # Make absolutely sure the bundle is restored after each test.
        try:
            paths = patch_mod.resolve_bundle_paths()
            patch_mod.uninstall(paths, restore_backup=True)
        except Exception:
            pass

    def test_status_returns_installed_field(self):
        s = patch_mod.status()
        assert "installed" in s
        assert "exe" in s
        assert "translator_py" in s

    def test_install_then_uninstall_round_trip(self, paths):
        # Force a clean state
        patch_mod.uninstall(paths, restore_backup=True)
        assert patch_mod.is_installed(paths) is False

        res = patch_mod.install(paths, backup=True)
        assert res["installed"] is True
        # The marker should be in translator.py
        text = Path(paths["translator_py"]).read_text(encoding="utf-8", errors="replace")
        assert MIMO_CLASS_MARKER in text
        # And registered in pdf2zh.py
        pz_text = Path(paths["pdf2zh_py"]).read_text(encoding="utf-8", errors="replace")
        assert "MiMoTranslator" in pz_text
        assert patch_mod.is_installed(paths) is True

        # Idempotent install
        res2 = patch_mod.install(paths, backup=True)
        assert res2["installed"] is False
        assert res2["reason"] == "already_present"

        # Uninstall
        u = patch_mod.uninstall(paths, restore_backup=True)
        assert u["uninstalled"] is True
        assert u["method"] == "restored_backup"
        assert patch_mod.is_installed(paths) is False

    def test_uninstall_when_not_installed(self, paths):
        patch_mod.uninstall(paths, restore_backup=True)
        u = patch_mod.uninstall(paths, restore_backup=True)
        assert u["uninstalled"] is False
        assert u["reason"] == "not_present"


# ── TestReplSkin ─────────────────────────────────────────────────────


class TestReplSkin:
    def test_banner_runs(self, capsys):
        skin = ReplSkin("pdf2zh")
        skin.print_banner()
        captured = capsys.readouterr()
        assert "cli-anything-pdf2zh" in captured.out

    def test_prompt_non_empty(self):
        skin = ReplSkin("pdf2zh")
        p = skin.prompt(project_name="doc.pdf", modified=True)
        assert "doc.pdf" in p
        assert "*" in p

    def test_table_renders(self, capsys):
        skin = ReplSkin("pdf2zh")
        skin.table(("a", "b"), [("1", "2"), ("3", "4")])
        captured = capsys.readouterr()
        assert "a" in captured.out
        assert "1" in captured.out


# ── TestTranslateIO ──────────────────────────────────────────────────


class TestTranslateIO:
    def test_parse_babeldoc_output(self):
        sample = """
[INFO] ... babeldoc translation running ...
Original PDF: /tmp/in.pdf
Time Cost: 4.21s
Mono PDF: /tmp/in-mono.pdf
Dual PDF: /tmp/in-dual.pdf
"""
        r = backend.parse_babeldoc_output(sample)
        assert r["original"] == "/tmp/in.pdf"
        assert abs(r["time"] - 4.21) < 0.01
        assert r["mono"] == "/tmp/in-mono.pdf"
        assert r["dual"] == "/tmp/in-dual.pdf"

    def test_parse_babeldoc_output_handles_missing_block(self):
        r = backend.parse_babeldoc_output("no result here")
        assert r["original"] is None
        assert r["mono"] is None


# ── TestMcpPassthrough ──────────────────────────────────────────────


class TestMcpPassthrough:
    def test_mcp_invokes_exe(self, monkeypatch):
        # We don't want to actually execvp in unit tests — just confirm
        # the path-resolver is called and the args include --mcp.
        captured = {}

        def fake_execvp(file, args):
            captured["file"] = file
            captured["args"] = args

        monkeypatch.setattr(os, "execvp", fake_execvp)
        from click.testing import CliRunner
        from cli_anything.pdf2zh.pdf2zh_cli import cli

        r = CliRunner().invoke(cli, ["mcp"])
        assert captured["file"].endswith("pdf2zh.exe")
        assert "--mcp" in captured["args"]
