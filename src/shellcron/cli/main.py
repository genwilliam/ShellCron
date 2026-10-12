"""ShellCron CLI — Typer application and command registration."""

from pathlib import Path

import typer

from shellcron import __version__

app = typer.Typer(
    name="shcron",
    help="Cron-like task scheduler — manage scheduled tasks from the terminal.",
    no_args_is_help=True,
    add_completion=False,
)


# ── Version callback ────────────────────────────────────────────

def _version_callback(value: bool):
    if value:
        typer.echo(f"shcron v{__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False, "--version", "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
):
    pass


# ── Import and register commands ────────────────────────────────

from shellcron.cli.commands.service import service_app
from shellcron.cli.commands.ls import ls_cmd
from shellcron.cli.commands.task import task_app
from shellcron.cli.commands.logs import logs_cmd
from shellcron.cli.commands.run_cmd import run_cmd
from shellcron.cli.commands.config import config_app
from shellcron.cli.commands.web import web_cmd
from shellcron.cli.commands.doctor import doctor_cmd

app.add_typer(service_app, name="service", help="Manage the daemon service.")
app.command(name="ls")(ls_cmd)
app.add_typer(task_app, name="task", help="Manage tasks.")
app.command(name="logs")(logs_cmd)
app.command(name="run")(run_cmd)
app.add_typer(config_app, name="config", help="Manage configuration.")
app.command(name="web")(web_cmd)
app.command(name="doctor")(doctor_cmd)

# For direct CLI use without sub-typer
from shellcron.cli.commands.service import install_cmd, uninstall_cmd, start_cmd, stop_cmd, restart_cmd, status_cmd

app.command(name="install")(install_cmd)
app.command(name="uninstall")(uninstall_cmd)
app.command(name="start")(start_cmd)
app.command(name="stop")(stop_cmd)
app.command(name="restart")(restart_cmd)
app.command(name="status")(status_cmd)
