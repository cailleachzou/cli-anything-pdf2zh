"""Backend wrapper around the pdf2zh Windows EXE.

This module is the ONLY place in the harness that talks to the real
PDFMathTranslate software. Per the cli-anything HARNESS rule:

    "The real software is a hard dependency. The CLI MUST invoke the actual
    application (LibreOffice, Blender, GIMP, etc.) for rendering and export.
    Do NOT reimplement rendering in Python."

For pdf2zh the "real software" is `C:\\Program Files\\pdf2zh\\build\\pdf2zh.exe`
(PyStand bundle). We shell out to it with `subprocess.run` and capture
stdout/stderr/exit-code.

Resolution order for the EXE path:
1. Environment variable ``PDF2ZH_EXE_PATH`` (explicit override).
2. ``shutil.which("pdf2zh")`` (works if user added it to PATH).
3. The standard Windows install: ``C:\\Program Files\\pdf2zh\\build\\pdf2zh.exe``.
4. A sibling build dir next to this file (dev convenience):
   ``<this-package>/../../../build/pdf2zh.exe`` (resolved upward).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ── EXE path resolution ─────────────────────────────────────────────────


DEFAULT_EXE_CANDIDATES: List[str] = [
    r"C:\Program Files\pdf2zh\build\pdf2zh.exe",
    r"C:\Program Files (x86)\pdf2zh\build\pdf2zh.exe",
    "/usr/local/bin/pdf2zh",
    "/opt/pdf2zh/pdf2zh",
    "/usr/bin/pdf2zh",
]


def _dev_sibling_exe() -> Optional[str]:
    """Walk up from this file to find a sibling ``build/pdf2zh.exe``.

    Useful when the harness is developed inside ``pdf2zh/agent-harness/``
    and the user has not exported the EXE to PATH.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "build" / "pdf2zh.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def find_pdf2zh_exe(explicit: Optional[str] = None) -> str:
    """Locate the pdf2zh executable. Raises ``RuntimeError`` with install
    instructions if not found."""
    if explicit:
        if not Path(explicit).is_file():
            raise RuntimeError(
                f"PDF2ZH_EXE_PATH points to {explicit!r} but the file does not exist."
            )
        return explicit

    env_path = os.environ.get("PDF2ZH_EXE_PATH", "").strip()
    if env_path:
        if not Path(env_path).is_file():
            raise RuntimeError(
                f"PDF2ZH_EXE_PATH={env_path!r} does not point to a valid file."
            )
        return env_path

    in_path = shutil.which("pdf2zh")
    if in_path:
        return in_path

    for candidate in DEFAULT_EXE_CANDIDATES:
        if Path(candidate).is_file():
            return candidate

    sibling = _dev_sibling_exe()
    if sibling:
        return sibling

    raise RuntimeError(
        "Could not locate pdf2zh.exe. Searched:\n"
        + "\n".join(f"  - {p}" for p in DEFAULT_EXE_CANDIDATES)
        + "\n  - PATH (which pdf2zh)\n"
        + "  - $PDF2ZH_EXE_PATH\n\n"
        "Install PDFMathTranslate from "
        "https://github.com/PDFMathTranslate/PDFMathTranslate/releases and "
        "either:\n"
        "  (a) put pdf2zh.exe in your PATH, or\n"
        "  (b) set PDF2ZH_EXE_PATH=C:\\Program Files\\pdf2zh\\build\\pdf2zh.exe"
    )


# ── Result types ────────────────────────────────────────────────────────


@dataclass
class TranslateResult:
    """Structured result of a translate invocation."""

    mono_pdf: Optional[str] = None
    dual_pdf: Optional[str] = None
    output_dir: str = ""
    service: str = ""
    lang_in: str = ""
    lang_out: str = ""
    thread: int = 4
    babeldoc: bool = False
    babeldoc_original: Optional[str] = None
    babeldoc_time: Optional[float] = None
    babeldoc_mono: Optional[str] = None
    babeldoc_dual: Optional[str] = None
    exit_code: int = 0
    duration_s: float = 0.0
    stdout_tail: str = ""
    stderr_tail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Argument builder ────────────────────────────────────────────────────


