"""Service installer/uninstaller for launchd (macOS) and systemd (Linux).

Uses the project's existing .venv Python — user is responsible for
installing dependencies via `pip install -r requirements.txt`.
"""

import os
import sys
import shutil
import logging
import platform
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_NAME = "shellcrond"
DAEMON_PORT = 4399

# ── Paths ────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent        # ShellCron/daemon/
_PROJECT_ROOT = _SCRIPT_DIR.parent                   # ShellCron/
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"

DATA_DIR = Path.home() / ".local" / "share" / SERVICE_NAME
CONFIG_DIR = Path.home() / ".config" / SERVICE_NAME
LOG_DIR = Path.home() / ".local" / "state" / SERVICE_NAME
BIN_DIR = Path.home() / ".local" / "bin"
WRAPPER_PATH = BIN_DIR / SERVICE_NAME

# macOS specific
LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / f"com.{SERVICE_NAME}.plist"

# Linux specific
SYSTEMD_UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
SYSTEMD_UNIT = SYSTEMD_UNIT_DIR / f"{SERVICE_NAME}.service"


def detect_system() -> str:
    system = platform.system()
    if system == "Darwin":
        return "launchd"
    elif system == "Linux":
        return "systemd"
    return system.lower()


def _resolve_daemon_path() -> str:
    """Return path to the executable to use for the daemon wrapper.

    Inside .app bundle: use the PyInstaller binary with --daemon flag.
    From source: use .venv/bin/python with -m gui --daemon.
    """
    if getattr(sys, "frozen", False):
        # Inside PyInstaller .app
        return str(Path(sys.executable))
    if _VENV_PYTHON.exists():
        return str(_VENV_PYTHON)
    return sys.executable


def _create_wrapper():
    """Create a wrapper that invokes the daemon.

    Inside .app:   ShellCron.app/Contents/MacOS/ShellCron --daemon
    From source:   .venv/bin/python -m gui --daemon
    """
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    daemon_bin = _resolve_daemon_path()
    extra_args = ""
    if not getattr(sys, "frozen", False):
        extra_args = f'export PYTHONPATH="{_PROJECT_ROOT}"'

    if getattr(sys, "frozen", False):
        # Inside .app: the binary already has all imports
        wrapper_content = f'''#!/bin/bash
exec "{daemon_bin}" --daemon "$@"
'''
    else:
        wrapper_content = f'''#!/bin/bash
{extra_args}
exec "{daemon_bin}" -m gui --daemon "$@"
'''
    WRAPPER_PATH.write_text(wrapper_content)
    WRAPPER_PATH.chmod(0o755)
    logger.info("Wrapper script created at %s → %s", WRAPPER_PATH, daemon_bin)


def _remove_wrapper():
    if WRAPPER_PATH.exists():
        WRAPPER_PATH.unlink()
        logger.info("Removed wrapper %s", WRAPPER_PATH)


# ── launchd (macOS) ──────────────────────────────────────────────

def _install_launchd():
    plist_dir = LAUNCHD_PLIST.parent
    plist_dir.mkdir(parents=True, exist_ok=True)

    log_dir = str(LOG_DIR)

    # Determine the executable launchd should run
    if getattr(sys, "frozen", False):
        # Inside .app — point directly to the binary (preserves bundle identity)
        daemon_exe = str(Path(sys.executable))
        args = [daemon_exe, "--daemon"]
    else:
        # From source — use the wrapper script
        args = [str(WRAPPER_PATH)]

    plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{SERVICE_NAME}</string>
    <key>ProgramArguments</key>
    <array>
'''
    for a in args:
        plist_content += f"        <string>{a}</string>\n"
    plist_content += f'''    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>'''
    LAUNCHD_PLIST.write_text(plist_content)
    logger.info("launchd plist created at %s", LAUNCHD_PLIST)

    uid = os.getuid()
    os.system(f"launchctl bootstrap gui/{uid} '{LAUNCHD_PLIST}' 2>/dev/null")
    os.system(f"launchctl kickstart -kp gui/{uid}/com.{SERVICE_NAME} 2>/dev/null")
    logger.info("launchd service bootstrapped")


def _uninstall_launchd():
    uid = os.getuid()
    os.system(f"launchctl bootout gui/{uid}/com.{SERVICE_NAME} 2>/dev/null")
    if LAUNCHD_PLIST.exists():
        LAUNCHD_PLIST.unlink()
        logger.info("Removed plist %s", LAUNCHD_PLIST)


# ── systemd (Linux) ──────────────────────────────────────────────

def _install_systemd():
    SYSTEMD_UNIT_DIR.mkdir(parents=True, exist_ok=True)
    wrapper = str(WRAPPER_PATH)

    unit_content = f'''[Unit]
Description=ShellCron Daemon
After=network.target

[Service]
Type=simple
ExecStart={wrapper}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
'''
    SYSTEMD_UNIT.write_text(unit_content)
    logger.info("systemd unit created at %s", SYSTEMD_UNIT)

    os.system("systemctl --user daemon-reload 2>/dev/null")
    os.system(f"systemctl --user enable {SERVICE_NAME}.service 2>/dev/null")
    os.system(f"systemctl --user start {SERVICE_NAME}.service 2>/dev/null")
    logger.info("systemd service enabled and started")


def _uninstall_systemd():
    os.system(f"systemctl --user stop {SERVICE_NAME}.service 2>/dev/null")
    os.system(f"systemctl --user disable {SERVICE_NAME}.service 2>/dev/null")
    if SYSTEMD_UNIT.exists():
        SYSTEMD_UNIT.unlink()
    os.system("systemctl --user daemon-reload 2>/dev/null")


# ── Public API ───────────────────────────────────────────────────

def install():
    """Check .venv, create wrapper, install system service."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not _VENV_PYTHON.exists():
        logger.warning(
            ".venv not found at %s. "
            "Run: cd %s && uv venv --python 3.11 && uv pip install -r requirements.txt",
            _VENV_PYTHON, _PROJECT_ROOT,
        )

    _create_wrapper()

    system = detect_system()
    if system == "launchd":
        _install_launchd()
    elif system == "systemd":
        _install_systemd()
    else:
        logger.warning("Unsupported system: %s", system)
        return False
    return True


def uninstall():
    """Uninstall the service and remove all data."""
    system = detect_system()
    if system == "launchd":
        _uninstall_launchd()
    elif system == "systemd":
        _uninstall_systemd()

    _remove_wrapper()

    for d in [DATA_DIR, CONFIG_DIR, LOG_DIR]:
        if d.exists():
            shutil.rmtree(str(d), ignore_errors=True)
            logger.info("Removed %s", d)

    logger.info("ShellCron uninstalled")
    return True


def is_installed() -> bool:
    system = detect_system()
    if system == "launchd":
        return LAUNCHD_PLIST.exists()
    elif system == "systemd":
        return SYSTEMD_UNIT.exists()
    return False


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
