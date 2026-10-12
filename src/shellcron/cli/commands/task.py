"""shcron task — task management commands."""

from typing import Optional

import typer

from shellcron.cli.client import (
    list_tasks, get_task, create_task, update_task,
    delete_task, toggle_task, DaemonNotRunning,
)
from shellcron.cli.output import green, red, yellow, cyan, bold

task_app = typer.Typer(help="Manage tasks.", no_args_is_help=True)


def _resolve_id(name_or_id: str) -> int:
    """Resolve a task name or ID to an integer ID."""
    try:
        return int(name_or_id)
    except ValueError:
        tasks = list_tasks()
        for t in tasks:
            if t.get("name", "").lower() == name_or_id.lower():
                return t["id"]
        raise typer.BadParameter(f"Task not found: {name_or_id}")


def _prompt(text: str, default: str = "") -> str:
    """Wrapper for typer.prompt."""
    if default:
        return typer.prompt(text, default=default)
    return typer.prompt(text)


# ── Task Add ────────────────────────────────────────────────────

def _interactive_add():
    """Interactive task creation."""
    typer.echo(bold("Creating a new task"))
    typer.echo("─" * 30)

    name = typer.prompt("Task name")
    schedule_type = typer.prompt(
        "Schedule type", type=typer.Choice(["interval", "cron", "fixed_time"]),
        default="interval",
    )

    if schedule_type == "interval":
        days = typer.prompt("Interval (days)", type=float, default=1.0)
        schedule_config = {"days": days}
    elif schedule_type == "cron":
        expr = typer.prompt("Cron expression", default="0 0 * * *")
        schedule_config = {"expr": expr}
    else:
        time_str = typer.prompt("Time (HH:MM)", default="00:00")
        schedule_config = {"time": time_str}

    scripts_input = typer.prompt("Script paths (comma-separated)", default="")
    scripts = [s.strip() for s in scripts_input.split(",") if s.strip()]

    script_args_input = typer.prompt("Script arguments (optional)", default="")
    if script_args_input.strip():
        schedule_config["script_args"] = [
            a.strip() for a in script_args_input.split() if a.strip()
        ]

    misfire = typer.prompt(
        "Misfire policy (skip/catchup)", type=typer.Choice(["skip", "catchup"]),
        default="skip",
    )
    schedule_config["misfire_policy"] = misfire

    enabled = typer.confirm("Enable task?", default=True)

    data = {
        "name": name,
        "schedule_type": schedule_type,
        "schedule_config": schedule_config,
        "scripts": scripts,
        "enabled": enabled,
    }
    return data


@task_app.command(name="add")
def task_add(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Task name"),
    schedule: Optional[str] = typer.Option(None, "--schedule", "-s",
                                            help="Schedule (cron expr or 'every N days')"),
    script: Optional[str] = typer.Option(None, "--script", help="Script path"),
    args: Optional[str] = typer.Option(None, "--args", help="Script arguments"),
    misfire: Optional[str] = typer.Option(None, "--misfire", help="skip or catchup"),
    enabled: Optional[bool] = typer.Option(None, "--enabled/--disabled"),
):
    """Add a new task (interactive or --flags)."""
    if name and script and schedule:
        # Non-interactive mode
        schedule_type = "interval"
        schedule_config = {"days": 1.0}

        if schedule.startswith("every "):
            days = float(schedule.replace("every ", "").replace(" days", "").replace(" day", ""))
            schedule_config = {"days": days}
        elif " " in schedule or schedule.count(" ") >= 4:
            schedule_type = "cron"
            schedule_config = {"expr": schedule}
        else:
            try:
                days = float(schedule)
                schedule_config = {"days": days}
            except ValueError:
                schedule_type = "cron"
                schedule_config = {"expr": schedule}

        if args:
            schedule_config["script_args"] = args.split()
        schedule_config["misfire_policy"] = misfire or "skip"

        data = {
            "name": name,
            "schedule_type": schedule_type,
            "schedule_config": schedule_config,
            "scripts": [script] if script else [],
            "enabled": enabled if enabled is not None else True,
        }
    else:
        data = _interactive_add()

    try:
        result = create_task(data)
        task_id = result.get("id", "?")
        typer.echo(green(f"✓ Task '{data['name']}' created (ID={task_id})"))
    except DaemonNotRunning as e:
        typer.echo(red(str(e)))
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(red(f"✕ Failed: {e}"))
        raise typer.Exit(code=1)


