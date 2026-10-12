"""APScheduler wrapper for task scheduling."""

import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from shellcron.daemon.models import (
    SCHEDULE_INTERVAL, SCHEDULE_CRON, SCHEDULE_FIXED_TIME,
    SCHEDULE_RELATIVE_INTERVAL, TRIGGER_SCHEDULED, TRIGGER_MANUAL,
)
from shellcron.daemon.db import (
    get_task, get_all_tasks, get_latest_successful_finish,
)
from shellcron.daemon.executor import run_task, is_running, is_relative_interval_due

logger = logging.getLogger(__name__)

# Prefix for APScheduler job IDs
_JOB_PREFIX = "shelld_task_"


def _job_id(task_id: int) -> str:
    return f"{_JOB_PREFIX}{task_id}"


def _recover_interval_trigger(
    config: dict, tid: int,
) -> Optional[IntervalTrigger]:
    """Determine the correct IntervalTrigger start_date for an interval task,
    accounting for misfire recovery.

    On daemon restart, checks if any scheduled runs were missed while the
    daemon was offline. Applies the task's misfire_policy:

    - skip (default):  skip missed runs, start at next theoretical boundary.
    - catchup:         run immediately (10s delay), then resume normal interval.

    Returns an IntervalTrigger with the computed start_date, or None if
    the task has no last_run (first-time scheduling handled by caller).
    """
    days = config.get("days", 1)
    total_seconds = int(days * 86400)
    misfire_policy = config.get("misfire_policy", "skip")

    last_run = get_latest_successful_finish(tid)
    now = datetime.now(timezone.utc)

    if last_run is None:
        # First run — schedule from now + interval
        start = now + timedelta(seconds=total_seconds)
        logger.info("Task %d: first run, scheduling at %s", tid, start.isoformat())
        return IntervalTrigger(seconds=total_seconds, start_date=start)

    expected_next = datetime.fromisoformat(last_run) + timedelta(days=days)

    if now <= expected_next:
        # On schedule — no misfire
        return IntervalTrigger(seconds=total_seconds, start_date=expected_next)

    # ── Misfire detected ────────────────────────────────────────
    elapsed = (now - expected_next).total_seconds()
    missed_count = int(elapsed / total_seconds) + 1

    if misfire_policy == "catchup":
        start = now + timedelta(seconds=10)
        logger.info(
            "Task %d: missed %d run(s), policy=catchup, executing at %s",
            tid, missed_count, start.isoformat(),
        )
        return IntervalTrigger(seconds=total_seconds, start_date=start)

    # policy == skip (default)
    next_cycle = expected_next + timedelta(seconds=total_seconds * missed_count)
    logger.info(
        "Task %d: missed %d run(s), policy=skip, next at %s",
        tid, missed_count, next_cycle.isoformat(),
    )
    return IntervalTrigger(seconds=total_seconds, start_date=next_cycle)


def _parse_schedule(task: dict) -> Optional[dict]:
    """Return APScheduler trigger kwargs based on task schedule config.

    Returns dict with keys 'trigger' and optionally 'args'.

    For interval tasks, applies misfire recovery logic on restart.
    For relative_interval, returns a DateTrigger and reschedules
    after each execution.
    """
    stype = task["schedule_type"]
    config = json.loads(task["schedule_config"])
    tid = task["id"]

    if stype == SCHEDULE_INTERVAL:
        trigger = _recover_interval_trigger(config, tid)
        if trigger:
            return {"trigger": trigger}
        # Fallback (shouldn't reach here)
        days = config.get("days", 1)
        total_seconds = int(days * 86400)
        now = datetime.now(timezone.utc)
        return {
            "trigger": IntervalTrigger(
                seconds=total_seconds,
                start_date=now + timedelta(seconds=total_seconds),
            ),
        }

    elif stype == SCHEDULE_CRON:
        expr = config.get("expr", "0 0 * * *")
        return {
            "trigger": CronTrigger.from_crontab(expr),
        }

    elif stype == SCHEDULE_FIXED_TIME:
        time_str = config.get("time", "00:00")
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return {
            "trigger": CronTrigger(hour=hour, minute=minute),
        }

    elif stype == SCHEDULE_RELATIVE_INTERVAL:
        days = config.get("days", 1)
        due = is_relative_interval_due(tid, days)
        if due:
            run_at = datetime.now(timezone.utc) + timedelta(seconds=30)
        else:
            last = get_latest_successful_finish(tid)
            if last:
                run_at = datetime.fromisoformat(last) + timedelta(days=days)
            else:
                run_at = datetime.now(timezone.utc) + timedelta(seconds=30)
        return {
            "trigger": DateTrigger(run_date=run_at),
        }

    return None


