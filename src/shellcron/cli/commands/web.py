"""shcron web — open Web UI in browser."""

import webbrowser

import typer

from shellcron.cli.client import is_daemon_alive
from shellcron.cli.commands.service import start_cmd
from shellcron.cli.output import green, red, yellow


def _check_ui_alive(url: str) -> bool:
    """Check if the Web UI is actually serving."""
    try:
        import urllib.request
        resp = urllib.request.urlopen(url, timeout=3)
        return resp.status == 200
    except Exception:
        return False


def _start_daemon_fallback():
    """Fallback: start daemon as a subprocess."""
    import subprocess, sys, time
    typer.echo(yellow("Starting daemon directly..."))
    subprocess.Popen(
        [sys.executable, "-m", "shellcron.daemon"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(10):
        time.sleep(0.5)
        if _check_ui_alive("http://127.0.0.1:4399/ui/"):
            return True
    return False


def web_cmd():
    """Open Web UI in the browser."""
    url = "http://127.0.0.1:4399/ui/"

    # Check if web UI is already up
    if _check_ui_alive(url):
        typer.echo(green(f"Opening {url}"))
        webbrowser.open(url)
        return

    # Daemon might be running but serving old .app version
    if is_daemon_alive():
        typer.echo(red(
            "Daemon is running but Web UI is unavailable.\n"
            "This is likely the old .app bundle daemon.\n"
            "Run:  shcron doctor  (to diagnose)\n"
            "Then: pkill -f ShellCron && shcron start"
        ))
        raise typer.Exit(code=1)

    # Start daemon
    typer.echo(yellow("Daemon is not running. Starting..."))
    try:
        start_cmd()
    except Exception:
        pass

    if _check_ui_alive(url):
        typer.echo(green(f"Opening {url}"))
        webbrowser.open(url)
        return

    # Fallback: try direct start
    if _start_daemon_fallback():
        typer.echo(green(f"Opening {url}"))
        webbrowser.open(url)
        return

    typer.echo(red("Failed to start Web UI. Run 'shcron doctor' for diagnostics."))
    raise typer.Exit(code=1)
