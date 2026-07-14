#!/usr/bin/env python3
"""ShellCron entry point.

Usage:
    python -m gui              # start GUI
    python -m gui --daemon     # start daemon only (for launchd)
"""

import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR.parent))


def start_daemon():
    """Start Flask API + APScheduler (no GUI)."""
    # Ensure PATH includes Homebrew (for bundled daemon inside .app)
    import os
    os.environ.setdefault("PATH",
        "/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
    from daemon.db import init_db
    from daemon.scheduler import create_scheduler, start, load_all_tasks
    from daemon.api import create_app
    init_db()
    create_scheduler()
    load_all_tasks()
    start()
    app = create_app()
    app.run(host="127.0.0.1", port=4399, debug=False, use_reloader=False)


def main():
    if "--daemon" in sys.argv:
        start_daemon()
        return
    from gui.app import ShellCronApp
    app = ShellCronApp()
    app.mainloop()


if __name__ == "__main__":
    main()
