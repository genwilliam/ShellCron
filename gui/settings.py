"""Settings dialog with notebook tabs."""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess, platform, json, os
from pathlib import Path
from datetime import datetime, timezone

from daemon.settings_store import load, save, detect_shells, detect_system_dark_mode
from gui.lang import L
from gui.api_client import _request, DaemonNotReachable


_SETTINGS = {}


def get_setting(key: str, default=None):
    global _SETTINGS
    if not _SETTINGS:
        _SETTINGS = load()
    return _SETTINGS.get(key, default)


def refresh_settings():
    global _SETTINGS
    _SETTINGS = load()


def apply_auto_start(enabled: bool):
    try:
        if enabled:
            from daemon.installer import install
            install()
            # Show macOS notification
            try:
                subprocess.run(["osascript", "-e",
                    'display notification "ShellCron will start automatically on login" '
                    'with title "Auto-start enabled"'],
                    capture_output=True, timeout=5)
            except Exception:
                pass
        else:
            uid = os.getuid()
            subprocess.run(
                ["launchctl", "bootout", f"gui/{uid}/com.shellcrond"],
                capture_output=True, timeout=5,
            )
            plist = Path.home() / "Library" / "LaunchAgents" / "com.shellcrond.plist"
            if plist.exists():
                plist.unlink()
            try:
                subprocess.run(["osascript", "-e",
                    'display notification "ShellCron auto-start disabled" '
                    'with title "Auto-start disabled"'],
                    capture_output=True, timeout=5)
            except Exception:
                pass
    except Exception:
        pass


