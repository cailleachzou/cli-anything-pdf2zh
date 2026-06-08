"""Xiaomi MiMo translator class — added by harness to the bundled pdf2zh EXE.

The bundled ``translator.py`` is edited by ``core.patch`` to append this
class. Once installed, the EXE accepts ``--service mimo`` and consumes:

    MIMO_BASE_URL  default ``https://token-plan-cn.xiaomimimo.com/v1``
    MIMO_API_KEY   required, no default
    MIMO_MODEL     default ``mimo-v2.5-pro``

This file is intentionally a **standalone** copy of the class definition
(mirroring ``OpenAITranslator``) so the install script can paste it into
the bundled ``translator.py`` without any imports or top-level helpers.
"""

MIMO_TRANSLATOR_SOURCE = '''

# ── Xiaomi MiMo (added by cli-anything-pdf2zh harness) ────────────────
import os as _os

class MiMoTranslator(OpenAITranslator):
    # Xiaomi MiMo is an OpenAI-compatible chat-completions API.
    # This class is appended to the bundled translator.py by the harness
    # patch (idempotent). It mirrors OpenAITranslator and uses the same
    # prompt and cache plumbing.
    name = "mimo"
    envs = {
        "MIMO_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
        "MIMO_API_KEY":  None,
        "MIMO_MODEL":    "mimo-v2.5-pro",
    }
    CustomPrompt = True

    def __init__(
        self, lang_in, lang_out, model, envs=None, prompt=None, ignore_cache=False
    ):
        self.set_envs(envs)
        if not model:
            model = self.envs["MIMO_MODEL"]
        base_url = self.envs["MIMO_BASE_URL"]
        api_key = self.envs["MIMO_API_KEY"] or _os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not api_key:
            raise ValueError(
                "MIMO_API_KEY is not set and ANTHROPIC_AUTH_TOKEN not found. Run: "
                "cli-anything-pdf2zh config set-key mimo MIMO_API_KEY <key>"
            )
        super().__init__(
            lang_in,
            lang_out,
            model,
            base_url=base_url,
            api_key=api_key,
            ignore_cache=ignore_cache,
        )
        self.prompttext = prompt
        self.add_cache_impact_parameters("prompt", self.prompt("", self.prompttext))
# ── end Xiaomi MiMo translator ────────────────────────────────────────
'''


# Lines that the install script appends to the ``yadt_main`` translator
# registration block in the bundled ``pdf2zh.py``.
MIMO_REGISTRATION_LINES = '''    MiMoTranslator,'''  # to be inserted into the import list
MIMO_REGISTRATION_BLOCK = '''        MiMoTranslator,'''  # to be inserted into the list-comprehension


# Lightweight marker that the install script greps for to determine
# whether the class has already been added.
MIMO_CLASS_MARKER = "class MiMoTranslator(OpenAITranslator):"
MIMO_NAME_MARKER = 'name = "mimo"'
