"""Web UI — Flask + HTMX administration interface."""

import json
import logging
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, jsonify, make_response

from shellcron.daemon.db import (
    get_all_tasks, get_task, get_task_scripts, set_task_scripts,
    get_execution_logs, get_execution_log, get_script_results,
    get_success_count, get_failed_count,
)
from shellcron.daemon.models import (
    SCHEDULE_TYPES, SCHEDULE_INTERVAL, SCHEDULE_CRON, SCHEDULE_FIXED_TIME,
    build_schedule_config,
)
from shellcron.daemon.scheduler import (
    schedule_task, unschedule_task, run_now, get_next_run_time,
)
from shellcron.daemon.executor import is_running
from shellcron.daemon.settings_store import load as load_settings, save as save_settings
from shellcron.web.i18n import t as _tr

logger = logging.getLogger(__name__)

ui = Blueprint("ui", __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/ui/static",
)


# ── Helpers ─────────────────────────────────────────────────────

def _enrich_task(t: dict) -> dict:
    cfg = json.loads(t["schedule_config"]) if isinstance(t["schedule_config"], str) else t.get("schedule_config", {})
    scripts = get_task_scripts(t["id"])
    logs = get_execution_logs(t["id"], limit=1)
    last_status = logs[0]["status"] if logs else None
    last_time = logs[0]["started_at"] if logs else None
    t.update({
        "enabled": bool(t["enabled"]),
        "schedule_config": cfg,
        "script_count": len(scripts),
        "script_paths": [s["script_path"] for s in scripts],
        "last_status": last_status,
        "last_run": last_time,
        "next_run": get_next_run_time(t["id"]),
        "running": is_running(t["id"]),
        "success_count": get_success_count(t["id"]),
        "failed_count": get_failed_count(t["id"]),
        "misfire_policy": cfg.get("misfire_policy", "skip"),
        "script_args": cfg.get("script_args", []),
    })
    return t


def _lang() -> str:
    return load_settings().get("language", "en")


# ── Task list ───────────────────────────────────────────────────

@ui.route("/ui/")
def index():
    tasks_raw = get_all_tasks()
    tasks = [_enrich_task(t) for t in tasks_raw]
    return render_template("tasks.html", tasks=tasks)


@ui.route("/ui/tasks/table")
def task_table():
    tasks_raw = get_all_tasks()
    tasks = [_enrich_task(t) for t in tasks_raw]
    return render_template("_task_table.html", tasks=tasks)


@ui.route("/ui/tasks/summary")
def task_summary():
    tasks_raw = get_all_tasks()
    tasks = [_enrich_task(t) for t in tasks_raw]
    return render_template("_task_summary.html", tasks=tasks)


# ── Task create/edit ────────────────────────────────────────────

@ui.route("/ui/tasks/new")
def task_new():
    return render_template("task_form.html", task=None, schedule_types=SCHEDULE_TYPES)


@ui.route("/ui/tasks/<int:task_id>/edit")
def task_edit(task_id: int):
    t = get_task(task_id)
    if not t:
        return "Task not found", 404
    scripts = get_task_scripts(task_id)
    t["script_paths"] = [s["script_path"] for s in scripts]
    return render_template("task_form.html", task=_enrich_task(t),
                           schedule_types=SCHEDULE_TYPES)


# ── Task actions ────────────────────────────────────────────────

@ui.route("/ui/tasks/<int:task_id>/toggle", methods=["POST"])
def task_toggle(task_id: int):
    """Toggle task enabled state. Returns full <tr> to refresh the entire row."""
    from shellcron.daemon.db import toggle_task as db_toggle
    t = get_task(task_id)
    if not t:
        return "Not found", 404
    new_enabled = not bool(t["enabled"])
    db_toggle(task_id, new_enabled)
    if new_enabled:
        schedule_task(task_id)
    else:
        unschedule_task(task_id)

    enriched = _enrich_task(get_task(task_id))
    html = render_template("_task_row.html", t=enriched)
    if new_enabled:
        toast_msg = "Task enabled"
        toast_type = "success"
    else:
        toast_msg = "Task disabled"
        toast_type = "info"
    resp = make_response(html)
    resp.headers["HX-Trigger"] = json.dumps({"show-toast": {"message": toast_msg, "type": toast_type}})
    return resp


@ui.route("/ui/tasks/<int:task_id>/run", methods=["POST"])
def task_run(task_id: int):
    """Trigger task execution. Returns full <tr> with toast notification."""
    t = get_task(task_id)
    run_now(task_id)
    enriched = _enrich_task(get_task(task_id))
    html = render_template("_task_row.html", t=enriched)
    resp = make_response(html)
    resp.headers["HX-Trigger"] = json.dumps({"show-toast": {"message": "Task triggered", "type": "info"}})
    return resp


