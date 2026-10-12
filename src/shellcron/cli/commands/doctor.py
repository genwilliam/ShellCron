"""shcron doctor — system diagnostics."""

import sys
from pathlib import Path

import typer

from shellcron.cli.client import is_daemon_alive, get_daemon_status, list_tasks
from shellcron.cli.output import green, red, yellow, bold, gray
from shellcron.daemon.server import SOCKET_PATH


def doctor_cmd():
    """Run system diagnostics."""
    typer.echo(bold("ShellCron Diagnostics"))
    typer.echo("─" * 40)

    # ── Python ──
    typer.echo(f"  Python:     {sys.version.split()[0]} ({sys.executable})")

    # ── Daemon ──
    alive = is_daemon_alive()
    if alive:
        typer.echo(green("  Daemon:     ● Running"))
    else:
        typer.echo(red("  Daemon:     ✕ Not running"))

    # ── Socket ──
    if SOCKET_PATH.exists():
        typer.echo(green(f"  Socket:     OK ({SOCKET_PATH})"))
    elif alive:
        typer.echo(red(f"  Socket:     ✕ Not found at {SOCKET_PATH}"))
    else:
        typer.echo(yellow(f"  Socket:     - (daemon not running)"))

    # ── Database ──
    db_path = Path.home() / ".local" / "share" / "shellcrond" / "shelld.db"
    if db_path.exists():
        size = db_path.stat().st_size
        typer.echo(green(f"  Database:   OK ({size} bytes)"))
    else:
        typer.echo(red(f"  Database:   ✕ Not found at {db_path}"))

    # ── Port ──
    import socket as sock_mod
    try:
        s = sock_mod.socket(sock_mod.AF_INET, sock_mod.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(("127.0.0.1", 4399))
        s.close()
        if result == 0:
            typer.echo(green("  Port 4399:  OK"))
        else:
            if alive:
                typer.echo(red("  Port 4399:  ✕ Not listening"))
            else:
                typer.echo(yellow("  Port 4399:  - (daemon not running)"))
    except Exception:
        typer.echo(yellow("  Port 4399:  ?"))

    # ── Scheduler / Tasks ──
    if alive:
        try:
            st = get_daemon_status()
            sched = st.get("scheduler", "?")
            sched_str = green(sched) if sched == "running" else red(sched)
            typer.echo(f"  Scheduler:  {sched_str}")

            tasks = list_tasks()
            enabled = sum(1 for t in tasks if t.get("enabled"))
            typer.echo(f"  Tasks:      {len(tasks)} total, {enabled} enabled")
        except Exception as e:
            typer.echo(red(f"  Tasks:      ✕ {e}"))

    # ── Web ──
    if alive:
        typer.echo(green("  Web UI:     http://127.0.0.1:4399/ui/"))
    else:
        typer.echo(yellow("  Web UI:     - (start daemon first)"))

    typer.echo("")
    if not alive:
        typer.echo(yellow("Run 'shcron start' to start the daemon."))