def build_translate_args(
    files: List[str],
    *,
    lang_in: str = "en",
    lang_out: str = "zh",
    service: str = "google",
    output: str = "",
    thread: int = 4,
    pages: Optional[str] = None,
    vfont: str = "",
    vchar: str = "",
    babeldoc: bool = False,
    compatible: bool = False,
    skip_subset_fonts: bool = False,
    ignore_cache: bool = False,
    onnx: Optional[str] = None,
    prompt: Optional[str] = None,
    config: Optional[str] = None,
    authorized: Optional[List[str]] = None,
    debug: bool = False,
    env_overrides: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Build the argv list for `pdf2zh.exe files ...`.

    Any extra env vars (e.g. ``OPENAI_API_KEY``) should be passed via
    ``env_overrides`` and merged into the process environment at run time.
    """
    if not files:
        raise ValueError("build_translate_args requires at least one file")
    if not output:
        raise ValueError("build_translate_args requires an output directory")

    args: List[str] = []
    for f in files:
        args.append(str(f))

    if pages:
        args.extend(["--pages", pages])
    if vfont:
        args.extend(["--vfont", vfont])
    if vchar:
        args.extend(["--vchar", vchar])
    args.extend(["--lang-in", lang_in])
    args.extend(["--lang-out", lang_out])
    args.extend(["--service", service])
    args.extend(["--output", output])
    args.extend(["--thread", str(thread)])
    if compatible:
        args.append("--compatible")
    if onnx:
        args.extend(["--onnx", onnx])
    if prompt:
        args.extend(["--prompt", prompt])
    if config:
        args.extend(["--config", config])
    if authorized:
        args.extend(["--authorized", *authorized])
    if skip_subset_fonts:
        args.append("--skip-subset-fonts")
    if ignore_cache:
        args.append("--ignore-cache")
    if babeldoc:
        args.append("--babeldoc")
    if debug:
        args.append("--debug")

    return args


# ── Stdout parsing ──────────────────────────────────────────────────────


_BABELDOC_RESULT_RE = (
    r"Original PDF:\s*(?P<original>\S+).*?"
    r"Time Cost:\s*(?P<time>[\d.]+)s.*?"
    r"Mono PDF:\s*(?P<mono>\S+).*?"
    r"Dual PDF:\s*(?P<dual>\S+)"
)


def parse_babeldoc_output(stdout: str) -> Dict[str, Optional[str]]:
    """Best-effort parse of the babeldoc result block printed at the end of
    a ``--babeldoc`` run. Returns a dict with the original/mono/dual paths
    and the time, or empty values if the block is not present."""
    import re

    m = re.search(_BABELDOC_RESULT_RE, stdout, re.DOTALL)
    if not m:
        return {"original": None, "time": None, "mono": None, "dual": None}
    return {
        "original": m.group("original"),
        "time": float(m.group("time")) if m.group("time") else None,
        "mono": None if m.group("mono") == "None" else m.group("mono"),
        "dual": None if m.group("dual") == "None" else m.group("dual"),
    }


def expected_output_paths(file_path: str, output_dir: str) -> Dict[str, str]:
    """Given an input PDF, predict the two output paths the EXE will create."""
    name = Path(file_path).stem
    out = Path(output_dir)
    return {
        "mono": str(out / f"{name}-mono.pdf"),
        "dual": str(out / f"{name}-dual.pdf"),
    }


# ── Main entry point ────────────────────────────────────────────────────


def run_translate(
    files: List[str],
    *,
    output: str,
    service: str = "google",
    lang_in: str = "en",
    lang_out: str = "zh",
    thread: int = 4,
    pages: Optional[str] = None,
    babeldoc: bool = False,
    ignore_cache: bool = False,
    compatible: bool = False,
    skip_subset_fonts: bool = False,
    vfont: str = "",
    vchar: str = "",
    onnx: Optional[str] = None,
    prompt: Optional[str] = None,
    config: Optional[str] = None,
    env_overrides: Optional[Dict[str, str]] = None,
    debug: bool = False,
    exe_path: Optional[str] = None,
    timeout: Optional[float] = None,
) -> TranslateResult:
    """Invoke pdf2zh.exe to translate one or more PDFs.

    Returns a ``TranslateResult`` with predicted output paths even if the EXE
    failed (so the caller can render diagnostic info).
    """
    if not files:
        raise ValueError("run_translate requires at least one file")
    Path(output).mkdir(parents=True, exist_ok=True)

    exe = find_pdf2zh_exe(exe_path)
    args = build_translate_args(
        files,
        output=output,
        lang_in=lang_in,
        lang_out=lang_out,
        service=service,
        thread=thread,
        pages=pages,
        vfont=vfont,
        vchar=vchar,
        babeldoc=babeldoc,
        compatible=compatible,
        skip_subset_fonts=skip_subset_fonts,
        ignore_cache=ignore_cache,
        onnx=onnx,
        prompt=prompt,
        config=config,
        debug=debug,
    )

    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    import time

    started = time.time()
    try:
        completed = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"pdf2zh.exe timed out after {timeout}s. "
            "The translation is taking too long — try a smaller page range "
            "or a different service."
        ) from e
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Could not launch {exe!r}. Is PDFMathTranslate installed?"
        ) from e

    duration = time.time() - started

    # Predict the mono/dual output paths from the first input (when not
    # --babeldoc). The EXE actually writes them; we surface them either way.
    first_file = files[0]
    predicted = expected_output_paths(first_file, output)

    result = TranslateResult(
        mono_pdf=predicted["mono"] if not babeldoc else None,
        dual_pdf=predicted["dual"] if not babeldoc else None,
        output_dir=output,
        service=service,
        lang_in=lang_in,
        lang_out=lang_out,
        thread=thread,
        babeldoc=babeldoc,
        exit_code=completed.returncode,
        duration_s=duration,
        stdout_tail=completed.stdout[-2000:],
        stderr_tail=completed.stderr[-2000:],
    )

    if babeldoc:
        bd = parse_babeldoc_output(completed.stdout)
        result.babeldoc_original = bd.get("original")
        result.babeldoc_time = bd.get("time")
        result.babeldoc_mono = bd.get("mono")
        result.babeldoc_dual = bd.get("dual")

    if completed.returncode != 0:
        # Build a useful error message. Don't raise — return the result so
        # the CLI can show the tail and the agent can decide what to do.
        result.exit_code = completed.returncode

    return result


# ── Lightweight probes (no full translate) ───────────────────────────────


def version(exe_path: Optional[str] = None) -> str:
    """Return ``pdf2zh vX.Y.Z`` from the EXE's ``--version`` flag."""
    exe = find_pdf2zh_exe(exe_path)
    out = subprocess.run(
        [exe, "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return (out.stdout or out.stderr).strip()


# ── JSON output helpers (for Click commands) ────────────────────────────


def to_json(obj) -> str:
    """Stable JSON serialisation for click.echo(..., json=True) consumers."""
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
