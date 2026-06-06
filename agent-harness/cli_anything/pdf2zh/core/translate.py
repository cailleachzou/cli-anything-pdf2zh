"""High-level translate operations used by the CLI.

This module wraps ``utils.pdf2zh_backend.run_translate`` with:
  * session-style state (current input, current output dir, current service)
  * project-file persistence (so a workflow can be saved and replayed)
  * per-call JSON-friendly result dicts
  * a default fallback chain (minimax → google) so an unset/misconfigured
    API key degrades to a free translator instead of a hard failure

The actual translation is delegated to pdf2zh.exe. The harness never tries
to translate in-process — that is the job of the real software.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from cli_anything.pdf2zh.utils import pdf2zh_backend as backend


# ── Fallback chain ─────────────────────────────────────────────────────


# When the default service (minimax) is requested but the EXE fails — e.g.
# the patch isn't installed, the API key isn't configured, or the API is
# down — retry once with the next service in the chain. The chain only
# applies when the user did not explicitly pick a non-default service.
DEFAULT_FALLBACK_CHAIN: List[str] = ["minimax", "google"]


def _next_fallback(current: str) -> Optional[str]:
    """Return the next service in the fallback chain, or None."""
    if current not in DEFAULT_FALLBACK_CHAIN:
        return None
    idx = DEFAULT_FALLBACK_CHAIN.index(current)
    if idx + 1 >= len(DEFAULT_FALLBACK_CHAIN):
        return None
    return DEFAULT_FALLBACK_CHAIN[idx + 1]


# ── Session state ───────────────────────────────────────────────────────


@dataclass
class TranslateOptions:
    """Mirror of pdf2zh's CLI args, minus positional files."""

    lang_in: str = "en"
    lang_out: str = "zh"
    service: str = "minimax"
    thread: int = 4
    pages: str = ""
    babeldoc: bool = False
    ignore_cache: bool = False
    compatible: bool = False
    skip_subset_fonts: bool = False
    onnx: str = ""
    prompt: str = ""
    output_dir: str = ""
    env: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Session:
    """REPL session state."""

    project_path: Optional[str] = None
    current_pdf: Optional[str] = None
    options: TranslateOptions = field(default_factory=TranslateOptions)
    modified: bool = False

    def to_dict(self) -> dict:
        return {
            "project_path": self.project_path,
            "current_pdf": self.current_pdf,
            "options": self.options.to_dict(),
            "modified": self.modified,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        opts = data.get("options", {}) or {}
        # Filter to known fields so the JSON can grow safely over versions.
        known = {f for f in TranslateOptions.__dataclass_fields__}
        clean_opts = {k: v for k, v in opts.items() if k in known}
        return cls(
            project_path=data.get("project_path"),
            current_pdf=data.get("current_pdf"),
            options=TranslateOptions(**clean_opts),
            modified=bool(data.get("modified", False)),
        )


# ── Project file (.json) ───────────────────────────────────────────────


def save_project(path: str, session: Session) -> str:
    """Write the current session to a JSON project file. Returns the path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_format": "cli-anything-pdf2zh/project@1",
        "session": session.to_dict(),
    }
    with p.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    session.project_path = str(p.resolve())
    session.modified = False
    return str(p.resolve())


def load_project(path: str) -> Session:
    """Read a JSON project file back into a Session."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"project file not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("_format") != "cli-anything-pdf2zh/project@1":
        raise ValueError(
            f"{path} is not a cli-anything-pdf2zh project file "
            f"(got _format={data.get('_format')!r})"
        )
    return Session.from_dict(data.get("session", {}))


# ── Translate one or more files ─────────────────────────────────────────


def translate_files(
    files: List[str],
    *,
    output_dir: str,
    options: TranslateOptions,
    env_overrides: Optional[Dict[str, str]] = None,
    exe_path: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Run the EXE on one or more files and return a JSON-friendly result.

    ``env_overrides`` is merged on top of the process env; pass API keys
    here (e.g. ``{"MINIMAX_API_KEY": "..."}``).

    If ``options.service`` is the default ``minimax`` and the first attempt
    fails (non-zero exit), the call is retried once with the next service
    in :data:`DEFAULT_FALLBACK_CHAIN` (currently ``google``). The returned
    dict carries ``fallback_used`` / ``fallback_from`` / ``fallback_to`` /
    ``fallback_reason`` fields so the caller can tell what happened.

    Auto-fallback is suppressed when the user explicitly picked a
    non-default service — they asked for that engine on purpose, and
    silently swapping it out is more confusing than the original error.
    """
    if not files:
        raise ValueError("translate_files requires at least one file")

    # Sanity-check the inputs up front. The EXE will check again, but a
    # fast failure with a clear message helps agents self-correct.
    missing = [f for f in files if not Path(f).is_file()]
    if missing:
        raise FileNotFoundError(
            "Input file(s) not found: " + ", ".join(missing)
        )

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    merged_env = dict(options.env or {})
    if env_overrides:
        merged_env.update(env_overrides)

    result = _run_translate_once(
        files, output_dir, options, merged_env, exe_path, timeout
    )

    # Auto-fallback: only kicks in for the default service. If the user
    # explicitly chose a different one (openai, deepl, …), respect it.
    if (
        result.get("exit_code", 0) != 0
        and options.service == DEFAULT_FALLBACK_CHAIN[0]
    ):
        fallback_service = _next_fallback(options.service)
        if fallback_service:
            fallback_opts = copy.copy(options)
            fallback_opts.service = fallback_service
            fallback_result = _run_translate_once(
                files, output_dir, fallback_opts, merged_env, exe_path, timeout
            )
            fallback_result["fallback_used"] = True
            fallback_result["fallback_from"] = options.service
            fallback_result["fallback_to"] = fallback_service
            fallback_result["fallback_reason"] = (
                (result.get("stderr_tail") or "")
                + (result.get("stdout_tail") or "")
            )[-300:]
            return fallback_result

    return result


def _run_translate_once(
    files: List[str],
    output_dir: str,
    options: TranslateOptions,
    merged_env: Dict[str, str],
    exe_path: Optional[str],
    timeout: Optional[float],
) -> Dict[str, Any]:
    """Single EXE invocation — the building block used by the fallback loop."""
    raw = backend.run_translate(
        files,
        output=output_dir,
        service=options.service,
        lang_in=options.lang_in,
        lang_out=options.lang_out,
        thread=options.thread,
        pages=options.pages or None,
        babeldoc=options.babeldoc,
        ignore_cache=options.ignore_cache,
        compatible=options.compatible,
        skip_subset_fonts=options.skip_subset_fonts,
        vfont="",
        vchar="",
        onnx=options.onnx or None,
        prompt=options.prompt or None,
        env_overrides=merged_env or None,
        exe_path=exe_path,
        timeout=timeout,
    )
    payload = raw.to_dict()
    payload["inputs"] = list(files)
    return payload


def translate_directory(
    directory: str,
    *,
    output_dir: str,
    options: TranslateOptions,
    env_overrides: Optional[Dict[str, str]] = None,
    exe_path: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Recursively translate every PDF in a directory.

    Uses the same EXE invocation as ``translate_files``; the EXE accepts a
    positional list of files. The harness does the directory walk.
    """
    p = Path(directory)
    if not p.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")
    pdfs = sorted(str(x) for x in p.rglob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF files found under {directory}")
    return translate_files(
        pdfs,
        output_dir=output_dir,
        options=options,
        env_overrides=env_overrides,
        exe_path=exe_path,
        timeout=timeout,
    )
