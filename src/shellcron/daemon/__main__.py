#!/usr/bin/env python3
"""Daemon entrypoint: python -m shellcron.daemon

Usage:
    python -m shellcron.daemon              # foreground server
    python -m shellcron.daemon --install    # install as system service
    python -m shellcron.daemon --uninstall  # remove service + data
"""

import sys
import logging
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging():
    log_dir = Path.home() / ".local" / "state" / "shellcrond"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "daemon.log"
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(str(log_file)),
            logging.StreamHandler(sys.stderr),
        ],
    )


def start_server():
    from shellcron.daemon.db import init_db
    from shellcron.daemon.scheduler import create_scheduler, start, load_all_tasks
    from shellcron.daemon.api import create_app
    from shellcron.daemon.server import run_server

    logger = logging.getLogger(__name__)
    init_db()
    logger.info("Database initialized")

    create_scheduler()
    load_all_tasks()
    start()
    logger.info("Scheduler started")

    app = create_app()
    logger.info("Starting daemon (unix socket + tcp :4399)")
    run_server(app)


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    args = set(sys.argv[1:])

    if "--install" in args:
        from shellcron.daemon.installer import install
        install()
        return
    if "--uninstall" in args:
        from shellcron.daemon.installer import uninstall
        uninstall()
        return

    start_server()


if __name__ == "__main__":
    main()
