"""shcron config — view, export, import configuration."""

from pathlib import Path

import typer

from shellcron.cli.client import get, DaemonNotRunning
from shellcron.cli.output import green, red, yellow, bold

config_app = typer.Typer(help="Manage configuration.", no_args_is_help=True)


@config_app.command(name="show")
def config_show():
    """Show current configuration."""
    try:
        settings = get("/api/settings")
    except DaemonNotRunning as e:
        typer.echo(red(str(e)))
        raise typer.Exit(code=1)
    except Exception as e:
        # Fallback: read directly
        settings_path = Path.home() / ".config" / "shellcrond" / "settings.json"
        if settings_path.exists():
            import json
            settings = json.loads(settings_path.read_text())
        else:
            typer.echo(red("No settings found"))
            raise typer.Exit(code=1)

    if not isinstance(settings, dict):
        typer.echo(red("Invalid settings format"))
        return

    typer.echo(bold("Configuration:"))
    # Show non-sensitive settings
    keys = ["language", "log_retention_days", "default_shell", "theme",
            "notify_email", "smtp_server", "smtp_port"]
    for key in keys:
        if key in settings:
            val = settings[key]
            typer.echo(f"  {key}: {val}")

    show_credential = typer.confirm("Show email credentials?", default=False)
    if show_credential:
        for key in ["smtp_username", "smtp_password", "email_recipient"]:
            if key in settings:
                typer.echo(f"  {key}: {settings[key]}")


@config_app.command(name="export")
def config_export(
    path: str = typer.Argument("shellcron-config.json", help="Output file path"),
):
    """Export configuration to a JSON file."""
    try:
        result = get("/api/config/export")
    except DaemonNotRunning as e:
        typer.echo(red(str(e)))
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(red(f"Error: {e}"))
        raise typer.Exit(code=1)

    import json
    Path(path).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    typer.echo(green(f"✓ Configuration exported to {path}"))


@config_app.command(name="import")
def config_import(
    path: str = typer.Argument(..., help="JSON file to import"),
):
    """Import configuration from a JSON file."""
    file_path = Path(path)
    if not file_path.exists():
        typer.echo(red(f"File not found: {path}"))
        raise typer.Exit(code=1)

    import json
    try:
        data = json.loads(file_path.read_text())
    except json.JSONDecodeError:
        typer.echo(red("Invalid JSON file"))
        raise typer.Exit(code=1)

    try:
        result = None
        # Use raw HTTP client
        from shellcron.cli.client import _http
        result = _http("POST", "/api/config/import", data)
    except DaemonNotRunning as e:
        typer.echo(red(str(e)))
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(red(f"Error: {e}"))
        raise typer.Exit(code=1)

    typer.echo(green(f"✓ Configuration imported from {path}"))
