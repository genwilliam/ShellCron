"""shcron logs — view execution logs."""

import time
from typing import Optional

import typer

from shellcron.cli.client import list_tasks, get_logs, DaemonNotRunning
from shellcron.cli.output import green, red, yellow, cyan, gray, bold


def _resolve_tid(task_id: str, tasks: list) -> Optional[int]:
    """Resolve task ID from string (numeric ID or name)."""
    try:
        return int(task_id)
    except ValueError:
        for t in tasks:
            if t.get("name", "").lower() == task_id.lower():
                return t["id"]
    return None


def logs_cmd(
    task_id: Optional[str] = typer.Argument(None, help="Task ID or name (omit for all tasks)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of log entries"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow new log entries (poll every 3s)"),
):
    """View task execution logs.

    Use --follow/-f to watch logs in real-time (polls daemon every 3 seconds).
    """
    try:
        tasks = list_tasks()
    except DaemonNotRunning as e:
        typer.echo(red(str(e)))
        raise typer.Exit(code=1)

    # Resolve target task IDs
    selected_ids = None
    if task_id:
        tid = _resolve_tid(task_id, tasks)
        if tid is None:
            typer.echo(red(f"Task not found: {task_id}"))
            raise typer.Exit(code=1)
        selected_ids = {tid}

    seen_ids = set()

    def _fetch_and_print():
        nonlocal seen_ids
        count = 0
        for t in tasks:
            tid = t["id"]
            if selected_ids is not None and tid not in selected_ids:
                continue
            try:
                logs = get_logs(tid, limit=limit)
            except Exception:
                continue
            if not logs:
                continue

            name = t.get("name", f"#{tid}")
            printed_header = False

            for log in logs:
                log_id = log.get("id")
                if follow and log_id in seen_ids:
                    continue
                if log_id:
                    seen_ids.add(log_id)

                if not printed_header and follow:
                    printed_header = True

                ts = log.get("started_at", "")[:19] if log.get("started_at") else "?"
                status_val = log.get("status", "?")
                dur = log.get("duration_ms", "")
                dur_str = f" ({dur}ms)" if dur else ""

                if status_val == "success":
                    status_str = green("● Success")
                elif status_val == "failed":
                    status_str = red("✕ Failed")
                elif status_val == "running":
                    status_str = green("▶ Running")
                else:
                    status_str = gray(status_val)

                trigger = log.get("triggered_by", "")
                trigger_str = f" [{trigger}]" if trigger else ""

                if follow:
                    typer.echo(f"{ts} [{name}] {status_str}{trigger_str}{dur_str}")
                else:
                    if count == 0:
                        typer.echo(bold(f"\n[{name}] (ID={tid}):"))
                    typer.echo(f"  {ts}{trigger_str} {status_str}{dur_str}")
                count += 1
        return count

    if follow:
        typer.echo(green("Following logs... (Ctrl+C to stop)"))
        try:
            while True:
                _fetch_and_print()
                time.sleep(3)
        except KeyboardInterrupt:
            typer.echo("\n" + green("Stopped."))
        return

    count = _fetch_and_print()
    if count == 0:
        if task_id:
            typer.echo(yellow("No logs found for this task."))
        else:
            typer.echo(yellow("No logs found."))