# ── Task Edit ───────────────────────────────────────────────────

@task_app.command(name="edit")
def task_edit(
    task_id: str = typer.Argument(..., help="Task ID or name"),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    enable: Optional[bool] = typer.Option(None, "--enable/--disable"),
):
    """Edit an existing task."""
    tid = _resolve_id(task_id)
    try:
        task = get_task(tid)
    except DaemonNotRunning as e:
        typer.echo(red(str(e)))
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(red(f"Error: {e}"))
        raise typer.Exit(code=1)

    data = {}
    if name:
        data["name"] = name

    if enable is not None:
        if enable != task.get("enabled"):
            toggle_task(tid)
            typer.echo(
                green(f"✓ Task {tid} enabled") if enable
                else yellow(f"○ Task {tid} disabled")
            )
        return

    if data:
        try:
            update_task(tid, data)
            typer.echo(green(f"✓ Task {tid} updated"))
        except Exception as e:
            typer.echo(red(f"✕ Failed: {e}"))
            raise typer.Exit(code=1)


# ── Task Remove ─────────────────────────────────────────────────

@task_app.command(name="remove")
def task_remove(
    task_id: str = typer.Argument(..., help="Task ID or name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Remove a task."""
    tid = _resolve_id(task_id)

    if not force:
        try:
            task = get_task(tid)
            name = task.get("name", f"#{tid}")
            typer.confirm(f"Remove task '{name}' (ID={tid})?", abort=True)
        except Exception:
            pass

    try:
        delete_task(tid)
        typer.echo(green(f"✓ Task {tid} removed"))
    except Exception as e:
        typer.echo(red(f"✕ Failed: {e}"))
        raise typer.Exit(code=1)


# ── Task Enable / Disable ───────────────────────────────────────

@task_app.command(name="enable")
def task_enable(task_id: str = typer.Argument(..., help="Task ID or name")):
    """Enable a task."""
    tid = _resolve_id(task_id)
    try:
        toggle_task(tid)
        # Toggle toggles — ensure it's actually enabled
        task = get_task(tid)
        if task.get("enabled"):
            typer.echo(green(f"✓ Task {tid} enabled"))
        else:
            toggle_task(tid)
            typer.echo(green(f"✓ Task {tid} enabled"))
    except Exception as e:
        typer.echo(red(f"✕ Failed: {e}"))
        raise typer.Exit(code=1)


@task_app.command(name="disable")
def task_disable(task_id: str = typer.Argument(..., help="Task ID or name")):
    """Disable a task."""
    tid = _resolve_id(task_id)
    try:
        task = get_task(tid)
        if task.get("enabled"):
            toggle_task(tid)
        typer.echo(yellow(f"○ Task {tid} disabled"))
    except Exception as e:
        typer.echo(red(f"✕ Failed: {e}"))
        raise typer.Exit(code=1)


# ── Task Show ───────────────────────────────────────────────────

@task_app.command(name="show")
def task_show(task_id: str = typer.Argument(..., help="Task ID or name")):
    """Show detailed task info."""
    tid = _resolve_id(task_id)
    try:
        t = get_task(tid)
    except Exception as e:
        typer.echo(red(f"Error: {e}"))
        raise typer.Exit(code=1)

    from shellcron.cli.output import status_symbol, status_text

    typer.echo(bold(f"Task #{t['id']}: {t.get('name', '?')}"))
    typer.echo(f"  Status:     {status_text(t.get('enabled', False), t.get('last_status'))}")
    typer.echo(f"  Schedule:   {t.get('schedule_desc', '?')}")
    typer.echo(f"  Type:       {t.get('schedule_type', '?')}")
    cfg = t.get("schedule_config", {})
    if isinstance(cfg, dict):
        misfire = cfg.get("misfire_policy", "skip")
        args = cfg.get("script_args", [])
        typer.echo(f"  Misfire:    {misfire}")
        if args:
            typer.echo(f"  Args:       {' '.join(args)}")
    typer.echo(f"  Scripts:    {t.get('script_count', 0)}")
    typer.echo(f"  Last run:   {t.get('last_run', '-')}")
    typer.echo(f"  Last stat:  {t.get('last_status', '-')}")
    typer.echo(f"  Next run:   {t.get('next_run', '-')}")
    typer.echo(f"  Success:    {t.get('success_count', 0)}")
    typer.echo(f"  Failed:     {t.get('failed_count', 0)}")
