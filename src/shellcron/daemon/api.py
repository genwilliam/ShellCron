"""Flask REST API for ShellCron daemon."""

import json
import logging
from flask import Flask, request, jsonify

from shellcron.daemon.models import (
    SCHEDULE_TYPES, TRIGGER_SCHEDULED, TRIGGER_MANUAL,
    build_schedule_config, describe_schedule,
)
from shellcron.daemon.db import (
    init_db, get_all_tasks, get_task, add_task, update_task, delete_task,
    toggle_task, get_task_scripts, set_task_scripts,
    get_execution_logs, get_execution_log, get_script_results,
    get_success_count, get_failed_count,
)
from shellcron.daemon.executor import is_running
from shellcron.daemon.scheduler import (
    schedule_task, unschedule_task, run_now, get_next_run_time, load_all_tasks,
)

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False  # Chinese characters in JSON

    # ── Health ──────────────────────────────────────────────────

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # ── Tasks ───────────────────────────────────────────────────

    @app.route("/api/tasks", methods=["GET"])
    def list_tasks():
        tasks = get_all_tasks()
        result = []
        for t in tasks:
            scripts = get_task_scripts(t["id"])
            next_run = get_next_run_time(t["id"])
            # Latest execution status
            logs = get_execution_logs(t["id"], limit=1)
            last_status = logs[0]["status"] if logs else None
            last_time = logs[0]["started_at"] if logs else None
            sc = get_success_count(t["id"])
            fc = get_failed_count(t["id"])
            cfg = json.loads(t["schedule_config"])

            result.append({
                "id": t["id"],
                "name": t["name"],
                "enabled": bool(t["enabled"]),
                "schedule_type": t["schedule_type"],
                "schedule_config": cfg,
                "schedule_desc": describe_schedule(t["schedule_type"], t["schedule_config"], "en"),
                "script_count": len(scripts),
                "script_args": cfg.get("script_args", []),
                "next_run": next_run,
                "last_status": last_status,
                "last_run": last_time,
                "running": is_running(t["id"]),
                "success_count": sc,
                "failed_count": fc,
            })
        return jsonify(result)

    @app.route("/api/tasks", methods=["POST"])
    def create_task():
        data = request.get_json(force=True)
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "任务名称不能为空"}), 400
        schedule_type = data.get("schedule_type", "")
        if schedule_type not in [s[0] for s in SCHEDULE_TYPES]:
            return jsonify({"error": "无效的调度类型"}), 400
        schedule_config = build_schedule_config(schedule_type, data.get("schedule_config", {}))
        enabled = data.get("enabled", True)
        scripts = data.get("scripts", [])

        task_id = add_task(name, schedule_type, schedule_config, enabled)
        if scripts:
            set_task_scripts(task_id, scripts)

        schedule_task(task_id)
        return jsonify({"id": task_id}), 201

    @app.route("/api/tasks/<int:task_id>", methods=["PUT"])
    def update_task_route(task_id):
        task = get_task(task_id)
        if not task:
            return jsonify({"error": "任务不存在"}), 404
        data = request.get_json(force=True)
        name = data.get("name", task["name"]).strip()
        schedule_type = data.get("schedule_type", task["schedule_type"])
        schedule_config = build_schedule_config(
            schedule_type,
            data.get("schedule_config", json.loads(task["schedule_config"])),
        )
        enabled = data.get("enabled", bool(task["enabled"]))
        scripts = data.get("scripts")

        update_task(task_id, name, schedule_type, schedule_config, enabled)
        if scripts is not None:
            set_task_scripts(task_id, scripts)

        schedule_task(task_id)
        return jsonify({"status": "ok"})

    @app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
    def delete_task_route(task_id):
        task = get_task(task_id)
        if not task:
            return jsonify({"error": "任务不存在"}), 404
        unschedule_task(task_id)
        delete_task(task_id)
        return jsonify({"status": "ok"})

    @app.route("/api/tasks/<int:task_id>/toggle", methods=["POST"])
    def toggle_task_route(task_id):
        task = get_task(task_id)
        if not task:
            return jsonify({"error": "任务不存在"}), 404
        enabled = not bool(task["enabled"])
        toggle_task(task_id, enabled)
        if enabled:
            schedule_task(task_id)
        else:
            unschedule_task(task_id)
        return jsonify({"enabled": enabled})

    @app.route("/api/tasks/<int:task_id>/run", methods=["POST"])
    def run_task_now(task_id):
        task = get_task(task_id)
        if not task:
            return jsonify({"error": "任务不存在"}), 404
        if is_running(task_id):
            return jsonify({"error": "任务正在运行中"}), 409
        run_now(task_id)
        return jsonify({"status": "triggered"})

    # ── Scripts ──────────────────────────────────────────────────

    @app.route("/api/tasks/<int:task_id>/scripts", methods=["GET"])
    def list_scripts(task_id):
        scripts = get_task_scripts(task_id)
        return jsonify(scripts)

    # ── Logs ─────────────────────────────────────────────────────

    @app.route("/api/tasks/<int:task_id>/logs", methods=["GET"])
    def list_logs(task_id):
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        logs = get_execution_logs(task_id, limit, offset)
        return jsonify(logs)

    @app.route("/api/logs/<int:log_id>", methods=["GET"])
    def get_log(log_id):
        log = get_execution_log(log_id)
        if not log:
            return jsonify({"error": "日志不存在"}), 404
        results = get_script_results(log_id)
        return jsonify({"log": log, "results": results})

    # ── Info ─────────────────────────────────────────────────────

    @app.route("/api/schedule-types", methods=["GET"])
    def schedule_types():
        return jsonify([
            {"key": k, "label": l} for k, l in SCHEDULE_TYPES
        ])

    # ── Settings ──────────────────────────────────────────────────

    @app.route("/api/settings", methods=["GET"])
    def get_settings():
        from shellcron.daemon.settings_store import load
        return jsonify(load())

    @app.route("/api/settings", methods=["PUT"])
    def update_settings():
        from shellcron.daemon.settings_store import save
        data = request.get_json(force=True)
        save(data)
        return jsonify({"status": "ok"})

    @app.route("/api/shells", methods=["GET"])
    def list_shells():
        from shellcron.daemon.settings_store import detect_shells
        return jsonify(detect_shells())

    # ── Daemon status ────────────────────────────────────────────

    @app.route("/api/daemon/status", methods=["GET"])
    def daemon_status():
        import os, time
        from datetime import datetime, timezone
        from shellcron.daemon.scheduler import _get_scheduler
        from shellcron.daemon.executor import _running_tasks
        from shellcron.daemon.db import get_all_tasks

        sched = _get_scheduler()
        scheduler_ok = sched is not None and sched.running
        tasks = get_all_tasks()
        pid = os.getpid()
        started = "?"
        uptime = "?"
        try:
            import subprocess as sp
            r = sp.run(["ps", "-p", str(pid), "-o", "lstart="],
                       capture_output=True, text=True, timeout=3)
            raw = r.stdout.strip()
            if raw:
                dt = datetime.strptime(raw, "%a %b %d %H:%M:%S %Y")
                started = dt.replace(tzinfo=timezone.utc).isoformat()
                elapsed = time.time() - dt.timestamp()
                dys = int(elapsed // 86400)
                hrs = int((elapsed % 86400) // 3600)
                uptime = f"{dys}d {hrs}h" if dys else f"{hrs}h"
        except Exception:
            pass

        return jsonify({
            "status": "running",
            "pid": pid,
            "started_at": started,
            "uptime": uptime,
            "scheduler": "running" if scheduler_ok else "stopped",
            "task_count": len(tasks),
            "running_count": len([t for t in _running_tasks if _running_tasks[t]]),
        })

    @app.route("/api/daemon/restart", methods=["POST"])
    def daemon_restart():
        """Restart the daemon by asking launchd to kickstart."""
        import subprocess as sp, os
        uid = os.getuid()
        sp.run(["launchctl", "kickstart", "-kp", f"gui/{uid}/com.shellcrond"],
               capture_output=True, timeout=10)
        return jsonify({"status": "restarting"})

    @app.route("/api/daemon/stop", methods=["POST"])
    def daemon_stop():
        """Stop the daemon by booting out of launchd."""
        import subprocess as sp, os
        from shellcron.daemon.scheduler import shutdown as sched_shutdown
        sched_shutdown(wait=False)
        uid = os.getuid()
        sp.run(["launchctl", "bootout", f"gui/{uid}/com.shellcrond"],
               capture_output=True, timeout=10)
        return jsonify({"status": "stopped"})

    # ── Logs management ──────────────────────────────────────────

    @app.route("/api/logs/dir", methods=["GET"])
    def logs_dir():
        from pathlib import Path
        return jsonify({"path": str(Path.home() / ".local" / "state" / "shellcrond")})

    @app.route("/api/logs/clear", methods=["POST"])
    def clear_logs():
        from shellcron.daemon.db import cleanup_old_logs
        from datetime import datetime, timedelta, timezone
        from pathlib import Path
        import shutil
        data = request.get_json(force=True)
        days = data.get("days", 0)
        if days and days > 0:
            before = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            cleanup_old_logs(before)
        else:
            # Delete all from DB
            cleanup_old_logs(datetime.now(timezone.utc).isoformat())
        # Also clean up log files in state directory
        log_dir = Path.home() / ".local" / "state" / "shellcrond"
        if log_dir.exists():
            for f in log_dir.iterdir():
                if f.is_file() and f.suffix in ('.log', '.err'):
                    try:
                        f.unlink()
                    except Exception:
                        pass
        return jsonify({"status": "ok"})

    # ── Config export/import ─────────────────────────────────────

    @app.route("/api/config/export", methods=["GET"])
    def export_config():
        from shellcron.daemon.settings_store import load as load_settings
        from shellcron.daemon.db import get_all_tasks, get_task_scripts
        tasks = get_all_tasks()
        task_list = []
        for t in tasks:
            scripts = get_task_scripts(t["id"])
            task_list.append({
                "name": t["name"],
                "enabled": bool(t["enabled"]),
                "schedule_type": t["schedule_type"],
                "schedule_config": json.loads(t["schedule_config"]),
                "scripts": [s["script_path"] for s in scripts],
            })
        return jsonify({
            "version": 1,
            "exported_at": __import__("datetime").datetime.now().isoformat(),
            "settings": load_settings(),
            "tasks": task_list,
        })

    @app.route("/api/config/import", methods=["POST"])
    def import_config():
        from shellcron.daemon.settings_store import save as save_settings
        from shellcron.daemon.db import add_task, set_task_scripts
        from shellcron.daemon.scheduler import schedule_task
        data = request.get_json(force=True)

        # Import settings
        if "settings" in data:
            save_settings(data["settings"])

        # Import tasks
        if "tasks" in data:
            for t in data["tasks"]:
                cfg = build_schedule_config(t.get("schedule_type", "interval"),
                                           t.get("schedule_config", {}))
                tid = add_task(
                    name=t.get("name", "Imported"),
                    schedule_type=t.get("schedule_type", "interval"),
                    schedule_config=cfg,
                    enabled=t.get("enabled", True),
                )
                scripts = t.get("scripts", [])
                if scripts:
                    set_task_scripts(tid, scripts)
                schedule_task(tid)

        return jsonify({"status": "ok"})

    # ── Web UI ──────────────────────────────────────────────────

    try:
        from shellcron.web.server import register_ui
        register_ui(app)
    except Exception as exc:
        logger.warning("Web UI not available: %s", exc)

    return app
