"""shcron service — install, start, stop, restart, status."""

import os
import sys
import platform
import subprocess
from pathlib import Path

import typer

from shellcron.cli.client import is_daemon_alive, get_daemon_status
from shellcron.cli.output import green, red, yellow, bold

service_app = typer.Typer(help="Manage the daemon service.", no_args_is_help=True)

SERVICE_NAME = "shellcrond"

# ── Detect system ───────────────────────────────────────────────

def _system() -> str:
    s = platform.system()
    if s == "Darwin":
        return "launchd"
    elif s == "Linux":
        return "systemd"
    return s.lower()


# ── Install ─────────────────────────────────────────────────────

def _install_launchd():
    uid = os.getuid()
    plist_src = Path(__file__).resolve().parents[4] / "packaging" / "macos" / "plist" / f"com.{SERVICE_NAME}.plist"
    plist_dst = Path.home() / "Library" / "LaunchAgents" / f"com.{SERVICE_NAME}.plist"

    plist_dst.parent.mkdir(parents=True, exist_ok=True)

    if plist_src.exists():
        import shutil
        shutil.copy2(str(plist_src), str(plist_dst))
    else:
        # Fallback: generate minimal plist
        daemon_path = shutil.which("shcron") or sys.argv[0] or "shcron"
        plist_content = PLIST_TEMPLATE.format(daemon_path=daemon_path)
        plist_dst.write_text(plist_content)

    typer.echo(green(f"✓ Created {plist_dst}"))
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist_dst)],
        capture_output=True, timeout=10,
    )
    typer.echo(green("✓ Service installed. Run: shcron start"))


