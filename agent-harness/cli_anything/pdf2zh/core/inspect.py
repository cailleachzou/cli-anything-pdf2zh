"""PDF inspection utilities.

Used by the ``inspect`` CLI group to report page count, size, basic metadata
for input PDFs and the ``*-mono.pdf`` / ``*-dual.pdf`` output PDFs. Reads
PDFs with pymupdf (already a pdf2zh transitive dep, but we also try
pdfminer's lightweight page iterator as a fallback so the harness has zero
new heavyweight deps).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def _human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024.0:
            return f"{num:3.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"


def _validate_pdf_magic(path: Path) -> bool:
    """Return True if the first 5 bytes are ``b'%PDF-'``."""
    try:
        with path.open("rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def _count_pages_pymupdf(path: Path) -> Optional[int]:
    try:
        import pymupdf  # type: ignore
    except Exception:
        return None
    try:
        doc = pymupdf.Document(str(path))
        n = doc.page_count
        doc.close()
        return int(n)
    except Exception:
        return None


def _count_pages_pdfminer(path: Path) -> Optional[int]:
    try:
        from pdfminer.pdfpage import PDFPage  # type: ignore
    except Exception:
        return None
    try:
        with path.open("rb") as f:
            return sum(1 for _ in PDFPage.get_pages(f))
    except Exception:
        return None


def inspect_pdf(path: str) -> Dict[str, Any]:
    """Return a JSON-friendly description of a single PDF.

    Falls back through ``pymupdf -> pdfminer`` so the harness never crashes
    if pymupdf is unavailable.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    size = p.stat().st_size
    info: Dict[str, Any] = {
        "path": str(p.resolve()),
        "filename": p.name,
        "size_bytes": size,
        "size_human": _human_size(size),
        "is_valid_pdf": _validate_pdf_magic(p),
    }
    page_count = _count_pages_pymupdf(p) or _count_pages_pdfminer(p)
    info["page_count"] = page_count
    return info


def inspect_outputs(
    input_pdf: str,
    output_dir: str,
    *,
    babeldoc: bool = False,
    babeldoc_mono: Optional[str] = None,
    babeldoc_dual: Optional[str] = None,
) -> Dict[str, Any]:
    """Inspect the two output PDFs the EXE should have produced for a
    given input. Returns existence/size/page info and a sanity-check
    verdict."""
    name = Path(input_pdf).stem
    out = Path(output_dir)
    candidates = {
        "mono": out / f"{name}-mono.pdf",
        "dual": out / f"{name}-dual.pdf",
    }
    if babeldoc:
        if babeldoc_mono:
            candidates["mono"] = Path(babeldoc_mono)
        if babeldoc_dual:
            candidates["dual"] = Path(babeldoc_dual)

    result: Dict[str, Any] = {
        "input": str(Path(input_pdf).resolve()),
        "output_dir": str(out.resolve()),
        "files": {},
    }
    mono_size = None
    dual_size = None
    for kind, p in candidates.items():
        if p.is_file():
            info = inspect_pdf(str(p))
            result["files"][kind] = info
            if kind == "mono":
                mono_size = info["size_bytes"]
            else:
                dual_size = info["size_bytes"]
        else:
            result["files"][kind] = {"path": str(p), "exists": False}

    # Sanity: dual should be larger than mono (it embeds both languages)
    if mono_size is not None and dual_size is not None:
        result["mono_dual_ratio"] = round(dual_size / max(mono_size, 1), 3)
        result["verdict"] = (
            "ok"
            if dual_size > mono_size and mono_size > 0
            else "suspicious: dual not larger than mono"
        )
    else:
        result["verdict"] = "incomplete: missing output(s)"

    return result
