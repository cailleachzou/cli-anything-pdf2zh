"""Read / write the PDFMathTranslate config file.

The original library stores translator envs in::

    ~/.config/PDFMathTranslate/config.json

We mirror that file directly (no import of pdf2zh.config, since the EXE
black-box mode does not require Python-side ``pdf2zh``). This means our
writes are picked up by the EXE on the next run.

Schema (as written by ``pdf2zh.config.ConfigManager``)::

    {
      "translators": [
        { "name": "openai", "envs": {"OPENAI_API_KEY": "sk-..."} }
      ],
      "NOTO_FONT_PATH": null,
      ...
    }
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


CONFIG_PATH = Path.home() / ".config" / "PDFMathTranslate" / "config.json"


def _ensure_path() -> Path:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text("{}", encoding="utf-8")
    return CONFIG_PATH


def load_raw() -> Dict[str, Any]:
    p = _ensure_path()
    with p.open("r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_raw(data: Dict[str, Any]) -> str:
    p = _ensure_path()
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(p)


# ── Translator-env helpers (the interesting part) ──────────────────────


def list_translators() -> List[Dict[str, Any]]:
    """Return the list of configured translator entries."""
    data = load_raw()
    return list(data.get("translators", []))


def get_translator(name: str) -> Optional[Dict[str, Any]]:
    for t in list_translators():
        if t.get("name") == name:
            return t
    return None


def set_translator_env(name: str, envs: Dict[str, str]) -> Dict[str, Any]:
    """Upsert the env dict for translator ``name`` and return the entry."""
    data = load_raw()
    translators = list(data.get("translators", []))
    for t in translators:
        if t.get("name") == name:
            t["envs"] = dict(envs)
            break
    else:
        translators.append({"name": name, "envs": dict(envs)})
    data["translators"] = translators
    save_raw(data)
    return {"name": name, "envs": dict(envs)}


def set_translator_key(name: str, key: str, value: str) -> Dict[str, Any]:
    """Set a single key on a translator's envs (upsert translator if needed)."""
    data = load_raw()
    translators = list(data.get("translators", []))
    for t in translators:
        if t.get("name") == name:
            envs = dict(t.get("envs", {}))
            envs[key] = value
            t["envs"] = envs
            break
    else:
        translators.append({"name": name, "envs": {key: value}})
    data["translators"] = translators
    save_raw(data)
    return {"name": name, "key": key, "value_set": True}


def delete_translator(name: str) -> bool:
    data = load_raw()
    translators = list(data.get("translators", []))
    new = [t for t in translators if t.get("name") != name]
    if len(new) == len(translators):
        return False
    data["translators"] = new
    save_raw(data)
    return True


def get(key: str, default: Any = None) -> Any:
    """Read a top-level key (NOT a translator env). Returns the value or default.

    If the key is not present, falls back to the environment variable of the
    same name. The pdf2zh ConfigManager does the same.
    """
    data = load_raw()
    if key in data:
        return data[key]
    if key in os.environ:
        return os.environ[key]
    return default


def set_top(key: str, value: Any) -> Any:
    data = load_raw()
    data[key] = value
    save_raw(data)
    return value


def delete_top(key: str) -> bool:
    data = load_raw()
    if key in data:
        del data[key]
        save_raw(data)
        return True
    return False


def all_entries() -> Dict[str, Any]:
    return load_raw()
