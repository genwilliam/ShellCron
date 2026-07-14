"""HTTP client over Unix socket — CLI ⇄ Daemon communication."""

import json
import socket
import logging
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

SOCKET_PATH = Path.home() / ".local" / "run" / "shcron" / "shcron.sock"


class ShcronClientError(Exception):
    pass


class DaemonNotRunning(ShcronClientError):
    pass


def _http(method: str, path: str, body: Optional[dict] = None) -> Any:
    """Send an HTTP request to the daemon via Unix socket."""
    if not SOCKET_PATH.exists():
        raise DaemonNotRunning(
            "Daemon is not running. Start it with: shcron start"
        )

    payload = json.dumps(body).encode() if body else b""
    content_len = len(payload)
    content_type = "application/json" if body else ""

    request = (
        f"{method} {path} HTTP/1.1\r\n"
        f"Host: shcron\r\n"
        f"Accept: application/json\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {content_len}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode() + payload

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect(str(SOCKET_PATH))
        sock.sendall(request)

        response = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            response += chunk
    except socket.timeout:
        raise DaemonNotRunning("Connection timed out — daemon may be unresponsive")
    except ConnectionRefusedError:
        raise DaemonNotRunning("Connection refused — daemon may have stopped")
    finally:
        sock.close()

    # Parse HTTP response
    header_end = response.find(b"\r\n\r\n")
    if header_end == -1:
        raise ShcronClientError("Malformed response from daemon")

    status_line = response[:response.find(b"\r\n")].decode()
    headers_raw = response[response.find(b"\r\n") + 2:header_end].decode()
    body_bytes = response[header_end + 4:]

    status_code = int(status_line.split(" ")[1])

    if status_code >= 400:
        detail = body_bytes.decode() if body_bytes else f"HTTP {status_code}"
        raise ShcronClientError(f"Daemon error ({status_code}): {detail}")

    if body_bytes:
        try:
            return json.loads(body_bytes)
        except json.JSONDecodeError:
            return {"_raw": body_bytes.decode()}
    return {}


# ── Convenience wrappers ────────────────────────────────────────

def get(path: str) -> Any:
    return _http("GET", path)


def post(path: str, body: Optional[dict] = None) -> Any:
    return _http("POST", path, body)


def put(path: str, body: dict) -> Any:
    return _http("PUT", path, body)


def delete(path: str) -> Any:
    return _http("DELETE", path)


def is_daemon_alive() -> bool:
    """Check if the daemon is running.

    Tries Unix socket first, then TCP :4399 as fallback.
    """
    # Try Unix socket first
    try:
        resp = _http("GET", "/api/health")
        return isinstance(resp, dict) and resp.get("status") == "ok"
    except (DaemonNotRunning, ShcronClientError, OSError):
        pass

    # Fallback: try TCP health check
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:4399/api/health", timeout=3) as r:
            import json
            data = json.loads(r.read())
            return isinstance(data, dict) and data.get("status") == "ok"
    except Exception:
        return False


# ── Task helpers (for CLI commands) ─────────────────────────────

def list_tasks() -> list:
    result = get("/api/tasks")
    return result if isinstance(result, list) else []


def get_task(task_id: int) -> dict:
    """Get a single task by ID via the list endpoint (no single-task GET)."""
    tasks = list_tasks()
    for t in tasks:
        if t["id"] == task_id:
            return t
    raise ShcronClientError(f"Task #{task_id} not found")


def create_task(data: dict) -> dict:
    return post("/api/tasks", data)


def update_task(task_id: int, data: dict) -> dict:
    return put(f"/api/tasks/{task_id}", data)


def delete_task(task_id: int) -> dict:
    return delete(f"/api/tasks/{task_id}")


def toggle_task(task_id: int) -> dict:
    return post(f"/api/tasks/{task_id}/toggle")


def run_task(task_id: int) -> dict:
    return post(f"/api/tasks/{task_id}/run")


def get_logs(task_id: int, limit: int = 50, offset: int = 0) -> list:
    resp = get(f"/api/tasks/{task_id}/logs?limit={limit}&offset={offset}")
    return resp if isinstance(resp, list) else resp.get("_list", [])


def get_daemon_status() -> dict:
    result = get("/api/daemon/status")
    return result if isinstance(result, dict) else {}
