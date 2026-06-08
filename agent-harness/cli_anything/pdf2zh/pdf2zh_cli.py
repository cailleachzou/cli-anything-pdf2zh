"""Main Click CLI for the pdf2zh harness.

Subcommand layout::

    cli-anything-pdf2zh
    ├── info      <pdf>                       # page count, size
    ├── translate <pdf>...                    # one-shot translation
    ├── batch     <dir>                       # directory translation
    ├── services  list|show                   # catalog of services
    ├── config    list|get|set|delete|set-key # ~/.config/PDFMathTranslate
    ├── inspect   <pdf>                       # pymupdf/pdfminer read
    ├── cache     summary|list|clear          # SQLite cache
    ├── patch     status|install|uninstall    # Xiaomi MiMo translator patch
    ├── mcp       --stdio|--sse               # pass-through to EXE --mcp
    └── repl                                   # default when no subcommand

Global flags:
    --json      machine-readable output (no banners, no colours)
    --exe PATH  override pdf2zh.exe path (default: $PDF2ZH_EXE_PATH or auto)
    --quiet     suppress non-essential output
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from cli_anything.pdf2zh import __version__
from cli_anything.pdf2zh.core import cache as cache_mod
from cli_anything.pdf2zh.core import config as config_mod
from cli_anything.pdf2zh.core import inspect as inspect_mod
from cli_anything.pdf2zh.core import patch as patch_mod
from cli_anything.pdf2zh.core import services as services_mod
from cli_anything.pdf2zh.core.translate import (
    Session,
    TranslateOptions,
    load_project,
    save_project,
    translate_directory,
    translate_files,
)
from cli_anything.pdf2zh.utils import pdf2zh_backend as backend
from cli_anything.pdf2zh.utils.repl_skin import ReplSkin


# ── Shared state helpers ────────────────────────────────────────────────


class Ctx:
    """Mutable per-process state shared by all subcommands."""

    def __init__(self) -> None:
        self.session: Optional[Session] = None
        self.skin: Optional[ReplSkin] = None
        self.json_mode: bool = False  # set by the global --json flag


pass_ctx = click.make_pass_decorator(Ctx, ensure=True)


def _want_json(local: bool) -> bool:
    """Resolve the effective JSON mode: a subcommand's local --json wins,
    otherwise fall back to the global --json flag stored in Ctx.json_mode.

    Uses ``click.get_current_context()`` so callers don't have to thread
    ``ctx`` through every signature.
    """
    if local:
        return True
    try:
        cur = click.get_current_context()
    except RuntimeError:
        return False
    while cur is not None:
        obj = cur.obj
        if obj is not None and getattr(obj, "json_mode", False):
            return True
        cur = cur.parent
    return False


def _emit(skin: ReplSkin, payload: Any, *, as_json: bool) -> None:
    """Single output chokepoint: respects --json."""
    if _want_json(as_json):
        click.echo(backend.to_json(payload))
    else:
        if isinstance(payload, dict):
            # Render as a two-column key-value table for compactness
            for k, v in payload.items():
                if isinstance(v, (dict, list)):
                    click.echo(f"  {k}:")
                    click.echo(backend.to_json(v))
                else:
                    click.echo(f"  {k}: {v}")
        else:
            click.echo(str(payload))


# ── Root group ─────────────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.version_option(__version__, "-V", "--version")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output JSON instead of human-readable text (machine-friendly).",
)
@click.option(
    "--exe",
    "exe_path",
    default=None,
    help="Override pdf2zh.exe path (default: $PDF2ZH_EXE_PATH or auto-detect).",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    default=False,
    help="Suppress non-essential output (still prints results).",
)
@click.pass_context
def cli(ctx: click.Context, as_json: bool, exe_path: Optional[str], quiet: bool) -> None:
    """cli-anything-pdf2zh — control the PDFMathTranslate EXE from scripts/agents."""
    # Lazily create the shared Ctx object (so subcommands receive it).
    if ctx.obj is None:
        ctx.obj = Ctx()
    ctx.obj.skin = ReplSkin("pdf2zh", version=__version__)
    ctx.obj.json_mode = bool(as_json)
    if exe_path:
        # Validate eagerly so the user gets a clear error before any work.
        try:
            backend.find_pdf2zh_exe(exe_path)
        except RuntimeError as e:
            if _want_json(as_json):
                click.echo(json.dumps({"error": str(e)}))
            else:
                click.echo(f"  ✗ {e}", err=True)
            sys.exit(2)
    if ctx.invoked_subcommand is None:
        # No subcommand → default to REPL.
        ctx.invoke(repl, exe_path=exe_path)


# ── info ────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("pdf", type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option("--json", "as_json", is_flag=True, default=False, help="JSON output.")
@pass_ctx
def info(ctx: Ctx, pdf: str, as_json: bool) -> None:
    """Show PDF page count, size, and validity."""
    try:
        payload = inspect_mod.inspect_pdf(pdf)
    except FileNotFoundError as e:
        if _want_json(as_json):
            click.echo(json.dumps({"error": "not_found", "path": str(e)}))
        else:
            click.echo(f"  ✗ not found: {e}", err=True)
        sys.exit(1)
    if _want_json(as_json):
        click.echo(backend.to_json(payload))
    else:
        skin = ctx.skin
        skin.info(f"{payload['filename']}  ({payload['size_human']})")
        skin.status("pages", str(payload.get("page_count")))
        skin.status("valid", "yes" if payload["is_valid_pdf"] else "no")
        skin.status("path", payload["path"])


# ── translate ──────────────────────────────────────────────────────────


@cli.command()
@click.argument("pdfs", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output", "output_dir", required=True, help="Output directory.")
@click.option("--lang-in",  default="en", show_default=True, help="Source language code.")
@click.option("--lang-out", default="zh", show_default=True, help="Target language code.")
@click.option("-s", "--service", default="mimo", show_default=True, help="Translator service (e.g. mimo, google, openai).")
@click.option("-t", "--thread", default=4, show_default=True, type=int, help="Worker threads.")
@click.option("--pages", default="", help="Page range, e.g. 1-3,5,7-9.")
@click.option("--babeldoc", is_flag=True, default=False, help="Use the experimental babeldoc backend.")
@click.option("--ignore-cache", is_flag=True, default=False, help="Force re-translation, bypass cache.")
@click.option("--compatible", is_flag=True, default=False, help="Convert output to PDF/A.")
@click.option("--skip-subset-fonts", is_flag=True, default=False, help="Skip font subsetting.")
@click.option("--prompt-file", default=None, type=click.Path(exists=True), help="Path to a prompt template file.")
@click.option("--exe", "exe_path", default=None, help="Override pdf2zh.exe path.")
@click.option("--json", "as_json", is_flag=True, default=False, help="JSON output.")
@pass_ctx
def translate(
    ctx: Ctx,
    pdfs: tuple,
    output_dir: str,
    lang_in: str,
    lang_out: str,
    service: str,
    thread: int,
    pages: str,
    babeldoc: bool,
    ignore_cache: bool,
    compatible: bool,
    skip_subset_fonts: bool,
    prompt_file: Optional[str],
    exe_path: Optional[str],
    as_json: bool,
) -> None:
    """Translate one or more PDF files via the EXE."""
    opts = TranslateOptions(
        lang_in=lang_in,
        lang_out=lang_out,
        service=service,
        thread=thread,
        pages=pages,
        babeldoc=babeldoc,
        ignore_cache=ignore_cache,
        compatible=compatible,
        skip_subset_fonts=skip_subset_fonts,
        prompt=prompt_file or "",
    )
    try:
        result = translate_files(
            list(pdfs),
            output_dir=output_dir,
            options=opts,
            exe_path=exe_path,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        if _want_json(as_json):
            click.echo(json.dumps({"error": str(e)}))
        else:
            click.echo(f"  ✗ {e}", err=True)
        sys.exit(1)

    if _want_json(as_json):
        click.echo(backend.to_json(result))
    else:
        skin = ctx.skin
        if result.get("fallback_used"):
            skin.warning(
                f"{result.get('fallback_from', '?')} failed — "
                f"fell back to {result.get('fallback_to', '?')}"
            )
        if result.get("exit_code", 0) != 0:
            skin.error(f"pdf2zh.exe exited with code {result['exit_code']}")
            skin.status("stderr (tail)", result.get("stderr_tail", "")[-500:])
        if not babeldoc:
            skin.success(
                f"mono: {result.get('mono_pdf')}  "
                f"dual: {result.get('dual_pdf')}"
            )
        else:
            skin.success(
                f"babeldoc mono: {result.get('babeldoc_mono')}  "
                f"dual: {result.get('babeldoc_dual')}  "
                f"({result.get('babeldoc_time')}s)"
            )
        skin.status("duration", f"{result['duration_s']:.2f}s")

    if result.get("exit_code", 0) != 0:
        sys.exit(result["exit_code"])


# ── batch ──────────────────────────────────────────────────────────────


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output", "output_dir", required=True, help="Output directory.")
@click.option("--lang-in",  default="en", show_default=True)
@click.option("--lang-out", default="zh", show_default=True)
@click.option("-s", "--service", default="mimo", show_default=True)
@click.option("-t", "--thread", default=4, show_default=True, type=int)
@click.option("--exe", "exe_path", default=None)
@click.option("--json", "as_json", is_flag=True, default=False, help="JSON output.")
@pass_ctx
def batch(
    ctx: Ctx,
    directory: str,
    output_dir: str,
    lang_in: str,
    lang_out: str,
    service: str,
    thread: int,
    exe_path: Optional[str],
    as_json: bool,
) -> None:
    """Recursively translate every PDF in DIRECTORY."""
    opts = TranslateOptions(
        lang_in=lang_in, lang_out=lang_out,
        service=service, thread=thread,
    )
    try:
        result = translate_directory(
            directory, output_dir=output_dir, options=opts, exe_path=exe_path
        )
    except (FileNotFoundError, NotADirectoryError, ValueError, RuntimeError) as e:
        if _want_json(as_json):
            click.echo(json.dumps({"error": str(e)}))
        else:
            click.echo(f"  ✗ {e}", err=True)
        sys.exit(1)

    if _want_json(as_json):
        click.echo(backend.to_json(result))
    else:
        skin = ctx.skin
        if result.get("fallback_used"):
            skin.warning(
                f"{result.get('fallback_from', '?')} failed — "
                f"fell back to {result.get('fallback_to', '?')}"
            )
        skin.success(f"translated {len(result.get('inputs', []))} files")
        skin.status("output_dir", output_dir)
        skin.status("duration", f"{result['duration_s']:.2f}s")


# ── services ───────────────────────────────────────────────────────────


@cli.group()
def services() -> None:
    """Catalog of translation services."""


@services.command("list")
@click.option("--exe", "exe_path", default=None)
@click.option("--json", "as_json", is_flag=True, default=False)
def services_list(exe_path: Optional[str], as_json: bool) -> None:
    """List all known translation services."""
    catalog = services_mod.list_services(exe_path)
    if _want_json(as_json):
        click.echo(backend.to_json(catalog))
        return
    headers = ("name", "kind", "key", "description")
    rows = [(s["name"], s["kind"], s["key"], s["desc"]) for s in catalog]
    skin = ReplSkin("pdf2zh")
    skin.table(headers, rows)


@services.command("show")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, default=False)
def services_show(name: str, as_json: bool) -> None:
    """Show details for one service."""
    svc = services_mod.describe_service(name)
    if svc is None:
        if _want_json(as_json):
            click.echo(json.dumps({"error": "not_found", "name": name}))
        else:
            click.echo(f"  ✗ unknown service: {name}", err=True)
        sys.exit(1)
    if _want_json(as_json):
        click.echo(backend.to_json(svc))
    else:
        skin = ReplSkin("pdf2zh")
        for k, v in svc.items():
            skin.status(k, str(v))


# ── config ─────────────────────────────────────────────────────────────


@cli.group()
def config() -> None:
    """Read / write ~/.config/PDFMathTranslate/config.json."""


@config.command("list")
@click.option("--json", "as_json", is_flag=True, default=False)
def config_list(as_json: bool) -> None:
    """Dump the full config (or empty {} if no file yet)."""
    data = config_mod.all_entries()
    if _want_json(as_json):
        click.echo(backend.to_json(data))
    else:
        skin = ReplSkin("pdf2zh")
        skin.status("path", str(config_mod.CONFIG_PATH))
        if not data:
            skin.info("(empty config)")
            return
        for k, v in data.items():
            skin.status(k, json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)


@config.command("get")
@click.argument("key")
@click.option("--json", "as_json", is_flag=True, default=False)
def config_get(key: str, as_json: bool) -> None:
    """Read a top-level key (NOT a translator env)."""
    val = config_mod.get(key)
    if _want_json(as_json):
        click.echo(backend.to_json({"key": key, "value": val}))
    else:
        if val is None:
            click.echo(f"  (unset) {key}")
        else:
            click.echo(f"  {key}: {val}")


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a top-level key (e.g. NOTO_FONT_PATH)."""
    config_mod.set_top(key, value)
    click.echo(f"  ✓ {key} = {value}")