@ui.route("/ui/tasks/save", methods=["POST"])
def task_save():
    name = request.form.get("name", "").strip()
    if not name:
        return "Task name required", 400
    schedule_type = request.form.get("schedule_type", "interval")
    enabled = request.form.get("enabled") == "on"
    task_id = request.form.get("task_id", type=int)
    misfire = request.form.get("misfire_policy", "skip")
    if schedule_type == SCHEDULE_INTERVAL:
        try:
            days = float(request.form.get("interval_days", 1))
        except (ValueError, TypeError):
            days = 1.0
        schedule_config = {"days": max(days, 1/1440.0)}
    elif schedule_type == SCHEDULE_CRON:
        expr = request.form.get("cron_expr", "0 0 * * *")
        schedule_config = {"expr": expr}
    elif schedule_type == SCHEDULE_FIXED_TIME:
        time_val = request.form.get("fixed_time", "00:00")
        schedule_config = {"time": time_val}
    else:
        schedule_config = {"days": 1.0}
    schedule_config["misfire_policy"] = misfire
    args_raw = request.form.get("script_args", "").strip()
    if args_raw:
        schedule_config["script_args"] = [a.strip() for a in args_raw.split()]
    scripts_raw = request.form.get("scripts", "").strip()
    scripts = [s.strip() for s in scripts_raw.split("\n") if s.strip()]
    cfg_str = build_schedule_config(schedule_type, schedule_config)
    from shellcron.daemon.db import add_task, update_task
    if task_id:
        update_task(task_id, name, schedule_type, cfg_str, enabled)
        set_task_scripts(task_id, scripts)
        schedule_task(task_id)
    else:
        tid = add_task(name, schedule_type, cfg_str, enabled)
        if scripts:
            set_task_scripts(tid, scripts)
        schedule_task(tid)
    return redirect("/ui/")


@ui.route("/ui/tasks/<int:task_id>/delete", methods=["POST"])
def task_delete(task_id: int):
    from shellcron.daemon.db import delete_task as db_delete
    t = get_task(task_id)
    name = t["name"] if t else f"#{task_id}"
    unschedule_task(task_id)
    db_delete(task_id)
    resp = make_response("")
    resp.headers["HX-Redirect"] = "/ui/"
    resp.headers["HX-Trigger"] = json.dumps({"show-toast": {"message": "Task deleted", "type": "info"}})
    return resp


# ── Logs ────────────────────────────────────────────────────────

@ui.route("/ui/logs")
def logs():
    tasks_raw = get_all_tasks()
    tasks = [_enrich_task(t) for t in tasks_raw]
    return render_template("logs.html", tasks=tasks)


@ui.route("/ui/logs/table")
def logs_table():
    task_id = request.args.get("task_id", type=int)
    limit = request.args.get("limit", 50, type=int)
    tasks_raw = get_all_tasks()
    tasks_map = {t["id"]: t["name"] for t in tasks_raw}
    if task_id:
        # Specific task: fetch up to `limit` logs
        logs_list = get_execution_logs(task_id, limit=limit)
        for l in logs_list:
            l["_task_name"] = tasks_map.get(l["task_id"], f"#{l['task_id']}")
        all_logs = logs_list
    else:
        # All tasks: fetch `limit` logs per task, merge, sort, cap
        all_logs = []
        for t in tasks_raw:
            logs_list = get_execution_logs(t["id"], limit=limit)
            for l in logs_list:
                l["_task_name"] = t["name"]
            all_logs.extend(logs_list)
        all_logs.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        all_logs = all_logs[:limit]
    return render_template("_log_table.html", logs=all_logs, task_id=task_id)


@ui.route("/ui/logs/<int:log_id>")
def log_detail(log_id: int):
    log_entry = get_execution_log(log_id)
    if not log_entry:
        return "Log not found", 404
    results = get_script_results(log_id)
    task = get_task(log_entry["task_id"])
    return render_template("log_detail.html", log=log_entry, results=results,
                           task_name=task["name"] if task else f"#{log_entry['task_id']}")


# ── Settings ────────────────────────────────────────────────────

@ui.route("/ui/settings")
def settings():
    return render_template("settings.html", settings=load_settings())


@ui.route("/ui/settings/save", methods=["POST"])
def settings_save():
    data = {
        "language": request.form.get("language", "en"),
        "log_retention_days": int(request.form.get("log_retention_days", 30)),
        "default_shell": request.form.get("default_shell", ""),
        "notify_email": request.form.get("notify_email") == "on",
        "smtp_server": request.form.get("smtp_server", ""),
        "smtp_port": int(request.form.get("smtp_port", 465)),
        "smtp_username": request.form.get("smtp_username", ""),
        "smtp_password": request.form.get("smtp_password", ""),
        "email_recipient": request.form.get("email_recipient", ""),
    }
    save_settings(data)
    return redirect("/ui/settings")


# ── Registration ────────────────────────────────────────────────

def register_ui(app):
    app.register_blueprint(ui)
    @app.context_processor
    def inject_globals():
        s = load_settings()
        lang = s.get("language", "en")
        return {
            "settings": s,
            "_lang": lang,
            "_t": lambda key: _tr(key, lang),
        }
    logger.info("Web UI registered at /ui/")
