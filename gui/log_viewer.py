"""Execution log viewer dialog."""

import tkinter as tk
from tkinter import ttk

from gui.api_client import get_logs, get_log_detail
from gui.lang import L

STATUS_LABELS = {
    "success": L.t("Success"),
    "failed": L.t("Failed"),
    "running": L.t("Running"),
    "skipped": L.t("Skipped"),
}

TRIGGER_LABELS = {
    "scheduled": L.t("Scheduled"),
    "manual": L.t("Manual"),
}


class LogViewer(tk.Toplevel):

    def __init__(self, parent, task_id: int, task_name: str):
        super().__init__(parent)
        self.withdraw()  # hide immediately, position before show
        self.title(f"{L.t('Execution Logs')} - {task_name}")
        self.geometry("900x600")
        self.transient(parent)

        self._task_id = task_id
        self._logs: list = []
        self._build_ui()
        self._load_logs()

        # Center on parent window
        self.update_idletasks()
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
        main = ttk.Frame(self, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        paned = ttk.PanedWindow(main, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Top: log list
        top_frame = ttk.Frame(paned)
        paned.add(top_frame, weight=1)

        # Toolbar
        tb = ttk.Frame(top_frame)
        tb.pack(fill=tk.X)
        ttk.Label(tb, text=L.t("Execution History"),
                  font=("", 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(tb, text=L.t("Refresh"),
                   command=self._load_logs).pack(side=tk.RIGHT, padx=4)

        cols = ("started_at", "triggered_by", "status", "duration_ms")
        self._tree = ttk.Treeview(top_frame, columns=cols, show="headings",
                                  selectmode="browse", height=8)
        self._tree.heading("started_at", text=L.t("Start Time"))
        self._tree.heading("triggered_by", text=L.t("Trigger"))
        self._tree.heading("status", text=L.t("Status"))
        self._tree.heading("duration_ms", text=L.t("Duration"))

        self._tree.column("started_at", width=200)
        self._tree.column("triggered_by", width=100, anchor=tk.CENTER)
        self._tree.column("status", width=100, anchor=tk.CENTER)
        self._tree.column("duration_ms", width=80, anchor=tk.CENTER)

        self._tree.bind("<<TreeviewSelect>>", self._on_select_log)

        vsb = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Bottom: detail
        bottom_frame = ttk.Frame(paned)
        paned.add(bottom_frame, weight=1)

        ttk.Label(bottom_frame, text=L.t("Execution Detail"),
                  font=("", 11, "bold")).pack(anchor=tk.W)

        self._notebook = ttk.Notebook(bottom_frame)
        self._notebook.pack(fill=tk.BOTH, expand=True)

    def _load_logs(self):
        try:
            self._logs = get_logs(self._task_id, limit=100)
        except Exception:
            self._logs = []

        # Clear existing tabs and tree
        for tab in self._notebook.tabs():
            self._notebook.forget(tab)
        for item in self._tree.get_children():
            self._tree.delete(item)

        for log in self._logs:
            status = log.get("status", "")
            label = STATUS_LABELS.get(status, status)
            duration = log.get("duration_ms")
            dur_str = f"{duration} {L.t('ms')}" if duration is not None else "—"
            triggered = TRIGGER_LABELS.get(log.get("triggered_by", ""),
                                           log.get("triggered_by", ""))

            self._tree.insert("", tk.END, values=(
                log.get("started_at", "")[:19],
                triggered,
                label,
                dur_str,
            ))

    def _on_select_log(self, event):
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        if idx >= len(self._logs):
            return
        log = self._logs[idx]

        for tab in self._notebook.tabs():
            self._notebook.forget(tab)

        try:
            detail = get_log_detail(log["id"])
        except Exception:
            frame = ttk.Frame(self._notebook)
            ttk.Label(frame, text="Failed to load").pack(padx=10, pady=10)
            self._notebook.add(frame, text="Error")
            return

        results = detail.get("results", [])
        if not results:
            frame = ttk.Frame(self._notebook)
            ttk.Label(frame, text=L.t("No script results")).pack(padx=10, pady=10)
            self._notebook.add(frame, text=L.t("Detail"))
            return

        for i, sr in enumerate(results):
            frame = ttk.Frame(self._notebook)
            self._notebook.add(frame,
                               text=f"#{i+1} {sr.get('script_path', '').split('/')[-1]}")

            text = tk.Text(frame, wrap=tk.WORD, font=("Menlo", 10))
            vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
            text.configure(yscrollcommand=vsb.set)
            text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)

            rc = sr.get("return_code")
            rc_str = str(rc) if rc is not None else "N/A"
            dur = sr.get("duration_ms")
            dur_str = f"{dur} {L.t('ms')}" if dur is not None else "—"

            info = (
                f"{L.t('Script')}: {sr.get('script_path', '?')}\n"
                f"{L.t('Return Code')}: {rc_str}  |  {L.t('Duration')}: {dur_str}\n"
                + "─" * 60 + "\n"
            )
            text.insert(tk.END, info, "info")

            stdout = sr.get("stdout", "")
            stderr = sr.get("stderr", "")

            if stdout:
                text.insert(tk.END, "\n[stdout]\n", "section")
                text.insert(tk.END, stdout + "\n")
            if stderr:
                text.insert(tk.END, "\n[stderr]\n", "section_error")
                text.insert(tk.END, stderr + "\n")

            if not stdout and not stderr:
                text.insert(tk.END, L.t("No output") + "\n")

            text.configure(state=tk.DISABLED)
            text.tag_configure("info", foreground="#555")
            text.tag_configure("section", foreground="#2196F3",
                               font=("Menlo", 10, "bold"))
            text.tag_configure("section_error", foreground="#F44336",
                               font=("Menlo", 10, "bold"))