@config.command("delete")
@click.argument("key")
def config_delete(key: str) -> None:
    """Delete a top-level key."""
    if config_mod.delete_top(key):
        click.echo(f"  ✓ deleted {key}")
    else:
        click.echo(f"  ✗ key not found: {key}", err=True)
        sys.exit(1)


@config.command("set-key")
@click.argument("translator")
@click.argument("env_key")
@click.argument("env_value")
def config_set_key(translator: str, env_key: str, env_value: str) -> None:
    """Set a single env var on a translator, e.g. ``mimo MIMO_API_KEY ...``."""
    config_mod.set_translator_key(translator, env_key, env_value)
    click.echo(f"  ✓ {translator}.{env_key} set")


@config.command("show-translator")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, default=False)
def config_show_translator(name: str, as_json: bool) -> None:
    """Show envs for one translator (e.g. ``mimo``)."""
    t = config_mod.get_translator(name)
    if t is None:
        if _want_json(as_json):
            click.echo(json.dumps({"error": "not_found", "name": name}))
        else:
            click.echo(f"  ✗ no translator entry for {name!r}", err=True)
        sys.exit(1)
    if _want_json(as_json):
        # Still mask secrets in JSON mode to avoid leaking them via
        # `cli-anything-pdf2zh --json config show-translator` in shell
        # logs or agent transcripts.
        masked_envs = {}
        for k, v in (t.get("envs") or {}).items():
            if ("KEY" in k or "TOKEN" in k or "SECRET" in k) and v:
                masked_envs[k] = "***"
            else:
                masked_envs[k] = v
        click.echo(backend.to_json({"name": t["name"], "envs": masked_envs}))
    else:
        skin = ReplSkin("pdf2zh")
        skin.status("name", t["name"])
        envs = t.get("envs", {}) or {}
        if not envs:
            skin.info("(no envs set)")
        else:
            for k, v in envs.items():
                # Mask values for keys that look like secrets.
                display = "***" if ("KEY" in k or "TOKEN" in k or "SECRET" in k) and v else (v or "(unset)")
                skin.status(k, display)


