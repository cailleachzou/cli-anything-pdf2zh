"""Install / uninstall the MiniMax translator in the bundled pdf2zh EXE.

This module edits two files inside the PDFMathTranslate bundle:

  * ``<build>/site-packages/pdf2zh/translator.py``
  * ``<build>/site-packages/pdf2zh/pdf2zh.py``

The class definition appended to ``translator.py`` is sourced from
``patch/__init__.py::MINIMAX_TRANSLATOR_SOURCE`` so the source of truth
lives in the harness package, not in a half-baked string in this file.

Operations are idempotent: running ``install()`` twice does not duplicate
the class.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from cli_anything.pdf2zh.patch import (
    MINIMAX_CLASS_MARKER,
    MINIMAX_NAME_MARKER,
    MINIMAX_TRANSLATOR_SOURCE,
)
from cli_anything.pdf2zh.utils import pdf2zh_backend as backend


# ── Path resolution ─────────────────────────────────────────────────────


def resolve_bundle_paths(exe_path: Optional[str] = None) -> Dict[str, str]:
    """Given the EXE path (or the default), return the absolute paths of
    the files we edit."""
    exe = backend.find_pdf2zh_exe(exe_path)
    p = Path(exe)
    # Standard layout: <root>/build/pdf2zh.exe and <root>/build/site-packages/
    if p.parent.name != "build":
        raise RuntimeError(
            f"pdf2zh.exe is not in a 'build/' parent directory: {exe}\n"
            "Cannot auto-locate the bundled site-packages. "
            "Pass --exe with the canonical build path."
        )
    build_dir = p.parent
    sp = build_dir / "site-packages" / "pdf2zh"
    return {
        "exe": str(p),
        "build_dir": str(build_dir),
        "translator_py": str(sp / "translator.py"),
        "pdf2zh_py": str(sp / "pdf2zh.py"),
        "converter_py": str(sp / "converter.py"),
    }


# ── Detection ───────────────────────────────────────────────────────────


def is_installed(paths: Dict[str, str]) -> bool:
    p = Path(paths["translator_py"])
    if not p.is_file():
        return False
    text = p.read_text(encoding="utf-8", errors="replace")
    return MINIMAX_CLASS_MARKER in text and MINIMAX_NAME_MARKER in text


# ── Install ─────────────────────────────────────────────────────────────


def install(paths: Dict[str, str], *, backup: bool = True) -> Dict[str, Any]:
    """Append the MiniMaxTranslator class to the bundled translator.py and
    register it in the pdf2zh.py and converter.py translator tables."""
    if is_installed(paths):
        return {
            "installed": False,
            "reason": "already_present",
            "paths": paths,
        }

    tr_path = Path(paths["translator_py"])
    pz_path = Path(paths["pdf2zh_py"])
    conv_path = Path(paths["converter_py"])

    if not tr_path.is_file():
        raise FileNotFoundError(f"missing {tr_path}")
    if not pz_path.is_file():
        raise FileNotFoundError(f"missing {pz_path}")

    if backup:
        for p in (tr_path, pz_path, conv_path):
            if p.is_file():
                bak = p.with_suffix(p.suffix + ".harness.bak")
                if not bak.exists():
                    shutil.copy2(p, bak)

    # 1. Append class to translator.py
    tr_text = tr_path.read_text(encoding="utf-8")
    if not tr_text.endswith("\n"):
        tr_text += "\n"
    tr_text += MINIMAX_TRANSLATOR_SOURCE
    tr_path.write_text(tr_text, encoding="utf-8")

    # 2. Patch pdf2zh.py: add "MiniMaxTranslator," to the import list AND
    #    the registration list inside yadt_main. Both must succeed.
    pz_text = pz_path.read_text(encoding="utf-8")
    pz_text, n_imports = _patch_pdf2zh_imports(pz_text)
    pz_text, n_registrations = _patch_pdf2zh_registrations(pz_text)
    pz_path.write_text(pz_text, encoding="utf-8")

    # 3. Patch converter.py: add "MiniMaxTranslator," to the import list
    #    AND to the per-service lookup list in TranslateConverter.__init__.
    n_conv_imports = 0
    n_conv_lookups = 0
    if conv_path.is_file():
        conv_text = conv_path.read_text(encoding="utf-8")
        conv_text, n_conv_imports = _patch_converter_imports(conv_text)
        conv_text, n_conv_lookups = _patch_converter_lookup(conv_text)
        conv_path.write_text(conv_text, encoding="utf-8")

    # Wipe __pycache__ so the next EXE launch re-imports the patched files
    cache_dir = pz_path.parent / "__pycache__"
    if cache_dir.is_dir():
        shutil.rmtree(cache_dir, ignore_errors=True)

    return {
        "installed": True,
        "imports_added": n_imports,
        "registrations_added": n_registrations,
        "converter_imports_added": n_conv_imports,
        "converter_lookup_added": n_conv_lookups,
        "paths": paths,
    }


def _patch_converter_imports(text: str) -> tuple[str, int]:
    """Insert ``MiniMaxTranslator,`` in the import block of converter.py.

    The block is a long list of imports from ``pdf2zh.translator``.
    """
    pattern = re.compile(
        r"(from pdf2zh\.translator import \(\n)((?:[ \t]*[A-Z][A-Za-z0-9_]*,\n)+)([ \t]*\))",
        re.MULTILINE,
    )

    def add_minimax(m: re.Match) -> str:
        head, body, tail = m.group(1), m.group(2), m.group(3)
        if "MiniMaxTranslator" in body:
            return m.group(0)
        new_body = body + "    MiniMaxTranslator,\n"
        return head + new_body + tail

    new_text, count = pattern.subn(add_minimax, text)
    return new_text, count


def _patch_converter_lookup(text: str) -> tuple[str, int]:
    """Insert ``MiniMaxTranslator,`` in the
    ``for translator in [...]:`` lookup list in ``TranslateConverter.__init__``.
    """
    pattern = re.compile(
        r"(for translator in \[)([^\]]+)(\]:)",
        re.DOTALL,
    )

    def add_minimax(m: re.Match) -> str:
        head, body, tail = m.group(1), m.group(2), m.group(3)
        if "MiniMaxTranslator" in body:
            return m.group(0)
        new_body = body.rstrip().rstrip(",") + ",\n                           MiniMaxTranslator,"
        return head + new_body + tail

    new_text, count = pattern.subn(add_minimax, text, count=1)
    return new_text, count


def _patch_pdf2zh_imports(text: str) -> tuple[str, int]:
    """Insert ``MiniMaxTranslator,`` in the import block of ``yadt_main``.

    The block is recognizable as a sequence of lines starting with 4 spaces
    followed by a capitalised identifier and a comma, inside
    ``pdf2zh.translator import (``. We anchor on the first such import
    block found.
    """
    pattern = re.compile(
        r"(from pdf2zh\.translator import \(\n)((?:[ \t]*[A-Z][A-Za-z0-9_]*,\n)+)([ \t]*\))",
        re.MULTILINE,
    )

    def add_minimax(m: re.Match) -> str:
        head, body, tail = m.group(1), m.group(2), m.group(3)
        if "MiniMaxTranslator" in body:
            return m.group(0)
        # Insert just after the last entry, before the closing paren.
        new_body = body + "        MiniMaxTranslator,\n"
        return head + new_body + tail

    new_text, count = pattern.subn(add_minimax, text)
    return new_text, count


def _patch_pdf2zh_registrations(text: str) -> tuple[str, int]:
    """Insert ``MiniMaxTranslator,`` in the ``yadt_main`` translator list
    that the for-loop iterates over.

    The block looks like::

        for translator in [
            GoogleTranslator,
            BingTranslator,
            ...
            QwenMtTranslator,
        ]:
    """
    pattern = re.compile(
        r"(for translator in \[\n)((?:[ \t]+[A-Z][A-Za-z0-9_]+,\n)+)([ \t]*\]:)",
        re.MULTILINE,
    )

    def add_minimax(m: re.Match) -> str:
        head, body, tail = m.group(1), m.group(2), m.group(3)
        if "MiniMaxTranslator" in body:
            return m.group(0)
        new_body = body + "        MiniMaxTranslator,\n"
        return head + new_body + tail

    new_text, count = pattern.subn(add_minimax, text)
    return new_text, count


# ── Uninstall ───────────────────────────────────────────────────────────


def uninstall(paths: Dict[str, str], *, restore_backup: bool = True) -> Dict[str, Any]:
    """Remove the MiniMax translator from the bundle.

    Strategy: prefer restoring the ``.harness.bak`` files written by
    ``install()``. Fall back to surgical string removal if no backup
    exists.
    """
    tr_path = Path(paths["translator_py"])
    pz_path = Path(paths["pdf2zh_py"])
    conv_path = Path(paths["converter_py"])

    if not is_installed(paths):
        return {"uninstalled": False, "reason": "not_present", "paths": paths}

    restored_from_backup = False
    if restore_backup:
        for p in (tr_path, pz_path, conv_path):
            bak = p.with_suffix(p.suffix + ".harness.bak")
            if bak.is_file():
                shutil.copy2(bak, p)
                restored_from_backup = True
        if restored_from_backup:
            cache_dir = pz_path.parent / "__pycache__"
            if cache_dir.is_dir():
                shutil.rmtree(cache_dir, ignore_errors=True)
            return {
                "uninstalled": True,
                "method": "restored_backup",
                "paths": paths,
            }

    # Fallback: surgical removal
    tr_text = tr_path.read_text(encoding="utf-8")
    new_tr = _strip_minimax_class(tr_text)
    tr_path.write_text(new_tr, encoding="utf-8")

    for p in (pz_path, conv_path):
        if p.is_file():
            t = p.read_text(encoding="utf-8")
            new_t = re.sub(r"^[ \t]*MiniMaxTranslator,\n", "", t, flags=re.MULTILINE)
            p.write_text(new_t, encoding="utf-8")

    cache_dir = pz_path.parent / "__pycache__"
    if cache_dir.is_dir():
        shutil.rmtree(cache_dir, ignore_errors=True)

    return {
        "uninstalled": True,
        "method": "surgical",
        "paths": paths,
    }


def _strip_minimax_class(text: str) -> str:
    """Remove the marker block (header banner + class + footer banner)
    that ``install()`` appended."""
    pattern = re.compile(
        r"\n*# ── MiniMax \(added by cli-anything-pdf2zh harness\) ─.*?"
        r"# ── end MiniMax translator ──+\n",
        re.DOTALL,
    )
    return pattern.sub("\n", text)


# ── Status / diag ──────────────────────────────────────────────────────


def status(exe_path: Optional[str] = None) -> Dict[str, Any]:
    try:
        paths = resolve_bundle_paths(exe_path)
    except RuntimeError as e:
        return {"error": str(e), "installed": False}
    return {
        "installed": is_installed(paths),
        "exe": paths["exe"],
        "translator_py": paths["translator_py"],
        "pdf2zh_py": paths["pdf2zh_py"],
        "converter_py": paths["converter_py"],
        "translator_py_exists": Path(paths["translator_py"]).is_file(),
        "pdf2zh_py_exists": Path(paths["pdf2zh_py"]).is_file(),
        "converter_py_exists": Path(paths["converter_py"]).is_file(),
    }
