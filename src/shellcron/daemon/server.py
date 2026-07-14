"""Dual-listener server: Unix socket (CLI) + TCP :4399 (Web/curl)."""

import os
import socket
import logging
import threading
from pathlib import Path
import wsgiref.handlers
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
from socketserver import ThreadingMixIn

from flask import Flask

logger = logging.getLogger(__name__)

SOCKET_DIR = Path.home() / ".local" / "run" / "shcron"
SOCKET_PATH = SOCKET_DIR / "shcron.sock"
WEB_PORT = 4399


class ShcronWSGIHandler(WSGIRequestHandler):
    """WSGI handler that works with both TCP and Unix socket client addresses."""

    def get_environ(self):
        # Build base WSGI environ
        env = self.server.base_environ.copy()
        env["SERVER_PROTOCOL"] = self.request_version
        env["REQUEST_METHOD"] = self.command
        env["PATH_INFO"] = self.path
        env["QUERY_STRING"] = ""
        if "?" in self.path:
            env["PATH_INFO"], env["QUERY_STRING"] = self.path.split("?", 1)

        # Headers
        for key, value in self.headers.items():
            key = "HTTP_" + key.upper().replace("-", "_")
            env[key] = value

        # Content type/length
        ct = self.headers.get("content-type", "")
        cl = self.headers.get("content-length", "")
        if ct:
            env["CONTENT_TYPE"] = ct
        if cl:
            env["CONTENT_LENGTH"] = cl

        # Client address
        if isinstance(self.client_address, tuple):
            env["REMOTE_ADDR"] = self.client_address[0]
        else:
            env["REMOTE_ADDR"] = "local"

        # Server
        if isinstance(self.server.server_address, tuple):
            env["SERVER_NAME"] = self.server.server_address[0]
            env["SERVER_PORT"] = str(self.server.server_address[1])
        else:
            env["SERVER_NAME"] = "localhost"
            env["SERVER_PORT"] = "0"

        return env

    def log_message(self, format, *args):
        logger.debug("WSGI: %s", format % args)


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass=ShcronWSGIHandler, app=None, bind_and_activate=True):
        self._app = app
        from socketserver import TCPServer
        TCPServer.__init__(self, server_address, RequestHandlerClass, bind_and_activate)

    def get_app(self):
        return self._app

    def set_app(self, app):
        self._app = app


# ── Unix socket helpers ─────────────────────────────────────────

def _unlink_socket():
    try:
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
    except OSError:
        pass


def _create_unix_server(app: Flask) -> ThreadedWSGIServer:
    """Return a WSGI server bound to a Unix domain socket."""
    _unlink_socket()
    SOCKET_DIR.mkdir(parents=True, exist_ok=True)

    # Create and bind the socket
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(SOCKET_PATH))
    sock.listen(128)
    os.chmod(str(SOCKET_PATH), 0o600)

    # Server with dummy address, no bind
    server = ThreadedWSGIServer(
        ("", 0), app=app, bind_and_activate=False,
    )
    server.socket = sock
    server.server_address = str(SOCKET_PATH)
    # Populate base_environ so WSGIRequestHandler.get_environ works
    server.server_name = "localhost"
    server.server_port = 0
    server.setup_environ()
    return server


# ── TCP server ──────────────────────────────────────────────────

def _create_tcp_server(app: Flask) -> ThreadedWSGIServer:
    """Return a WSGI server bound to 127.0.0.1:4399."""
    return ThreadedWSGIServer(("127.0.0.1", WEB_PORT), app=app)


# ── Public API ──────────────────────────────────────────────────

def run_server(app: Flask):
    """Start both Unix socket and TCP servers.

    Unix socket on main thread; TCP in daemon thread.
    If TCP port is busy, only the Unix socket runs (CLI mode).
    """
    unix_server = _create_unix_server(app)
    logger.info("Unix socket: %s", SOCKET_PATH)

    tcp_server = None
    tcp_thread = None
    try:
        tcp_server = _create_tcp_server(app)
        tcp_thread = threading.Thread(
            target=tcp_server.serve_forever, daemon=True, name="tcp-server",
        )
        tcp_thread.start()
        logger.info("TCP: 127.0.0.1:%d", WEB_PORT)
    except OSError as exc:
        logger.warning("TCP port %d unavailable (%s). CLI-only mode.", WEB_PORT, exc)

    try:
        unix_server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        if tcp_server:
            tcp_server.shutdown()
        _unlink_socket()
