"""ctx — the command line.

Hooks are the hot path: they must never raise, never block a session, and never
write to stdout unless they are injecting context.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import typer

from . import spool
from .client import Client, health
from .config import Config, config_path, state_dir

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Shared Context CLI")
spool_app = typer.Typer(help="Local spool management")
app.add_typer(spool_app, name="spool")


@app.command()
def login(
    server: str = typer.Option(None, "--server", "-s", help="Server base URL"),
    token: str = typer.Option(None, "--token", "-t", help="API token"),
) -> None:
    """Point the recorder at a server."""
    cfg = Config.load()
    if server:
        cfg.server_url = server.rstrip("/")
    if token:
        cfg.token = token
    cfg.save()
    typer.echo(f"server : {cfg.server_url}")
    typer.echo(f"config : {config_path()}")
    typer.echo(f"health : {health(cfg) or 'unreachable (recording will spool locally)'}")


@app.command()
def init(
    harness: str = typer.Option("claude-code", "--harness"),
    mode: str = typer.Option("observe", "--mode", help="observe | active"),
    project: Path = typer.Option(Path.cwd(), "--project", "-p", help="Project directory"),
    transcripts: str = typer.Option("none", "--transcripts", help="none | excerpt | full"),
    path_signals: bool = typer.Option(True, "--path-signals/--no-path-signals"),
    restatement: bool = typer.Option(True, "--restatement/--no-restatement"),
) -> None:
    """Install hooks and project instructions. Shows exactly what is captured."""
    if harness != "claude-code":
        raise typer.BadParameter("only --harness claude-code is supported right now")
    if mode not in ("observe", "active"):
        raise typer.BadParameter("mode must be observe or active")

    cfg = Config.load()
    cfg.mode = mode
    cfg.transcripts = transcripts
    cfg.path_signals = path_signals
    cfg.restatement = restatement

    from .install import install_claude_code, install_project_doc

    settings = install_claude_code(mode)
    doc = install_project_doc(project.resolve(), mode)
    cfg.hooks_installed = True
    cfg.save()

    typer.echo(f"hooks     -> {settings}")
    typer.echo(f"project   -> {doc}")
    typer.echo("")
    typer.echo("Capture consent:")
    typer.echo("  session timing, tool counts, tokens ...... on   (aggregate numbers)")
    typer.echo("  first-edit timestamp .................... on   (orientation time)")
    typer.echo(f"  path signals (HMAC only) ................ {'on' if path_signals else 'off'}")
    typer.echo(f"  restatement detection ................... {'on' if restatement else 'off'}  (counts + class only)")
    typer.echo(f"  transcript upload ....................... {transcripts}")
    typer.echo("")
    typer.echo("Nothing blocks a session: hooks fail open and spool locally when offline.")


@app.command()
def uninstall(
    project: Path = typer.Option(Path.cwd(), "--project", "-p"),
) -> None:
    """Remove hooks and project instructions."""
    from .install import uninstall_claude_code, uninstall_project_doc

    settings = uninstall_claude_code()
    removed = uninstall_project_doc(project.resolve())
    cfg = Config.load()
    cfg.hooks_installed = False
    cfg.save()
    typer.echo(f"hooks removed from {settings}" if settings else "no claude settings found")
    for doc in removed:
        typer.echo(f"removed block from {doc}")


@app.command()
def hook(event: str = typer.Argument(..., help="session-start|user-prompt-submit|pre-compact|stop|session-end")) -> None:
    """Entry point invoked by harness hooks. Always exits 0."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        from . import hooks

        cfg = Config.load()
        out = hooks.handle(event, payload, cfg)
        if out:
            typer.echo(out)
    except Exception as exc:  # never break the harness
        print(f"shared-context hook error ({event}): {exc}", file=sys.stderr)
    raise typer.Exit(0)


@spool_app.command("status")
def spool_status() -> None:
    typer.echo(f"queued: {spool.size()}  ({spool.spool_path()})")


@spool_app.command("flush")
def spool_flush() -> None:
    cfg = Config.load()
    sent, remaining = Client(cfg).flush()
    typer.echo(f"sent={sent} remaining={remaining}")


@app.command()
def report(days: int = typer.Option(7, "--days", "-d"), as_json: bool = typer.Option(False, "--json")) -> None:
    """Team-speed metrics from captured sessions."""
    cfg = Config.load()
    data = Client(cfg).get("/v1/report", {"days": days})
    if data is None:
        typer.echo("server unreachable or no data", err=True)
        raise typer.Exit(1)
    if as_json:
        typer.echo(json.dumps(data, indent=2))
        return
    typer.echo(f"Window: last {days} day(s) · sessions: {data.get('session_count', 0)} · "
               f"principals: {data.get('principal_count', 0)}\n")
    orient = data.get("orientation_minutes") or {}
    typer.echo("Orientation time (session start -> first edit)")
    typer.echo(f"  p50 {orient.get('p50', '-')} min · p90 {orient.get('p90', '-')} min · n={orient.get('n', 0)}")
    rd = data.get("rederivation") or {}
    typer.echo("\nRe-derivation (paths re-read across sessions)")
    typer.echo(f"  within-user  {rd.get('within_user_rate', '-')}  ({rd.get('shared_paths', 0)}/{rd.get('paths', 0)} paths)")
    typer.echo(f"  cross-user   {rd.get('cross_user_rate', '-')}  ({rd.get('cross_user_paths', 0)} paths)")
    rs = data.get("restatement") or {}
    typer.echo("\nRestatement (locally detected, count only)")
    typer.echo(f"  total {rs.get('count', 0)} · classes {rs.get('classes', {})}")
    ov = data.get("overlap") or {}
    typer.echo("\nOverlap (same paths read by multiple principals, 48h window)")
    typer.echo(f"  {ov.get('pairs', 0)} path(s) co-touched")
    tk = data.get("tokens") or {}
    typer.echo("\nTokens (secondary / cost constraint)")
    typer.echo(f"  in {tk.get('in', 0):,} · out {tk.get('out', 0):,}")
    ow = data.get("overhead") or {}
    typer.echo("\nContext overhead (explore vs mutate)")
    typer.echo(f"  median {ow.get('median', '-')}")


@app.command()
def doctor() -> None:
    """Check config, server, hooks, and transcript discovery."""
    cfg = Config.load()
    typer.echo(f"config     : {config_path()}")
    typer.echo(f"state      : {state_dir()}")
    typer.echo(f"server     : {cfg.server_url}")
    typer.echo(f"mode       : {cfg.mode}")
    typer.echo(f"principal  : {cfg.principal}")
    typer.echo(f"health     : {health(cfg) or 'unreachable'}")
    typer.echo(f"spool      : {spool.size()} queued")

    settings = Path.home() / ".claude" / "settings.json"
    installed = False
    if settings.exists():
        try:
            hooks = json.loads(settings.read_text()).get("hooks", {})
            installed = any(
                "shared_context.cli hook" in str(h.get("command", "")) or "ctx hook" in str(h.get("command", ""))
                for entries in hooks.values()
                for entry in entries
                for h in entry.get("hooks", [])
            )
        except ValueError:
            installed = False
    typer.echo(f"hooks      : {'installed' if installed else 'not installed'}")
    projects = Path.home() / ".claude" / "projects"
    typer.echo(f"transcripts: {projects if projects.exists() else 'not found'}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Run the ingest + report server."""
    from .server.app import run

    run(host=host, port=port, reload=reload)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
