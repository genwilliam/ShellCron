"""Main Tkinter application for ShellCron GUI."""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional
import threading, json
from pathlib import Path

_GUI_STATE = Path.home() / ".config" / "shellcrond" / "gui_state.json"

def _save_state(**kwargs):
    _GUI_STATE.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(_GUI_STATE.read_text()) if _GUI_STATE.exists() else {}
        data.update(kwargs)
        _GUI_STATE.write_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass

def _load_state(key: str, default=None):
    try:
        if _GUI_STATE.exists():
            return json.loads(_GUI_STATE.read_text()).get(key, default)
    except Exception:
        pass
    return default

from gui.api_client import (
    DaemonNotReachable, check_health, get_tasks, create_task,
    update_task, delete_task, toggle_task, run_task,
)
from gui.task_list import TaskListPanel
from gui.task_edit import TaskEditDialog
from gui.log_viewer import LogViewer
from gui.lang import L
from daemon.settings_store import load as load_settings, save as save_settings


class ShellCronApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("ShellCron")
        self.geometry("900x500")
        self.minsize(700, 400)

        self._settings = load_settings()
        self._daemon_ok = False
        self._build_ui()

        # Restore language from settings
        saved_lang = self._settings.get("language", "en")
        if saved_lang != L.current:
            L.toggle()
            if L.current != saved_lang:
                L.toggle()
        self._refresh_ui_text()

        # Restore saved window geometry
        saved_geo = _load_state("main_geometry", "")
        if saved_geo:
            try: self.geometry(saved_geo)
            except Exception: pass

        self._geo_save_id = None
        self.bind("<Configure>", self._on_configure)
        # Close → hide window
        self.protocol("WM_DELETE_WINDOW", lambda: self.iconify())

        self._check_daemon()

    # ── Menu bar ────────────────────────────────────────────
    def _build_ui(self):
        self._build_menubar()

        # Status bar
        self._status_frame = ttk.Frame(self, relief=tk.SUNKEN, padding=(4, 2))
        self._status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self._status_label = ttk.Label(
            self._status_frame, text=L.t("Connecting to daemon..."))
        self._status_label.pack(side=tk.LEFT)

        self._daemon_indicator = ttk.Label(
            self._status_frame, text="●", foreground="#999")
        self._daemon_indicator.pack(side=tk.RIGHT, padx=(0, 4))

        # Main content
        self._main_frame = ttk.Frame(self, padding=8)
        self._main_frame.pack(fill=tk.BOTH, expand=True)

        self._no_daemon_frame = ttk.Frame(self._main_frame)
        self._setup_no_daemon_ui()

        self._task_frame = ttk.Frame(self._main_frame)
        self._task_panel = TaskListPanel(
            self._task_frame,
            on_edit=self._edit_task,
            on_delete=self._delete_task,
            on_run=self._run_task_now,
            on_toggle=self._toggle_task,
            on_refresh=self._refresh_tasks,
            on_logs=self._view_logs,
            on_settings=self._open_settings,
        )
        self._task_panel.pack(fill=tk.BOTH, expand=True)

    def _setup_no_daemon_ui(self):
        for w in self._no_daemon_frame.winfo_children():
            w.destroy()
        ttk.Label(self._no_daemon_frame, text="Starting daemon...",
                  font=("", 14)).pack(pady=20)
        ttk.Button(self._no_daemon_frame, text="Retry",
                   command=self._check_daemon).pack(pady=4)

    def _show_daemon_ui(self, ok: bool):
        self._daemon_ok = ok
        if ok:
            self._no_daemon_frame.pack_forget()
            self._task_frame.pack(fill=tk.BOTH, expand=True)
            self._status_label.configure(text=L.t("Daemon is running"))
            self._daemon_indicator.configure(text="●", foreground="#4CAF50")
            refresh_ms = max(1000, self._settings.get("refresh_interval", 5) * 1000)
            self._task_panel.start_auto_refresh(refresh_ms)
        else:
            self._task_frame.pack_forget()
            self._no_daemon_frame.pack(fill=tk.BOTH, expand=True)
            self._status_label.configure(text=L.t("Daemon not running"))
            self._daemon_indicator.configure(text="●", foreground="#F44336")
            self._setup_no_daemon_ui()

    def _check_daemon(self):
        ok = check_health()
        if not ok:
            self._start_inprocess_daemon()
            return
        self._show_daemon_ui(ok)

    def _start_inprocess_daemon(self):
        """Start Flask + APScheduler as background thread (same process as GUI)."""
        import threading
        def _run():
            from daemon.db import init_db
            from daemon.scheduler import create_scheduler, start, load_all_tasks
            from daemon.api import create_app
            init_db()
            create_scheduler()
            load_all_tasks()
            start()
            app = create_app()
            app.run(host="127.0.0.1", port=4399, debug=False, use_reloader=False)
        self._daemon_thread = threading.Thread(target=_run, daemon=True)
        self._daemon_thread.start()
        self.after(2000, lambda: self._show_daemon_ui(check_health()))

    def _watch_reconnect(self):
        """Repeatedly check daemon health until it comes back."""
        def _try():
            if check_health():
                self._show_daemon_ui(True)
                self._status_label.configure(text=L.t("Daemon is running"))
            else:
                self._status_label.configure(text="Waiting for daemon...")
                self._show_daemon_ui(False)
                self.after(2000, _try)
        self.after(1000, _try)

    def _install_and_start(self):
        # In-process daemon: just start it
        self._start_inprocess_daemon()

    # ── Settings ────────────────────────────────────────────
    def _open_settings(self):
        from gui.settings import SettingsDialog
        SettingsDialog(self, self)
        # Re-read settings after dialog closes
        self._settings = load_settings()
        # Restart auto-refresh with new interval
        if self._daemon_ok:
            self._task_panel.stop_auto_refresh()
            refresh_ms = max(1000, self._settings.get("refresh_interval", 5) * 1000)
            self._task_panel.start_auto_refresh(refresh_ms)

    # ── Language ────────────────────────────────────────────
    def _toggle_lang(self):
        L.toggle()
        self._settings["language"] = L.current
        save_settings(self._settings)
        self._refresh_ui_text()

    def _refresh_ui_text(self):
        self._task_panel.refresh_labels()
        # Rebuild menu
        self._build_menubar()
        if self._daemon_ok:
            self._status_label.configure(text=L.t("Daemon is running"))
        else:
            self._status_label.configure(text=L.t("Daemon not running"))

    def _build_menubar(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label=L.t("Settings"), command=self._open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Quit ShellCron", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

    # ── Tasks ───────────────────────────────────────────────
    def _refresh_tasks(self):
        if not self._daemon_ok:
            return
        try:
            tasks = get_tasks()
            self._task_panel.update_tasks(tasks)
        except DaemonNotReachable:
            self._daemon_ok = False
            self._show_daemon_ui(False)

    def _edit_task(self, task_id: Optional[int]):
        scripts, task_data = [], None
        if task_id is not None:
            try:
                tasks = get_tasks()
                for t in tasks:
                    if t["id"] == task_id:
                        task_data = t
                        break
                if task_data:
                    from gui.api_client import get_scripts
                    raw_scripts = get_scripts(task_id)
                    scripts = [s["script_path"] for s in raw_scripts]
                    task_data["_scripts"] = raw_scripts
            except Exception:
                messagebox.showerror(L.t("Error"), "Failed to load task")
                return

        dialog = TaskEditDialog(self, task_data, scripts)
        result = dialog.result
        if not result:
            return
        try:
            if task_id is None:
                create_task(**result)
            else:
                update_task(task_id, **result)
            self._refresh_tasks()
        except Exception as e:
            messagebox.showerror(L.t("Save Failed"), str(e))

    def _delete_task(self, task_id: int):
        from gui.dialogs import askyesno
        if not askyesno(self, L.t("Confirm Delete"), L.t("Delete task and its logs?")):
            return
        try:
            delete_task(task_id)
            self._refresh_tasks()
        except Exception as e:
            messagebox.showerror(L.t("Delete Failed"), str(e))

    def _toggle_task(self, task_id: int):
        try:
            toggle_task(task_id)
            self._refresh_tasks()
        except Exception as e:
            messagebox.showerror(L.t("Operation Failed"), str(e))

    def _run_task_now(self, task_id: int):
        try:
            resp = run_task(task_id)
            self._refresh_tasks()
            # Wait for execution to finish so we get a complete log
            def _show_logs():
                self._refresh_tasks()
                tasks = get_tasks()
                name = None
                for t in tasks:
                    if t["id"] == task_id: name = t["name"]; break
                LogViewer(self, task_id, name or f"Task #{task_id}")
            self.after(1500, _show_logs)
        except Exception as e:
            messagebox.showerror(L.t("Execution Failed"), str(e))

    def _view_logs(self, task_id: int):
        try:
            tasks = get_tasks()
            name = None
            for t in tasks:
                if t["id"] == task_id: name = t["name"]; break
            LogViewer(self, task_id, name or f"Task #{task_id}")
        except Exception as e:
            messagebox.showerror(L.t("Error"), str(e))

        # Show a status bar message
        if hasattr(self, "_status_label"):
            self._status_label.configure(text="ShellCron running in background")

    # ── Geometry / Shutdown ─────────────────────────────────
    def _on_configure(self, event):
        if event.widget == self:
            if self._geo_save_id:
                self.after_cancel(self._geo_save_id)
            self._geo_save_id = self.after(
                500, lambda: _save_state(main_geometry=self.geometry()))

    def destroy(self):
        self._task_panel.stop_auto_refresh()
        _save_state(main_geometry=self.geometry(), lang=L.current)
        super().destroy()
