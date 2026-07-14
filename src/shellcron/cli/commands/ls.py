"""shcron ls — list all tasks with status."""

from datetime import datetime

import typer

from shellcron.cli.client import list_tasks, DaemonNotRunning
from shellcron.cli.output import (
    green, red, yellow, gray, cyan, bold,
    status_symbol, print_table,
)


def ls_cmd():
    """List all tasks with status and next run time."""
    try:
        tasks = list_tasks()
    except DaemonNotRunning as e:
        typer.echo(red(str(e)))
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(red(f"Error: {e}"))
        raise typer.Exit(code=1)

    if not tasks:
        typer.echo(yellow("No tasks. Create one with: shcron task add"))
        return

    headers = ["ID", "Name", "Status", "Last Run", "Last Status", "Next Run"]
    rows = []

    for t in tasks:
        tid = str(t["id"])
        name = t.get("name", "?")

        enabled = t.get("enabled", False)
        last_status = t.get("last_status") or t.get("last_status")
        status_col = (
            green("● Enabled") if enabled and last_status == "success"
            else yellow("● Enabled") if enabled and last_status is None
            else red("✕ Failed") if enabled and last_status == "failed"
            else gray("○ Disabled")
        )

        last_run = t.get("last_run", "")
        if last_run:
            try:
                dt = datetime.fromisoformat(last_run)
                last_run_str = dt.strftime("%m-%d %H:%M")
            except (ValueError, TypeError):
                last_run_str = str(last_run)[:16]
        else:
            last_run_str = gray("-")

        last_status_label = t.get("last_status", "")
        if last_status_label == "success":
            last_status_col = green("Success")
        elif last_status_label == "failed":
            last_status_col = red("Failed")
        elif last_status_label == "running":
            last_status_col = green("Running")
        elif last_status_label:
            last_status_col = yellow(last_status_label)
        else:
            last_status_col = gray("-")

        next_run = t.get("next_run", "")
        if next_run:
            try:
                dt = datetime.fromisoformat(next_run)
                next_run_str = dt.strftime("%m-%d %H:%M")
            except (ValueError, TypeError):
                next_run_str = str(next_run)[:16]
        else:
            next_run_str = gray("-")

        rows.append([
            cyan(tid),
            bold(name),
            status_col,
            last_run_str,
            last_status_col,
            next_run_str,
        ])

    print_table(rows, headers)
    typer.echo("")
    ntasks = len(tasks)
    enabled_count = sum(1 for t in tasks if t.get("enabled"))
    typer.echo(
        gray(f"{ntasks} task(s), {green(str(enabled_count))} enabled, "
             f"{gray(str(ntasks - enabled_count))} disabled")
    )
