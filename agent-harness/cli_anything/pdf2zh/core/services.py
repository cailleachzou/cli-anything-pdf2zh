"""Catalog of available translation services.

The 20+ services are discovered by reading the bundled ``translator.py``
and the harness's patch. We also list the services that pdf2zh.py registers
in its ``yadt_main`` translator selection block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


# ── Static catalog ──────────────────────────────────────────────────────
#
# When the EXE is not installed, we still want `services list` to return
# useful info, so we hard-code the known list. If a new translator is added
# to the bundle (e.g. by the MiniMax patch) and the bundle is reachable,
# `discover_from_bundle()` will return the live authoritative list.
#


SERVICES: List[Dict[str, str]] = [
    # name, kind, requires_key, description
    {"name": "google",       "kind": "free",  "key": "no",  "desc": "Google Translate (web endpoint)"},
    {"name": "bing",         "kind": "key",   "key": "yes", "desc": "Bing Microsoft Translator"},
    {"name": "deepl",        "kind": "key",   "key": "yes", "desc": "DeepL API"},
    {"name": "deeplx",       "kind": "self",  "key": "no",  "desc": "DeepLX (self-hosted)"},
    {"name": "ollama",       "kind": "local", "key": "no",  "desc": "Ollama local model"},
    {"name": "xinference",   "kind": "self",  "key": "no",  "desc": "Xinference local server"},
    {"name": "azure-openai", "kind": "key",   "key": "yes", "desc": "Azure OpenAI"},
    {"name": "openai",       "kind": "key",   "key": "yes", "desc": "OpenAI Chat Completions"},
    {"name": "zhipu",        "kind": "key",   "key": "yes", "desc": "Zhipu GLM"},
    {"name": "modelscope",   "kind": "key",   "key": "yes", "desc": "ModelScope"},
    {"name": "silicon",      "kind": "key",   "key": "yes", "desc": "SiliconFlow"},
    {"name": "gemini",       "kind": "key",   "key": "yes", "desc": "Google Gemini (OpenAI-compat)"},
    {"name": "azure",        "kind": "key",   "key": "yes", "desc": "Azure Translator"},
    {"name": "tencent",      "kind": "key",   "key": "yes", "desc": "Tencent TMT"},
    {"name": "dify",         "kind": "self",  "key": "yes", "desc": "Dify workflow"},
    {"name": "anythingllm",  "kind": "self",  "key": "yes", "desc": "AnythingLLM workspace"},
    {"name": "argos",        "kind": "free",  "key": "no",  "desc": "Argos Translate (offline)"},
    {"name": "grok",         "kind": "key",   "key": "yes", "desc": "xAI Grok"},
    {"name": "groq",         "kind": "key",   "key": "yes", "desc": "Groq Cloud"},
    {"name": "deepseek",     "kind": "key",   "key": "yes", "desc": "Deepseek"},
    {"name": "openailiked",  "kind": "key",   "key": "yes", "desc": "Any OpenAI-compatible endpoint"},
    {"name": "qwenmt",       "kind": "key",   "key": "yes", "desc": "QwenMT (Aliyun DashScope)"},
    {"name": "minimax",      "kind": "key",   "key": "yes", "desc": "MiniMax (added by harness patch)"},
]


# ── Discovery from the bundled source (live authoritative list) ────────


_CLASS_RE = re.compile(
    r"^class\s+(\w+)\s*\(\s*(?:BaseTranslator|OpenAITranslator)\s*\)",
    re.MULTILINE,
)


def discover_from_bundle(backend_root: Optional[Path]) -> List[str]:
    """Walk ``build/site-packages/pdf2zh/`` and return ``name = "..."``
    attributes found in ``translator.py``.

    Falls back to an empty list if the bundle is not reachable.
    """
    if backend_root is None:
        return []
    candidate = backend_root / "pdf2zh" / "translator.py"
    if not candidate.is_file():
        return []
    text = candidate.read_text(encoding="utf-8", errors="replace")
    services: List[str] = []
    for cls_match in _CLASS_RE.finditer(text):
        cls_start = cls_match.end()
        # Look at the next 800 chars for `name = "..."`
        head = text[cls_start:cls_start + 800]
        name_match = re.search(r'name\s*=\s*["\']([a-z0-9_]+)["\']', head)
        if name_match:
            services.append(name_match.group(1))
    # Stable, unique, sorted by appearance
    seen = set()
    ordered = []
    for s in services:
        if s not in seen and s != "base":
            seen.add(s)
            ordered.append(s)
    return ordered


def find_bundle_root(exe_path: str) -> Optional[Path]:
    """Given a path to pdf2zh.exe, return the parent of the site-packages
    directory (i.e. ``build/``)."""
    p = Path(exe_path)
    # bundle layout: <root>/build/pdf2zh.exe and <root>/build/site-packages/
    if p.parent.name == "build":
        return p.parent
    return None


# ── CLI helpers ─────────────────────────────────────────────────────────


def list_services(exe_path: Optional[str] = None) -> List[Dict[str, str]]:
    """Return the service catalog. If the EXE is reachable, prepend a
    ``_live`` flag to each entry that the bundle also has."""
    bundle_root = find_bundle_root(exe_path) if exe_path else None
    live = set(discover_from_bundle(bundle_root))
    catalog: List[Dict[str, str]] = []
    for svc in SERVICES:
        entry = dict(svc)
        if live and entry["name"] not in live:
            entry["note"] = "not registered in installed bundle"
        catalog.append(entry)
    return catalog


def describe_service(name: str) -> Optional[Dict[str, str]]:
    for svc in SERVICES:
        if svc["name"] == name:
            return dict(svc)
    return None
