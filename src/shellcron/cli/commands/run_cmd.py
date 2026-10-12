"""shcron run — execute a task immediately."""

from typing import Optional

import typer

from shellcron.cli.client import run_task as api_run, list_tasks, DaemonNotRunning
from shellcron.cli.output import green, red, yellow


def run_cmd(
    task_id: str = typer.Argument(..., help="Task ID or name"),
):
    """Execute a task immediately."""
    # Resolve name to ID
    try:
        tid = int(task_id)
    except ValueError:
        tasks = list_tasks()
        tid = None
        for t in tasks:
            if t.get("name", "").lower() == task_id.lower():
                tid = t["id"]
                break
        if tid is None:
            typer.echo(red(f"Task not found: {task_id}"))
            raise typer.Exit(code=1)

    try:
        result = api_run(tid)
        typer.echo(green(f"✓ Task {tid} triggered"))
    except DaemonNotRunning as e:
        typer.echo(red(str(e)))
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(red(f"✕ Failed: {e}"))
        raise typer.Exit(code=1)