def _execute_wrapper(task_id: int, triggered_by: str = TRIGGER_SCHEDULED):
    """Execute task and, for relative_interval, reschedule the next run.

    This is the APScheduler job callback.  triggered_by distinguishes
    scheduled runs from manual triggers.
    """
    task = get_task(task_id)
    if not task or not task["enabled"]:
        return

    # For relative_interval tasks, we need the days config for rescheduling
    days = None
    if task["schedule_type"] == SCHEDULE_RELATIVE_INTERVAL:
        import json
        cfg = json.loads(task["schedule_config"])
        days = cfg.get("days", 1)

    status = run_task(task_id, triggered_by)

    # After execution, reschedule relative_interval tasks
    if task["schedule_type"] == SCHEDULE_RELATIVE_INTERVAL and days:
        _reschedule_relative(task_id, days)


def _reschedule_relative(task_id: int, days: float):
    """Schedule the next run N days from now for a relative-interval task."""
    scheduler = _get_scheduler()
    if scheduler is None:
        return
    next_run = datetime.now(timezone.utc) + timedelta(days=days)
    trigger = DateTrigger(run_date=next_run)
    try:
        scheduler.reschedule_job(
            _job_id(task_id),
            trigger=trigger,
        )
        logger.info("Rescheduled task %d for %s", task_id, next_run.isoformat())
    except Exception as e:
        logger.error("Failed to reschedule task %d: %s", task_id, e)


_scheduler: Optional[BackgroundScheduler] = None


def _get_scheduler() -> Optional[BackgroundScheduler]:
    return _scheduler


def create_scheduler() -> BackgroundScheduler:
    global _scheduler
    scheduler = BackgroundScheduler(
        daemon=True,
        job_defaults={
            "max_instances": 1,
            "coalesce": False,
        },
    )
    _scheduler = scheduler
    return scheduler


def start():
    if _scheduler and not _scheduler.running:
        _scheduler.start()
        logger.info("Scheduler started")


def shutdown(wait: bool = True):
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=wait)
        logger.info("Scheduler shut down")


def load_all_tasks():
    """Load all enabled tasks from DB into APScheduler."""
    if _scheduler is None:
        logger.error("Scheduler not initialized")
        return
    tasks = get_all_tasks()
    count = 0
    for task in tasks:
        if task["enabled"]:
            try:
                _add_job(task)
                count += 1
            except Exception as e:
                logger.error("Failed to load task %d: %s", task["id"], e)
    logger.info("Loaded %d tasks into scheduler", count)


def schedule_task(task_id: int):
    """Add or update a task's APScheduler job."""
    if _scheduler is None:
        return
    task = get_task(task_id)
    if not task:
        return
    # Remove existing job if any
    unschedule_task(task_id)
    if task["enabled"]:
        _add_job(task)


def unschedule_task(task_id: int):
    """Remove a task's APScheduler job."""
    if _scheduler is None:
        return
    jid = _job_id(task_id)
    try:
        _scheduler.remove_job(jid)
    except Exception:
        pass  # job may not exist


def _add_job(task: dict):
    """Add an APScheduler job for a task."""
    tid = task["id"]
    params = _parse_schedule(task)
    if params is None:
        logger.warning("Unknown schedule type for task %d: %s", tid, task["schedule_type"])
        return

    trigger = params["trigger"]
    jid = _job_id(tid)

    _scheduler.add_job(
        _execute_wrapper,
        trigger=trigger,
        args=[tid],
        id=jid,
        replace_existing=True,
        name=task["name"],
    )
    logger.info("Scheduled task %d (%s) with %s", tid, task["name"], task["schedule_type"])


def run_now(task_id: int):
    """Manually trigger a task (does not affect schedule).
    Always runs regardless of enabled/disabled state.
    """
    import threading
    def _run():
        task = get_task(task_id)
        if not task:
            return
        run_task(task_id, TRIGGER_MANUAL)
    threading.Thread(target=_run, daemon=True).start()


def get_next_run_time(task_id: int) -> Optional[str]:
    """Return the ISO timestamp of the next scheduled run for a task."""
    if _scheduler is None:
        return None
    jid = _job_id(task_id)
    try:
        job = _scheduler.get_job(jid)
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
    except Exception:
        pass
    return None
