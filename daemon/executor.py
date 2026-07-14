"""Shell script execution with proper environment handling."""

import subprocess
import os
import pwd
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from daemon.models import STATUS_RUNNING, STATUS_SUCCESS, STATUS_FAILED, STATUS_SKIPPED
from daemon.db import (
    get_task,
    get_task_scripts,
    create_execution_log,
    update_execution_log,
    add_script_result,
    get_script_results,
    get_latest_successful_finish,
)

logger = logging.getLogger(__name__)

# task_id -> bool — whether a task is currently being executed
_running_tasks: dict[int, bool] = {}


def is_running(task_id: int) -> bool:
    return _running_tasks.get(task_id, False)


def _build_env() -> dict:
    """Build execution environment that works in launchd/systemd context.

    launchd provides minimal PATH and no shell init. We explicitly set
    a comprehensive PATH and derive user info from the OS.
    """
    user = os.environ.get("USER", pwd.getpwuid(os.getuid()).pw_name)
    home = str(Path.home())

    base_path = os.environ.get("PATH", "")
    extra_paths = [
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/local/sbin",
        home + "/.pyenv/shims",
        home + "/.asdf/shims",
        home + "/.local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
    # Merge: keep existing PATH contents, add our defaults after
    existing = base_path.split(":") if base_path else []
    all_parts = existing + [p for p in extra_paths if p not in existing]
    path = ":".join(all_parts)

    env = {
        "HOME": home,
        "USER": user,
        "LOGNAME": user,
        "SHELL": os.environ.get("SHELL", "/bin/bash"),
        "PATH": path,
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "TERM": "xterm-256color",
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PWD": home,
    }
    # Preserve useful session variables if present
    for k in ("SSH_AUTH_SOCK", "DBUS_SESSION_BUS_ADDRESS", "DISPLAY", "XDG_RUNTIME_DIR"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def _resolve_shell() -> str:
    """Return the user's login shell path."""
    shell = os.environ.get("SHELL", "")
    if shell and Path(shell).exists():
        return shell
    try:
        return pwd.getpwuid(os.getuid()).pw_shell or "/bin/bash"
    except Exception:
        return "/bin/bash"


def run_single_script(script_path: str, env: dict, cwd: str,
                       timeout: Optional[int] = None,
                       args: Optional[list[str]] = None) -> dict:
    """Execute a single shell script and return result metadata.

    If args is provided, they are passed as arguments to the script.
    Uses login shell so .zshrc/.bash_profile / pyenv / asdf are picked up.
    """
    shell_path = _resolve_shell()
    abs_path = os.path.abspath(os.path.expanduser(script_path))
    started_at = datetime.now(timezone.utc)

    if not os.path.isfile(abs_path):
        finished = datetime.now(timezone.utc)
        return dict(
            return_code=-1, stdout="",
            stderr=f"Script not found: {abs_path}",
            started_at=started_at.isoformat(),
            finished_at=finished.isoformat(),
            duration_ms=0,
        )

    # Build command: shell -l script_path [args...]
    cmd = [shell_path, "-l", abs_path]
    if args:
        cmd.extend(args)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True, text=True, env=env, cwd=cwd,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        finished = datetime.now(timezone.utc)
        dur = int((finished - started_at).total_seconds() * 1000)
        return dict(
            return_code=-1, stdout="",
            stderr=f"Execution timed out after {timeout}s",
            started_at=started_at.isoformat(),
            finished_at=finished.isoformat(), duration_ms=dur,
        )
    except Exception as e:
        finished = datetime.now(timezone.utc)
        return dict(
            return_code=-1, stdout="", stderr=str(e),
            started_at=started_at.isoformat(),
            finished_at=finished.isoformat(), duration_ms=0,
        )

    finished = datetime.now(timezone.utc)
    dur = int((finished - started_at).total_seconds() * 1000)
    return dict(
        return_code=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        started_at=started_at.isoformat(),
        finished_at=finished.isoformat(),
        duration_ms=dur,
    )


def run_task(task_id: int, triggered_by: str = "scheduled") -> str:
    """Execute all scripts for a task in order.

    If any script fails, stop and record failure.
    Returns final status string.
    """
    if _running_tasks.get(task_id):
        logger.warning("Task %d already running, skip", task_id)
        return STATUS_SKIPPED

    task = get_task(task_id)
    if not task:
        logger.error("Task %d not found", task_id)
        return STATUS_FAILED

    scripts = get_task_scripts(task_id)
    if not scripts:
        logger.warning("Task %d has no scripts", task_id)
        return STATUS_FAILED

    _running_tasks[task_id] = True
    log_id = create_execution_log(task_id, triggered_by, STATUS_RUNNING)
    env = _build_env()
    cwd = str(Path.home())
    final_status = STATUS_SUCCESS
    task_start = datetime.now(timezone.utc)
    failed_script = None
    failed_return_code = None

    # Get script arguments from task config
    import json
    script_args = None
    try:
        cfg = json.loads(task.get("schedule_config", "{}"))
        script_args = cfg.get("script_args")
    except (json.JSONDecodeError, TypeError):
        pass

    try:
        for i, script in enumerate(scripts):
            result = run_single_script(script["script_path"], env, cwd, args=script_args)
            add_script_result(
                execution_id=log_id,
                script_path=script["script_path"],
                sort_order=i,
                return_code=result["return_code"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                started_at=result["started_at"],
                finished_at=result["finished_at"],
                duration_ms=result["duration_ms"],
            )
            if result["return_code"] != 0:
                logger.info("Task %d script %s failed (rc=%d)",
                            task_id, script["script_path"], result["return_code"])
                final_status = STATUS_FAILED
                failed_script = script["script_path"]
                failed_return_code = result["return_code"]
                break

        task_duration = int((datetime.now(timezone.utc) - task_start).total_seconds() * 1000)
        update_execution_log(log_id, final_status, task_duration)

    except Exception as e:
        logger.exception("Task %d execution error: %s", task_id, e)
        final_status = STATUS_FAILED
        failed_script = str(e)
        update_execution_log(log_id, STATUS_FAILED)
    finally:
        _running_tasks[task_id] = False

    # Send email with detailed script report
    _elog = logging.getLogger(__name__)
    try:
        from daemon.email_notify import send_alert
        all_results = []
        try:
            all_results = get_script_results(log_id)
        except Exception:
            pass
        _elog.info("email: calling send_alert for %s (status=%s, scripts=%d)",
                    task.get("name","?"), final_status, len(all_results))
        send_alert(
            task_name=task.get("name", f"Task #{task_id}"),
            status=final_status,
            scripts=all_results,
            failed_script=failed_script,
            return_code=failed_return_code,
            started_at=task_start.isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        _elog.info("email: send_alert completed")
    except Exception as e:
        _elog.warning("email: send_alert failed: %s", e)

    return final_status


def is_relative_interval_due(task_id: int, days: int) -> bool:
    """Check whether N days have passed since last successful finish."""
    last = get_latest_successful_finish(task_id)
    if last is None:
        return True
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds()
    return elapsed >= days * 86400
