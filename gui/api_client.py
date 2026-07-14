"""HTTP client for ShellCron daemon API."""

import json
import logging
from typing import Optional
from urllib.request import Request, urlopen, URLError
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

BASE_URL = "http://127.0.0.1:4399/api"
TIMEOUT = 5


class DaemonClientError(Exception):
    pass


class DaemonNotReachable(DaemonClientError):
    pass


def _request(method: str, path: str, data: dict = None,
             params: dict = None) -> Optional[dict]:
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + urlencode({k: v for k, v in params.items() if v is not None})

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    req = Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            if raw:
                return json.loads(raw)
            return None
    except URLError as e:
        raise DaemonNotReachable(f"无法连接守护进程: {e.reason}") from e
    except Exception as e:
        raise DaemonClientError(str(e)) from e


def check_health() -> bool:
    try:
        _request("GET", "/health")
        return True
    except DaemonNotReachable:
        return False


# ── Tasks ────────────────────────────────────────────────────────

def get_tasks() -> list:
    return _request("GET", "/tasks") or []


def create_task(name: str, schedule_type: str, schedule_config: dict,
                scripts: list[str], enabled: bool = True) -> dict:
    return _request("POST", "/tasks", data={
        "name": name,
        "schedule_type": schedule_type,
        "schedule_config": schedule_config,
        "scripts": scripts,
        "enabled": enabled,
    })


def update_task(task_id: int, name: str, schedule_type: str,
                schedule_config: dict, scripts: list[str],
                enabled: bool) -> dict:
    return _request("PUT", f"/tasks/{task_id}", data={
        "name": name,
        "schedule_type": schedule_type,
        "schedule_config": schedule_config,
        "scripts": scripts,
        "enabled": enabled,
    })


def delete_task(task_id: int) -> dict:
    return _request("DELETE", f"/tasks/{task_id}")


def toggle_task(task_id: int) -> dict:
    return _request("POST", f"/tasks/{task_id}/toggle")


def run_task(task_id: int) -> dict:
    return _request("POST", f"/tasks/{task_id}/run")


# ── Scripts ──────────────────────────────────────────────────────

def get_scripts(task_id: int) -> list:
    return _request("GET", f"/tasks/{task_id}/scripts") or []


# ── Logs ─────────────────────────────────────────────────────────

def get_logs(task_id: int, limit: int = 50, offset: int = 0) -> list:
    return _request("GET", f"/tasks/{task_id}/logs",
                    params={"limit": limit, "offset": offset}) or []


def get_log_detail(log_id: int) -> dict:
    return _request("GET", f"/logs/{log_id}")


# ── Schedule types ───────────────────────────────────────────────

def get_schedule_types() -> list:
    return _request("GET", "/schedule-types") or []
