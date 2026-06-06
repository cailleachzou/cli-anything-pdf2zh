"""Read / clear the PDFMathTranslate SQLite translation cache.

The original cache lives at::

    ~/.cache/pdf2zh/cache.v1.db

with a single ``_translation_cache`` table:

    id, translate_engine, translate_engine_params, original_text, translation

We use the stdlib ``sqlite3`` module to query it (no peewee import) so the
harness can ship without re-declaring the cache schema.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


CACHE_PATH = Path.home() / ".cache" / "pdf2zh" / "cache.v1.db"


def _open_ro() -> Optional[sqlite3.Connection]:
    if not CACHE_PATH.is_file():
        return None
    # Read-only URI mode
    uri = f"file:{CACHE_PATH}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        # Older Python fallback
        conn = sqlite3.connect(str(CACHE_PATH))
        conn.row_factory = sqlite3.Row
        return conn
    conn.row_factory = sqlite3.Row
    return conn


def summary() -> Dict[str, Any]:
    """High-level cache summary: size on disk, row count, top engines."""
    info: Dict[str, Any] = {
        "path": str(CACHE_PATH),
        "exists": CACHE_PATH.is_file(),
        "size_bytes": CACHE_PATH.stat().st_size if CACHE_PATH.is_file() else 0,
    }
    conn = _open_ro()
    if conn is None:
        info["row_count"] = 0
        info["top_engines"] = []
        return info
    try:
        try:
            cur = conn.execute("SELECT COUNT(*) FROM _translation_cache")
            info["row_count"] = int(cur.fetchone()[0])
            cur = conn.execute(
                "SELECT translate_engine AS engine, COUNT(*) AS n "
                "FROM _translation_cache GROUP BY translate_engine "
                "ORDER BY n DESC LIMIT 20"
            )
            info["top_engines"] = [
                {"engine": r["engine"], "count": r["n"]} for r in cur.fetchall()
            ]
        except sqlite3.OperationalError as e:
            # Table missing — treat as empty cache (e.g. fresh install,
            # old schema, or corrupted DB). pdf2zh will re-create on next
            # run via cache.init_db().
            info["row_count"] = 0
            info["top_engines"] = []
            info["note"] = f"cache table missing: {e}"
    finally:
        conn.close()
    return info


def list_entries(
    engine: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    conn = _open_ro()
    if conn is None:
        return []
    try:
        if engine:
            cur = conn.execute(
                "SELECT id, translate_engine, translate_engine_params, "
                "substr(original_text, 1, 200) AS original_text, "
                "substr(translation, 1, 200) AS translation "
                "FROM _translation_cache WHERE translate_engine = ? "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (engine, limit, offset),
            )
        else:
            cur = conn.execute(
                "SELECT id, translate_engine, translate_engine_params, "
                "substr(original_text, 1, 200) AS original_text, "
                "substr(translation, 1, 200) AS translation "
                "FROM _translation_cache ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = []
        for r in cur.fetchall():
            rows.append(
                {
                    "id": r["id"],
                    "engine": r["translate_engine"],
                    "params": r["translate_engine_params"],
                    "original_text": r["original_text"],
                    "translation": r["translation"],
                }
            )
        return rows
    finally:
        conn.close()


def clear(engine: Optional[str] = None) -> Dict[str, Any]:
    """Delete cache entries. If engine is None, drops the whole table.

    Returns a dict with ``deleted`` (count) and ``path``.
    """
    if not CACHE_PATH.is_file():
        return {"deleted": 0, "path": str(CACHE_PATH), "scope": engine or "all"}
    # We need write access — copy the conn pattern
    conn = sqlite3.connect(str(CACHE_PATH))
    try:
        if engine:
            cur = conn.execute(
                "DELETE FROM _translation_cache WHERE translate_engine = ?",
                (engine,),
            )
        else:
            cur = conn.execute("DELETE FROM _translation_cache")
        deleted = cur.rowcount
        conn.commit()
        return {"deleted": deleted, "path": str(CACHE_PATH), "scope": engine or "all"}
    finally:
        conn.close()
