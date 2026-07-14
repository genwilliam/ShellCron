#!/usr/bin/env python3
"""ShellCron daemon entry point.

Usage:
    python -m daemon              # start server in foreground
    python -m daemon --daemon     # called by launchd/systemd
    python -m daemon --install    # install as system service
    python -m daemon --uninstall  # remove service + data
"""

import sys
import os
import logging
from pathlib import Path

# Ensure package is importable when run as `python -m daemon`
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR.parent))

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
    """Initialize DB, scheduler, and start Flask server."""
    from daemon.db import init_db
    from daemon.scheduler import create_scheduler, start, load_all_tasks
    from daemon.api import create_app

    logger = logging.getLogger(__name__)

    # Init database
    init_db()
    logger.info("Database initialized")

    # Init scheduler
    create_scheduler()
    load_all_tasks()
    start()
    logger.info("Scheduler started")

    # Start Flask
    app = create_app()
    logger.info("Starting API server on 127.0.0.1:4399")
    app.run(
        host="127.0.0.1",
        port=4399,
        debug=False,
        use_reloader=False,
    )


def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    args = set(sys.argv[1:])

    if "--install" in args:
        from daemon.installer import install
        install()
        return

    if "--uninstall" in args:
        from daemon.installer import uninstall
        uninstall()
        return

    if "--daemon" in args or len(args) == 0:
        start_server()


if __name__ == "__main__":
    main()