class SettingsDialog(tk.Toplevel):
    """Modal settings dialog."""

    def __init__(self, parent, app_ref):
        super().__init__(parent)
        self.withdraw()  # hide immediately, position before show
        self.title("Settings")
        self.geometry("750x550")
        self.transient(parent)
        self.resizable(False, False)
        self._app = app_ref
        self._settings = load()
        self._build_ui()
        self._load_values()
        self.update_idletasks()
        # Center on parent window
        try:
            px, py = parent.winfo_x(), parent.winfo_y()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            w, h = self.winfo_width(), self.winfo_height()
            self.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//2}")
        except Exception:
            pass
        self.deiconify()
        self.wait_window()

    def _build_ui(self):
        nb = ttk.Notebook(self, padding=4)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._general = ttk.Frame(nb)
        self._shell = ttk.Frame(nb)
        self._logs = ttk.Frame(nb)
        self._notif = ttk.Frame(nb)
        self._service = ttk.Frame(nb)
        self._data = ttk.Frame(nb)

        nb.add(self._general, text=L.t("General"))
        nb.add(self._shell, text=L.t("Shell"))
        nb.add(self._logs, text=L.t("Logs"))
        nb.add(self._notif, text=L.t("Notifications"))
        nb.add(self._service, text=L.t("Service"))
        nb.add(self._data, text=L.t("Data"))

        self._build_general()
        self._build_shell()
        self._build_logs()
        self._build_notif()
        self._build_service()
        self._build_data()

        btnf = ttk.Frame(self)
        btnf.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(btnf, text=L.t("Save"), command=self._save).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btnf, text=L.t("Cancel"), command=self._cancel).pack(side=tk.RIGHT, padx=4)

    def _build_general(self):
        pad = {"padx": 10, "pady": 6}
        f = self._general
        self._auto_start = tk.BooleanVar()
        ttk.Checkbutton(f, text=L.t("Auto start on login"),
                        variable=self._auto_start).grid(row=0, column=0, columnspan=2, sticky=tk.W, **pad)
        ttk.Label(f, text=L.t("Refresh interval (seconds):")).grid(row=1, column=0, sticky=tk.W, **pad)
        self._refresh_var = tk.StringVar()
        ttk.Spinbox(f, from_=1, to=60, textvariable=self._refresh_var, width=6).grid(row=1, column=1, sticky=tk.W, **pad)
        ttk.Label(f, text=L.t("Language:")).grid(row=2, column=0, sticky=tk.NW, **pad)
        self._lang_var = tk.StringVar()
        lf = ttk.Frame(f)
        lf.grid(row=2, column=1, sticky=tk.W, **pad)
        ttk.Radiobutton(lf, text="English", variable=self._lang_var, value="en").pack(anchor=tk.W)
        ttk.Radiobutton(lf, text="中文", variable=self._lang_var, value="zh").pack(anchor=tk.W)

    def _build_shell(self):
        pad = {"padx": 10, "pady": 4}
        f = self._shell
        ttk.Label(f, text=L.t("Default shell for executing scripts:")).grid(row=0, column=0, columnspan=2, sticky=tk.W, **pad)
        ttk.Label(f, text="(" + L.t("Empty = auto-detect from environment") + ")",
                  font=("", 9), foreground="gray").grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=10)
        self._shell_var = tk.StringVar()
        shells = detect_shells()
        self._shell_combo = ttk.Combobox(f, textvariable=self._shell_var, values=[""] + shells,
                                          state="readonly", width=40)
        self._shell_combo.grid(row=2, column=0, columnspan=2, sticky=tk.W, **pad)
        ttk.Button(f, text=L.t("Rescan available shells"),
                   command=self._rescan_shells).grid(row=3, column=0, columnspan=2, sticky=tk.W, **pad)

    def _rescan_shells(self):
        shells = detect_shells()
        self._shell_combo.configure(values=[""] + shells)

    def _build_logs(self):
        pad = {"padx": 10, "pady": 6}
        f = self._logs
        ttk.Label(f, text=L.t("Log retention:")).grid(row=0, column=0, sticky=tk.W, **pad)
        self._log_ret_var = tk.StringVar()
        self._ret_vals = ["1", "7", "30", "90", "180", "365", "0"]
        self._ret_labels = ["1 day", "7 days", "30 days", "90 days", "180 days", "365 days", "Keep forever"]
        cb = ttk.Combobox(f, textvariable=self._log_ret_var, values=self._ret_labels, state="readonly", width=20)
        cb.grid(row=0, column=1, sticky=tk.W, **pad)
        ttk.Button(f, text=L.t("Open log directory"), command=self._open_log_dir).grid(row=1, column=0, columnspan=2, sticky=tk.W, **pad)

    def _open_log_dir(self):
        log_dir = str(Path.home() / ".local" / "state" / "shellcrond")
        try:
            subprocess.run(["open" if platform.system() == "Darwin" else "xdg-open", log_dir])
        except Exception:
            pass

    def _build_notif(self):
        pad = {"padx": 10, "pady": 4}
        f = self._notif

        # Notification on/off checkboxes
        self._notif_ok = tk.BooleanVar()
        ttk.Checkbutton(f, text=L.t("Notify on success"),
                        variable=self._notif_ok).grid(row=0, column=0, columnspan=2, sticky=tk.W, **pad)
        self._notif_fail = tk.BooleanVar()
        ttk.Checkbutton(f, text=L.t("Notify on failure"),
                        variable=self._notif_fail).grid(row=1, column=0, columnspan=2, sticky=tk.W, **pad)

        ttk.Separator(f, orient=tk.HORIZONTAL).grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=10)

        self._email_var = tk.BooleanVar()
        ttk.Checkbutton(f, text=L.t("Send email notification"),
                        variable=self._email_var).grid(row=3, column=0, columnspan=2, sticky=tk.W, **pad)

        ttk.Label(f, text=L.t("SMTP Server:")).grid(row=4, column=0, sticky=tk.W, **pad)
        self._smtp_server = tk.StringVar()
        ttk.Entry(f, textvariable=self._smtp_server, width=30).grid(row=4, column=1, sticky=tk.W, **pad)

        ttk.Label(f, text=L.t("Port:")).grid(row=5, column=0, sticky=tk.W, **pad)
        self._smtp_port = tk.StringVar()
        ttk.Entry(f, textvariable=self._smtp_port, width=10).grid(row=5, column=1, sticky=tk.W, **pad)

        ttk.Label(f, text=L.t("Username:")).grid(row=6, column=0, sticky=tk.W, **pad)
        self._smtp_user = tk.StringVar()
        ttk.Entry(f, textvariable=self._smtp_user, width=30).grid(row=6, column=1, sticky=tk.W, **pad)

        ttk.Label(f, text=L.t("Password:")).grid(row=7, column=0, sticky=tk.W, **pad)
        self._smtp_pass = tk.StringVar()
        ttk.Entry(f, textvariable=self._smtp_pass, width=30, show="*").grid(row=7, column=1, sticky=tk.W, **pad)

        ttk.Label(f, text=L.t("Recipient:")).grid(row=8, column=0, sticky=tk.W, **pad)
        self._email_to = tk.StringVar()
        ttk.Entry(f, textvariable=self._email_to, width=30).grid(row=8, column=1, sticky=tk.W, **pad)

        ttk.Button(f, text=L.t("Send Test Email"),
                   command=self._test_email).grid(row=9, column=0, columnspan=2, sticky=tk.W, **pad)

    def _build_service(self):
        pad = {"padx": 10, "pady": 4}
        f = self._service
        self._svc_text = tk.Text(f, height=8, width=70, font=("Menlo", 10), state=tk.DISABLED)
        self._svc_text.grid(row=0, column=0, columnspan=4, sticky=tk.EW, **pad)
        btnf = ttk.Frame(f)
        btnf.grid(row=1, column=0, columnspan=4, **pad)
        ttk.Button(btnf, text=L.t("Refresh status"), command=self._refresh_service).pack(side=tk.LEFT, padx=4)
        ttk.Button(btnf, text=L.t("Restart service"), command=self._restart_service).pack(side=tk.LEFT, padx=4)
        ttk.Button(btnf, text=L.t("Stop service"), command=self._stop_service).pack(side=tk.LEFT, padx=4)
        ttk.Button(btnf, text=L.t("View service logs"), command=self._view_service_logs).pack(side=tk.LEFT, padx=4)
        self._refresh_service()

    def _refresh_service(self):
        try:
            info = _request("GET", "/daemon/status")
        except Exception:
            info = {}
        self._svc_text.configure(state=tk.NORMAL)
        self._svc_text.delete("1.0", tk.END)
        lines = [
            ("Daemon status", info.get("status", "unknown")),
            ("PID", str(info.get("pid", "N/A"))),
            ("Started", info.get("started_at", "N/A")[:19]),
            ("Uptime", info.get("uptime", "N/A")),
            ("Scheduler", info.get("scheduler", "unknown")),
            ("Tasks", str(info.get("task_count", 0))),
            ("Running now", str(info.get("running_count", 0))),
        ]
        for k, v in lines:
            self._svc_text.insert(tk.END, f"{k:20s}  {v}\n")
        self._svc_text.configure(state=tk.DISABLED)

    def _restart_service(self):
        from gui.dialogs import askyesno
        if not askyesno(self, "Restart", "Restart the background daemon?"):
            return
        try:
            _request("POST", "/daemon/restart")
            if hasattr(self._app, "_status_label"):
                self._app._status_label.configure(text="Restarting daemon...")
            self.destroy()
            if hasattr(self._app, "_watch_reconnect"):
                self._app._watch_reconnect()
        except Exception as e:
            messagebox.showerror(L.t("Error"), str(e))

    def _stop_service(self):
        from gui.dialogs import askyesno
        if not askyesno(self, "Stop service", L.t("Stop the background daemon?")):
            return
        try:
            _request("POST", "/daemon/stop")
            self.destroy()
            # Show stopped state, no flash — parent already knows daemon status
            if hasattr(self._app, "_status_label"):
                self._app._status_label.configure(text="Daemon stopped")
                self._app._daemon_indicator.configure(text="●", foreground="#F44336")
            if hasattr(self._app, "_show_daemon_ui"):
                self._app.after(100, lambda: self._app._show_daemon_ui(False))
        except Exception as e:
            messagebox.showerror(L.t("Error"), str(e))

    def _view_service_logs(self):
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.run(["open", str(Path.home() / ".local" / "state" / "shellcrond" / "daemon.log")])
            else:
                subprocess.run(["journalctl", "--user", "-u", "shellcrond", "--no-pager", "-n", "50"])
        except Exception:
            pass

    def _test_email(self):
        """Send a test email using current settings."""
        from daemon.email_notify import send_test_email
        settings = {
            "email_recipient": self._email_to.get(),
            "smtp_server": self._smtp_server.get(),
            "smtp_port": int(self._smtp_port.get() or 465),
            "smtp_username": self._smtp_user.get(),
            "smtp_password": self._smtp_pass.get().replace(" ", "").replace("\n", "").strip(),
        }
        err = send_test_email(settings)
        if err:
            messagebox.showerror(L.t("Test Email"), L.t("Failed") + f": {err}")
        else:
            messagebox.showinfo(L.t("Test Email"), L.t("Test email sent. Check your inbox."))

    def _build_data(self):
        pad = {"padx": 10, "pady": 6}
        f = self._data
        ttk.Button(f, text=L.t("Export configuration"), command=self._export_config).grid(row=0, column=0, columnspan=2, sticky=tk.W, **pad)
        ttk.Button(f, text=L.t("Import configuration"), command=self._import_config).grid(row=1, column=0, columnspan=2, sticky=tk.W, **pad)
        ttk.Separator(f, orient=tk.HORIZONTAL).grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=10)
        ttk.Label(f, text=L.t("Clear logs:"), font=("", 10, "bold")).grid(row=3, column=0, sticky=tk.W, **pad)
        ttk.Button(f, text=L.t("Delete logs older than 30 days"), command=lambda: self._clear_logs(30)).grid(row=4, column=0, columnspan=2, sticky=tk.W, **pad)
        ttk.Button(f, text=L.t("Delete logs older than 90 days"), command=lambda: self._clear_logs(90)).grid(row=5, column=0, columnspan=2, sticky=tk.W, **pad)
        ttk.Button(f, text=L.t("Delete all logs"), command=lambda: self._clear_logs(0)).grid(row=6, column=0, columnspan=2, sticky=tk.W, **pad)

    def _export_config(self):
        path = filedialog.asksaveasfilename(title=L.t("Export"), defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            data = _request("GET", "/config/export")
            with open(path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._app._status_label.configure(text=L.t("Configuration exported"))
            self._app.after(3000, lambda: self._app._status_label.configure(
                text=L.t("Daemon is running")))
        except Exception as e:
            messagebox.showerror(L.t("Export"), str(e))

    def _import_config(self):
        path = filedialog.askopenfilename(title=L.t("Import"), filetypes=[("JSON", "*.json")])
        if not path:
            return
        from gui.dialogs import askyesno
        if not askyesno(self, L.t("Import"), L.t("Replace all existing tasks?"),
                        yes_text=L.t("Confirm"), no_text=L.t("Cancel")):
            return
        try:
            with open(path) as f:
                data = json.load(f)
            _request("POST", "/config/import", data=data)
            self._app._status_label.configure(text=L.t("Configuration imported"))
            self._app.after(3000, lambda: self._app._status_label.configure(
                text=L.t("Daemon is running")))
        except Exception as e:
            messagebox.showerror(L.t("Import"), str(e))

    def _clear_logs(self, days: int):
        msg = L.t("Delete all logs?") if days == 0 else f"Delete logs older than {days} days?"
        from gui.dialogs import askyesno
        if not askyesno(self, L.t("Clear logs"), msg):
            return
        try:
            _request("POST", "/logs/clear", data={"days": days})
            self._app._status_label.configure(text=L.t("Done."))
            self._app.after(2000, lambda: self._app._status_label.configure(
                text=L.t("Daemon is running")))
        except Exception as e:
            messagebox.showerror(L.t("Error"), str(e))

    def _load_values(self):
        s = self._settings
        self._auto_start.set(s.get("auto_start", False))
        self._refresh_var.set(str(s.get("refresh_interval", 5)))
        self._lang_var.set(s.get("language", "en"))
        self._shell_var.set(s.get("default_shell", ""))
        ret_labels = ["1 day", "7 days", "30 days", "90 days", "180 days", "365 days", "Keep forever"]
        ret_vals = ["1", "7", "30", "90", "180", "365", "0"]
        try:
            idx = ret_vals.index(str(s.get("log_retention_days", 30)))
            self._log_ret_var.set(ret_labels[idx])
        except ValueError:
            self._log_ret_var.set(ret_labels[2])
        self._notif_ok.set(s.get("notify_on_success", False))
        self._notif_fail.set(s.get("notify_on_failure", True))
        self._email_var.set(s.get("notify_email", False))
        self._smtp_server.set(s.get("smtp_server", "smtp.gmail.com"))
        self._smtp_port.set(str(s.get("smtp_port", 465)))
        self._smtp_user.set(s.get("smtp_username", ""))
        self._smtp_pass.set(s.get("smtp_password", ""))
        self._email_to.set(s.get("email_recipient", ""))


    def _save(self):
        try:
            refresh_val = max(1, int(self._refresh_var.get()))
        except ValueError:
            refresh_val = 5

        ret_labels = ["1 day", "7 days", "30 days", "90 days", "180 days", "365 days", "Keep forever"]
        ret_vals = ["1", "7", "30", "90", "180", "365", "0"]
        try:
            idx = ret_labels.index(self._log_ret_var.get())
            ret_days = int(ret_vals[idx])
        except (ValueError, IndexError):
            ret_days = 30

        new_settings = {
            "auto_start": self._auto_start.get(),
            "refresh_interval": refresh_val,
            "language": self._lang_var.get(),
            "default_shell": self._shell_var.get(),
            "log_retention_days": ret_days,
            "notify_on_success": self._notif_ok.get(),
            "notify_on_failure": self._notif_fail.get(),
            "notify_email": self._email_var.get(),
            "smtp_server": self._smtp_server.get(),
            "smtp_port": int(self._smtp_port.get() or 465),
            "smtp_username": self._smtp_user.get(),
            "smtp_password": self._smtp_pass.get().replace(" ", "").replace("\n", "").strip(),
            "email_recipient": self._email_to.get(),
        }
        save(new_settings)
        global _SETTINGS
        _SETTINGS = new_settings

        # Apply auto-start only if changed
        old_settings = load()
        if new_settings["auto_start"] != old_settings.get("auto_start", False):
            apply_auto_start(new_settings["auto_start"])

        # Apply language
        if new_settings["language"] != L.current:
            L.toggle()
            if L.current != new_settings["language"]:
                L.toggle()
            if hasattr(self._app, "_refresh_ui_text"):
                self._app._refresh_ui_text()

        self._show_saved_notification()
        self.destroy()

    def _cancel(self):
        self.destroy()

    def _show_saved_notification(self):
        """Show a brief non-blocking saved indicator in the parent's status bar."""
        if hasattr(self._app, "_status_label") and self._app._status_label:
            orig = self._app._status_label.cget("text")
            self._app._status_label.configure(text=L.t("Settings saved"))
            self._app.after(2000, lambda: self._app._status_label.configure(text=orig))


_DIALOG_STATE_FILE = Path.home() / ".config" / "shellcrond" / "gui_state.json"



