"""MiniMax translator class — added by harness to the bundled pdf2zh EXE.

The bundled ``translator.py`` is edited by ``core.patch`` to append this
class. Once installed, the EXE accepts ``--service minimax`` and consumes:

    MINIMAX_BASE_URL  default ``https://api.minimaxi.com/v1``
    MINIMAX_API_KEY   required, no default
    MINIMAX_MODEL     default ``MiniMax-Text-01``

This file is intentionally a **standalone** copy of the class definition
(mirroring ``OpenAITranslator``) so the install script can paste it into
the bundled ``translator.py`` without any imports or top-level helpers.
"""

MINIMAX_TRANSLATOR_SOURCE = '''

# ── MiniMax (added by cli-anything-pdf2zh harness) ─────────────────────
class MiniMaxTranslator(OpenAITranslator):
    # MiniMax (MiniMax) is an OpenAI-compatible chat-completions API.
    # This class is appended to the bundled translator.py by the harness
    # patch (idempotent). It mirrors OpenAITranslator and uses the same
    # prompt and cache plumbing.
    name = "minimax"
    envs = {
        "MINIMAX_BASE_URL": "https://api.minimaxi.com/v1",
        "MINIMAX_API_KEY":  None,
        "MINIMAX_MODEL":    "MiniMax-Text-01",
    }
    CustomPrompt = True

    def __init__(
        self, lang_in, lang_out, model, envs=None, prompt=None, ignore_cache=False
    ):
        self.set_envs(envs)
        if not model:
            model = self.envs["MINIMAX_MODEL"]
        base_url = self.envs["MINIMAX_BASE_URL"]
        api_key = self.envs["MINIMAX_API_KEY"]
        if not api_key:
            raise ValueError(
                "MINIMAX_API_KEY is not set. Run: "
                "cli-anything-pdf2zh config set-key minimax MINIMAX_API_KEY <key>"
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
# ── end MiniMax translator ─────────────────────────────────────────────
'''


# Lines that the install script appends to the ``yadt_main`` translator
# registration block in the bundled ``pdf2zh.py``.
MINIMAX_REGISTRATION_LINES = '''    MiniMaxTranslator,'''  # to be inserted into the import list
MINIMAX_REGISTRATION_BLOCK = '''        MiniMaxTranslator,'''  # to be inserted into the list-comprehension


# Lightweight marker that the install script greps for to determine
# whether the class has already been added.
MINIMAX_CLASS_MARKER = "class MiniMaxTranslator(OpenAITranslator):"
MINIMAX_NAME_MARKER = 'name = "minimax"'