def _install_systemd():
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / f"{SERVICE_NAME}.service"

    daemon_path = shutil.which("shcron") or sys.argv[0] or "shcron"
    unit_content = f"""[Unit]
Description=ShellCron Daemon
After=network.target

[Service]
Type=simple
ExecStart={daemon_path} start
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""
    unit_path.write_text(unit_content)
    typer.echo(green(f"✓ Created {unit_path}"))
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=10)
    subprocess.run(["systemctl", "--user", "enable", f"{SERVICE_NAME}.service"],
                   capture_output=True, timeout=10)
    typer.echo(green("✓ Service installed and enabled"))


def install_cmd():
    """Install the daemon as a system service."""
    sys_name = _system()
    typer.echo(f"Detected system: {sys_name}")

    if sys_name == "launchd":
        _install_launchd()
    elif sys_name == "systemd":
        _install_systemd()
    else:
        typer.echo(red(f"Unsupported system: {sys_name}"))
        raise typer.Exit(code=1)


# ── Uninstall ───────────────────────────────────────────────────

def _uninstall_launchd():
    uid = os.getuid()
    plist_dst = Path.home() / "Library" / "LaunchAgents" / f"com.{SERVICE_NAME}.plist"
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/com.{SERVICE_NAME}"],
                   capture_output=True, timeout=10)
    if plist_dst.exists():
        plist_dst.unlink()
        typer.echo(green(f"✓ Removed {plist_dst}"))


def _uninstall_systemd():
    subprocess.run(["systemctl", "--user", "stop", f"{SERVICE_NAME}.service"],
                   capture_output=True, timeout=10)
    subprocess.run(["systemctl", "--user", "disable", f"{SERVICE_NAME}.service"],
                   capture_output=True, timeout=10)
    unit_path = Path.home() / ".config" / "systemd" / "user" / f"{SERVICE_NAME}.service"
    if unit_path.exists():
        unit_path.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=10)
    typer.echo(green("✓ Service removed"))


def uninstall_cmd(
    purge: bool = typer.Option(False, "--purge", help="Also remove all data and logs."),
):
    """Uninstall the daemon service."""
    sys_name = _system()
    try:
        stop_cmd()
    except Exception:
        pass

    if sys_name == "launchd":
        _uninstall_launchd()
    elif sys_name == "systemd":
        _uninstall_systemd()

    # Remove wrapper
    wrapper = Path.home() / ".local" / "bin" / SERVICE_NAME
    if wrapper.exists():
        wrapper.unlink()
        typer.echo(green(f"✓ Removed {wrapper}"))

    if purge:
        import shutil
        for d in ["share", "state", "run"]:
            p = Path.home() / ".local" / d / SERVICE_NAME
            if p.exists():
                shutil.rmtree(str(p))
                typer.echo(green(f"✓ Removed {p}"))

    typer.echo(green("✓ Uninstalled"))


# ── Start ───────────────────────────────────────────────────────

def _start_launchd():
    uid = os.getuid()
    result = subprocess.run(
        ["launchctl", "kickstart", "-kp", f"gui/{uid}/com.{SERVICE_NAME}"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0 and "already" not in result.stderr:
        # Try bootstrap instead
        plist_dst = Path.home() / "Library" / "LaunchAgents" / f"com.{SERVICE_NAME}.plist"
        subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist_dst)],
                       capture_output=True, timeout=10)


def _start_systemd():
    subprocess.run(["systemctl", "--user", "start", f"{SERVICE_NAME}.service"],
                   capture_output=True, timeout=10)


def start_cmd():
    """Start the daemon service."""
    if is_daemon_alive():
        typer.echo(green("✓ Daemon is already running"))
        return

    typer.echo("Starting daemon...")
    import time, subprocess

    # Try launchd/systemd first
    sys_name = _system()
    if sys_name == "launchd":
        _start_launchd()
    elif sys_name == "systemd":
        _start_systemd()

    # Wait briefly for service manager
    for _ in range(5):
        if is_daemon_alive():
            typer.echo(green("✓ Daemon is running"))
            return
        time.sleep(0.5)

    # Fallback: start directly as subprocess
    typer.echo(yellow("Starting daemon directly as subprocess..."))
    proc = subprocess.Popen(
        [sys.executable, "-m", "shellcron.daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for _ in range(10):
        time.sleep(0.5)
        if is_daemon_alive():
            typer.echo(green(f"✓ Daemon is running (PID {proc.pid})"))
            return

    typer.echo(red("✕ Daemon failed to start (check logs)"))
    raise typer.Exit(code=1)


# ── Stop ────────────────────────────────────────────────────────

def stop_cmd():
    """Stop the daemon service."""
    if not is_daemon_alive():
        typer.echo(yellow("Daemon is not running"))
        return

    from shellcron.cli.client import post
    try:
        post("/api/daemon/stop")
        typer.echo(green("✓ Daemon stopped"))
    except Exception as e:
        typer.echo(red(f"✕ Failed to stop daemon: {e}"))
        raise typer.Exit(code=1)


# ── Restart ─────────────────────────────────────────────────────

def restart_cmd():
    """Restart the daemon service."""
    stop_cmd()
    import time
    time.sleep(1)
    start_cmd()


# ── Status ──────────────────────────────────────────────────────

def status_cmd():
    """Show daemon status."""
    alive = is_daemon_alive()
    if not alive:
        typer.echo(red("● Daemon:   Stopped"))
        typer.echo("")
        typer.echo(yellow("Start it with: shcron start"))
        raise typer.Exit(code=1)

    try:
        st = get_daemon_status()
    except Exception as e:
        typer.echo(red(f"● Daemon:   Running (status unavailable: {e})"))
        return

    from shellcron.cli.client import list_tasks
    from shellcron.daemon.server import SOCKET_PATH

    typer.echo(green("● Daemon:   Running"))
    typer.echo(f"  PID:      {st.get('pid', '?')}")
    typer.echo(f"  Uptime:   {st.get('uptime', '?')}")
    typer.echo(f"  Started:  {st.get('started_at', '?')}")
    typer.echo(f"  Socket:   {SOCKET_PATH}")

    sched = st.get('scheduler', '?')
    sched_str = green(sched) if sched == "running" else red(sched)
    typer.echo(f"  Scheduler: {sched_str}")

    # Task summary
    try:
        tasks = list_tasks()
        total = len(tasks)
        enabled = sum(1 for t in tasks if t.get("enabled"))
        running_t = sum(1 for t in tasks if t.get("running"))
        failed_t = sum(1 for t in tasks if t.get("last_status") == "failed")
        typer.echo(f"  Tasks:    {total} total, {enabled} enabled, {running_t} running, {failed_t} failed")
    except Exception:
        typer.echo(f"  Tasks:    {st.get('task_count', '?')} loaded")

    running_count = st.get('running_count', 0)
    if running_count:
        typer.echo(yellow(f"  Running:  {running_count} task(s) in progress"))

    # Web
    import socket
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", 4399))
        s.close()
        typer.echo(green(f"  Web:      http://127.0.0.1:4399/ui/"))
    except Exception:
        pass


# ── Plist template (fallback) ───────────────────────────────────

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{SERVICE_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{daemon_path}</string>
        <string>start</string>
    </array>
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
</plist>"""
