"""ReplSkin — vendored copy from the cli-anything plugin.

Trimmed/modified copy of the plugin's ``repl_skin.py`` so the harness
package is self-contained when installed via ``pip install -e .``.
The full plugin file is ~600 lines; we only ship the parts we need.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_ITALIC = "\033[3m"
_UNDERLINE = "\033[4m"

_CYAN = "\033[38;5;80m"
_WHITE = "\033[97m"
_GRAY = "\033[38;5;245m"
_DARK_GRAY = "\033[38;5;240m"
_LIGHT_GRAY = "\033[38;5;250m"

_ACCENT = "\033[38;5;141m"  # pdf2zh: violet

_GREEN = "\033[38;5;78m"
_YELLOW = "\033[38;5;220m"
_RED = "\033[38;5;196m"
_BLUE = "\033[38;5;75m"
_MAGENTA = "\033[38;5;176m"

_ICON = f"{_CYAN}{_BOLD}◆{_RESET}"
_ICON_SMALL = f"{_CYAN}▸{_RESET}"

_H_LINE = "─"
_V_LINE = "│"
_TL = "╭"
_TR = "╮"
_BL = "╰"
_BR = "╯"


def _repo_root_skill_path(name: str) -> Path:
    """Prefer the canonical repo-root skills/ path during development."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "skills" / f"cli-anything-{name}" / "SKILL.md"
        if candidate.is_file():
            return candidate
    return candidate  # not found


def _packaged_skill_path(name: str) -> Path:
    return Path(__file__).resolve().parent.parent / "skills" / "SKILL.md"


class ReplSkin:
    def __init__(self, software: str, version: str = "0.1.0"):
        self.software = software
        self.version = version
        self.skill_path = _repo_root_skill_path(software)
        if not self.skill_path.is_file():
            self.skill_path = _packaged_skill_path(software)

    # ── Banner ──────────────────────────────────────────────────────

    def print_banner(self) -> None:
        bar = _H_LINE * 64
        print(f"{_ACCENT}{_TL}{bar}{_TR}{_RESET}")
        print(
            f"{_ACCENT}{_V_LINE}{_RESET}  {_ICON} {_BOLD}{_ACCENT}"
            f"cli-anything-{self.software}{_RESET}  "
            f"{_DIM}v{self.version}{_RESET}  "
            f"{_DIM}(PDFMathTranslate harness){_RESET}  {_ACCENT}{_V_LINE}{_RESET}"
        )
        print(f"{_ACCENT}{_V_LINE}{_RESET}  {_DIM}Skill: {_RESET}{self.skill_path}")
        print(f"{_ACCENT}{_BL}{bar}{_BR}{_RESET}")

    # ── Prompt + status helpers ─────────────────────────────────────

    def prompt(self, project_name: str | None = None, modified: bool = False) -> str:
        flag = "*" if modified else ""
        proj = f" {_DIM}[{project_name}]{flag}{_RESET}" if project_name else ""
        return f"{_ACCENT}{_BOLD}{self.software}{_RESET}{proj} {_CYAN}▸{_RESET} "

    def success(self, msg: str) -> None:
        print(f"  {_GREEN}✓{_RESET} {msg}")

    def error(self, msg: str) -> None:
        print(f"  {_RED}✗{_RESET} {msg}", file=sys.stderr)

    def warning(self, msg: str) -> None:
        print(f"  {_YELLOW}⚠{_RESET} {msg}")

    def info(self, msg: str) -> None:
        print(f"  {_BLUE}●{_RESET} {msg}")

    def status(self, key: str, value: str) -> None:
        print(f"  {_DIM}{key}:{_RESET} {value}")

    def table(self, headers, rows) -> None:
        widths = [len(h) for h in headers]
        for r in rows:
            for i, c in enumerate(r):
                widths[i] = max(widths[i], len(str(c)))
        sep = _H_LINE * (sum(widths) + 3 * len(headers) + 1)
        print(f"  {_DARK_GRAY}{sep}{_RESET}")
        line = "  " + _V_LINE + _V_LINE.join(
            f" {h:<{widths[i]}} " for i, h in enumerate(headers)
        ) + _V_LINE
        print(f"  {_BOLD}{_WHITE}{line}{_RESET}")
        print(f"  {_DARK_GRAY}{sep}{_RESET}")
        for r in rows:
            line = "  " + _V_LINE + _V_LINE.join(
                f" {str(c):<{widths[i]}} " for i, c in enumerate(r)
            ) + _V_LINE
            print(line)
        print(f"  {_DARK_GRAY}{sep}{_RESET}")

    def print_goodbye(self) -> None:
        print(f"  {_DIM}Bye.{_RESET}")
