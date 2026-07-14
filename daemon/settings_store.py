"""Settings store — reads/writes JSON settings file."""

import json
import os
import platform
from pathlib import Path
from typing import Any

_SETTINGS_PATH = Path.home() / ".config" / "shellcrond" / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "auto_start": False,
    "refresh_interval": 5,
    "default_shell": "",
    "log_retention_days": 30,
    "theme": "system",
    "notify_email": False,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 465,
    "smtp_username": "",
    "smtp_password": "",
    "email_recipient": "",
    "language": "en",
}


def load() -> dict:
    """Load settings from file, merging with defaults."""
    try:
        if _SETTINGS_PATH.exists():
            with open(_SETTINGS_PATH) as f:
                data = json.load(f)
            merged = dict(DEFAULT_SETTINGS)
            merged.update(data)
            return merged
    except Exception:
        pass
    return dict(DEFAULT_SETTINGS)


def save(settings: dict):
    """Persist settings to JSON file."""
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)
    with open(_SETTINGS_PATH, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)


def get(key: str, default=None):
    return load().get(key, default)


def set_key(key: str, value):
    s = load()
    s[key] = value
    save(s)


def detect_shells() -> list[str]:
    """Scan the system for available login shells."""
    shells = set()
    # Common locations
    candidates = [
        "/bin/zsh", "/bin/bash", "/bin/sh", "/bin/dash",
        "/usr/local/bin/fish", "/opt/homebrew/bin/fish",
        "/usr/local/bin/zsh", "/usr/local/bin/bash",
    ]
    for p in candidates:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            shells.add(p)

    # Try reading /etc/shells
    try:
        with open("/etc/shells") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and os.path.isfile(line):
                    shells.add(line)
    except Exception:
        pass

    return sorted(shells)


def detect_system_dark_mode() -> bool:
    """Return True if macOS/iOS system is in dark mode."""
    if platform.system() == "Darwin":
        try:
            import subprocess
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=2,
            )
            return result.stdout.strip() == "Dark"
        except Exception:
            pass
    return False