# ── inspect ────────────────────────────────────────────────────────────


@cli.command()
@click.argument("pdf", type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option("--json", "as_json", is_flag=True, default=False)
@pass_ctx
def inspect(ctx: Ctx, pdf: str, as_json: bool) -> None:
    """Inspect an arbitrary PDF (alias of `info` with extra detail)."""
    payload = inspect_mod.inspect_pdf(pdf)
    if _want_json(as_json):
        click.echo(backend.to_json(payload))
    else:
        skin = ctx.skin
        skin.table(("field", "value"), list(payload.items()))


# ── cache ──────────────────────────────────────────────────────────────


@cli.group()
def cache() -> None:
    """Translation cache (~/.cache/pdf2zh/cache.v1.db)."""


@cache.command("summary")
@click.option("--json", "as_json", is_flag=True, default=False)
def cache_summary(as_json: bool) -> None:
    s = cache_mod.summary()
    if _want_json(as_json):
        click.echo(backend.to_json(s))
    else:
        skin = ReplSkin("pdf2zh")
        skin.status("path", s["path"])
        skin.status("exists", str(s["exists"]))
        skin.status("size", f"{s['size_bytes']} bytes")
        skin.status("rows", str(s["row_count"]))
        if s.get("top_engines"):
            skin.table(
                ("engine", "count"),
                [(e["engine"], e["count"]) for e in s["top_engines"]],
            )


@cache.command("list")
@click.option("--engine", default=None, help="Filter by engine name.")
@click.option("--limit", default=20, show_default=True, type=int)
@click.option("--offset", default=0, show_default=True, type=int)
@click.option("--json", "as_json", is_flag=True, default=False)
def cache_list(engine: Optional[str], limit: int, offset: int, as_json: bool) -> None:
    entries = cache_mod.list_entries(engine=engine, limit=limit, offset=offset)
    if _want_json(as_json):
        click.echo(backend.to_json(entries))
        return
    skin = ReplSkin("pdf2zh")
    if not entries:
        skin.info("(no entries)")
        return
    skin.table(
        ("id", "engine", "original", "translation"),
        [(e["id"], e["engine"], e["original_text"][:50], e["translation"][:50]) for e in entries],
    )


@cache.command("clear")
@click.option("--engine", default=None, help="Only clear entries for this engine.")
@click.option("--json", "as_json", is_flag=True, default=False)
def cache_clear(engine: Optional[str], as_json: bool) -> None:
    res = cache_mod.clear(engine=engine)
    if _want_json(as_json):
        click.echo(backend.to_json(res))
    else:
        skin = ReplSkin("pdf2zh")
        skin.success(f"deleted {res['deleted']} entries from {res['scope']!r} scope")


# ── patch (Xiaomi MiMo translator) ────────────────────────────────────


@cli.group()
def patch() -> None:
    """Install / uninstall the Xiaomi MiMo translator into the bundled EXE."""


@patch.command("status")
@click.option("--exe", "exe_path", default=None)
@click.option("--json", "as_json", is_flag=True, default=False)
def patch_status(exe_path: Optional[str], as_json: bool) -> None:
    s = patch_mod.status(exe_path)
    if _want_json(as_json):
        click.echo(backend.to_json(s))
    else:
        skin = ReplSkin("pdf2zh")
        if "error" in s:
            skin.error(s["error"])
            sys.exit(1)
        skin.status("installed", str(s["installed"]))
        skin.status("exe", s["exe"])
        skin.status("translator.py", f"{s['translator_py']}  exists={s['translator_py_exists']}")
        skin.status("pdf2zh.py", f"{s['pdf2zh_py']}  exists={s['pdf2zh_py_exists']}")


@patch.command("install")
@click.option("--exe", "exe_path", default=None)
@click.option("--no-backup", is_flag=True, default=False, help="Skip writing .harness.bak files.")
@click.option("--json", "as_json", is_flag=True, default=False)
def patch_install(exe_path: Optional[str], no_backup: bool, as_json: bool) -> None:
    try:
        paths = patch_mod.resolve_bundle_paths(exe_path)
        res = patch_mod.install(paths, backup=not no_backup)
    except (FileNotFoundError, RuntimeError) as e:
        if _want_json(as_json):
            click.echo(json.dumps({"error": str(e)}))
        else:
            click.echo(f"  ✗ {e}", err=True)
        sys.exit(1)
    if _want_json(as_json):
        click.echo(backend.to_json(res))
    else:
        skin = ReplSkin("pdf2zh")
        if res.get("installed"):
            skin.success(
                f"Xiaomi MiMo translator installed "
                f"(imports={res['imports_added']}, registrations={res['registrations_added']})"
            )
        else:
            skin.info(f"no-op: {res.get('reason')}")


@patch.command("uninstall")
@click.option("--exe", "exe_path", default=None)
@click.option("--no-restore", is_flag=True, default=False, help="Use surgical removal even if .harness.bak exists.")
@click.option("--json", "as_json", is_flag=True, default=False)
def patch_uninstall(exe_path: Optional[str], no_restore: bool, as_json: bool) -> None:
    try:
        paths = patch_mod.resolve_bundle_paths(exe_path)
        res = patch_mod.uninstall(paths, restore_backup=not no_restore)
    except (FileNotFoundError, RuntimeError) as e:
        if _want_json(as_json):
            click.echo(json.dumps({"error": str(e)}))
        else:
            click.echo(f"  ✗ {e}", err=True)
        sys.exit(1)
    if _want_json(as_json):
        click.echo(backend.to_json(res))
    else:
        skin = ReplSkin("pdf2zh")
        if res.get("uninstalled"):
            skin.success(f"Xiaomi MiMo translator removed ({res.get('method')})")
        else:
            skin.info(f"no-op: {res.get('reason')}")


# ── mcp (passthrough) ────────────────────────────────────────────────


@cli.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.option("--stdio", "use_stdio", is_flag=True, default=True, help="Run MCP server in STDIO mode (default).")
@click.option("--sse",    "use_sse",   is_flag=True, default=False, help="Run MCP server in SSE mode (HTTP).")
@click.option("--exe", "exe_path", default=None)
@click.pass_context
def mcp(ctx: click.Context, use_stdio: bool, use_sse: bool, exe_path: Optional[str]) -> None:
    """Launch the EXE's MCP server (passes any extra args through)."""
    exe = backend.find_pdf2zh_exe(exe_path)
    args = [exe, "--mcp"]
    if use_sse:
        args.append("--sse")
    args.extend(ctx.args)
    # Replace this process with the EXE so signals work correctly
    os.execvp(exe, args)


# ── repl ───────────────────────────────────────────────────────────────


@cli.command()
@click.option("--exe", "exe_path", default=None)
@pass_ctx
def repl(ctx: Ctx, exe_path: Optional[str]) -> None:
    """Interactive REPL (the default when no subcommand is given)."""
    ctx.session = Session()
    skin = ctx.skin
    skin.print_banner()

    # Hint about MiMo
    try:
        s = patch_mod.status(exe_path)
        if not s.get("installed"):
            skin.info(
                "Xiaomi MiMo translator not installed. Run: "
                "cli-anything-pdf2zh patch install"
            )
    except RuntimeError:
        pass

    help_text = _repl_help()
    print(help_text)

    while True:
        try:
            line = input(skin.prompt(
                project_name=ctx.session.current_pdf,
                modified=ctx.session.modified,
            )).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            skin.print_goodbye()
            return
        if not line:
            continue
        if line in ("exit", "quit"):
            skin.print_goodbye()
            return
        if line in ("help", "?"):
            print(help_text)
            continue
        if line == "status":
            click.echo(backend.to_json(ctx.session.to_dict()))
            continue
        if line == "services":
            catalog = services_mod.list_services(exe_path)
            skin.table(
                ("name", "kind", "key", "description"),
                [(s["name"], s["kind"], s["key"], s["desc"]) for s in catalog],
            )
            continue
        if line.startswith("use "):
            service = line.split(None, 1)[1].strip()
            ctx.session.options.service = service
            ctx.session.modified = True
            skin.success(f"service = {service}")
            continue
        if line.startswith("lang "):
            try:
                _, lang_in, lang_out = line.split()
            except ValueError:
                skin.error("usage: lang <in> <out>")
                continue
            ctx.session.options.lang_in = lang_in
            ctx.session.options.lang_out = lang_out
            ctx.session.modified = True
            skin.success(f"lang = {lang_in} -> {lang_out}")
            continue
        if line.startswith("pdf "):
            pdf = line.split(None, 1)[1].strip().strip('"')
            if not Path(pdf).is_file():
                skin.error(f"not found: {pdf}")
                continue
            ctx.session.current_pdf = pdf
            ctx.session.modified = True
            skin.success(f"current_pdf = {pdf}")
            continue
        if line.startswith("out "):
            out = line.split(None, 1)[1].strip().strip('"')
            ctx.session.options.output_dir = out
            ctx.session.modified = True
            skin.success(f"output_dir = {out}")
            continue
        if line == "translate" or line.startswith("translate "):
            if not ctx.session.current_pdf:
                skin.error("no current pdf. Use: pdf <path>")
                continue
            if not ctx.session.options.output_dir:
                skin.error("no output_dir. Use: out <path>")
                continue
            res = translate_files(
                [ctx.session.current_pdf],
                output_dir=ctx.session.options.output_dir,
                options=ctx.session.options,
                exe_path=exe_path,
            )
            if res.get("exit_code", 0) != 0:
                skin.error(f"exit {res['exit_code']}")
            else:
                skin.success(
                    f"mono: {res.get('mono_pdf')}  dual: {res.get('dual_pdf')}"
                )
            ctx.session.modified = False
            continue
        if line == "save":
            if not ctx.session.project_path:
                skin.error("no project path. Use: save <path>")
                continue
            save_project(ctx.session.project_path, ctx.session)
            skin.success(f"saved {ctx.session.project_path}")
            continue
        if line.startswith("save "):
            path = line.split(None, 1)[1].strip()
            save_project(path, ctx.session)
            skin.success(f"saved {path}")
            continue
        if line.startswith("open "):
            path = line.split(None, 1)[1].strip()
            try:
                ctx.session = load_project(path)
                skin.success(f"opened {path}")
            except (FileNotFoundError, ValueError) as e:
                skin.error(str(e))
            continue
        if line == "version":
            try:
                v = backend.version(exe_path)
                skin.status("pdf2zh.exe", v)
            except Exception as e:  # noqa: BLE001
                skin.error(str(e))
            continue
        if line == "patch-install":
            try:
                paths = patch_mod.resolve_bundle_paths(exe_path)
                res = patch_mod.install(paths)
                if res.get("installed"):
                    skin.success("Xiaomi MiMo translator installed")
                else:
                    skin.info(f"no-op: {res.get('reason')}")
            except Exception as e:  # noqa: BLE001
                skin.error(str(e))
            continue
        skin.error(f"unknown command: {line!r}. Type 'help'.")


def _repl_help() -> str:
    return """
  Commands:
    status                 show session state as JSON
    services               list all available translators
    use <service>          set the translator (e.g. use mimo)
    lang <in> <out>        set languages (e.g. lang en zh)
    pdf <path>             set the current input PDF
    out <path>             set the output directory
    translate              run translation on current pdf → out
    save [path]            save session to a project file
    open <path>            load a project file
    patch-install          one-shot install the Xiaomi MiMo translator
    version                show pdf2zh.exe version
    help, ?                this message
    exit, quit             leave the REPL
"""


# ── Default-to-REPL ────────────────────────────────────────────────────


def main() -> int:
    """Console script entry point.

    The default (no subcommand) is handled inside ``cli()`` itself via
    ``invoke_without_command=True``; we just call Click here. ``cli()``
    exits on its own (Click's default standalone behavior), so we wrap it
    in a try/except to convert SystemExit into a clean return code.
    """
    try:
        cli()
    except SystemExit as e:
        # Click raises SystemExit; propagate the code (None → 0).
        return int(e.code) if e.code is not None else 0
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
