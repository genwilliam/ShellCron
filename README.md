# ShellCron

Lightweight shell script task scheduler for macOS.

## Features

- Create multiple tasks, each with multiple shell scripts
- Four scheduling modes: interval / cron / fixed time / relative interval
- Background daemon via launchd, survives GUI exit and system reboot
- Manual execution does not affect scheduled plan
- Execution logs with stdout/stderr capture
- Automatic PATH and environment handling for macOS launchd
- Email notifications via SMTP (Gmail supported)

## Quick Start

Build from source:
  cd ShellCron
  uv venv --python 3.11
  uv pip install -r requirements.txt
  python -m gui

Or download dist/ShellCron.dmg.

## Build App

  bash build_dmg.sh

Output: dist/ShellCron.dmg. Drag ShellCron.app to /Applications.

## Components

- GUI (Tkinter): task management, settings
- Daemon: APScheduler + Flask API (starts with app)
- Email: SMTP notification via daemon after each task

## Uninstall

  rm -rf ~/.local/share/shellcrond
  rm -rf ~/.local/state/shellcrond
  rm -f ~/Library/LaunchAgents/com.shellcrond.plist
