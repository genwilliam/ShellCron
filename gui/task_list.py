"""Task list panel using ttk.Treeview."""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
from datetime import datetime, timezone

from gui.lang import L


def _describe_schedule(task: dict) -> str:
    zh = L.current == "zh"
    stype = task.get("schedule_type", "")
    cfg = task.get("schedule_config", {})
    if isinstance(cfg, str):
        import json
        try:
            cfg = json.loads(cfg)
        except json.JSONDecodeError:
            cfg = {}
    days = cfg.get("days", 1)
    if days <= 0:
        days = 1 / 1440.0
    total_m = int(round(days * 1440))
    if total_m < 1:
        total_m = 1
    if stype == "interval":
        if total_m < 60:
            return f"每 {total_m} 分钟" if zh else f"Every {total_m}m"
        elif total_m < 1440:
            h = total_m // 60
            m = total_m % 60
            if zh:
                return f"每 {h} 小时{m} 分钟" if m else f"每 {h} 小时"
            return f"Every {h}h{m}m" if m else f"Every {h}h"
        d = days if days == int(days) else round(days, 1)
        return f"每 {int(d)} 天" if zh else f"Every {d}d"
    elif stype == "cron":
        return f"Cron: {cfg.get('expr', '?')}"
    elif stype == "fixed_time":
        t = cfg.get('time', '?')
        return f"每天 {t}" if zh else f"Daily {t}"
    elif stype == "relative_interval":
        if zh:
            if total_m < 60:
                return f"等待 {total_m} 分钟后执行"
            elif total_m < 1440:
                return f"等待 {total_m // 60} 小时后执行"
            d = days if days == int(days) else round(days, 1)
            return f"等待 {int(d)} 天后执行"
        else:
            if total_m < 60:
                return f"Wait {total_m}m"
            elif total_m < 1440:
                return f"Wait {total_m // 60}h"
            d = days if days == int(days) else round(days, 1)
            return f"Wait {d}d"
    return "?"


def _countdown_str(next_run_iso: Optional[str]) -> str:
    if not next_run_iso:
        return "—"
    try:
        dt = datetime.fromisoformat(next_run_iso)
        now = datetime.now(timezone.utc)
        secs = int((dt - now).total_seconds())
        if secs < 0:
            return "Overdue" if L.current == "en" else "已逾期"
        if secs < 60:
            return f"{secs}s"
        mins = secs // 60
        if mins < 60:
            return f"{mins}m {secs % 60}s"
        hrs = mins // 60
        if hrs < 24:
            return f"{hrs}h {mins % 60}m"
        dys = hrs // 24
        return f"{dys}d {hrs % 24}h"
    except (ValueError, TypeError):
        return "—"


class TaskListPanel(ttk.Frame):

    def __init__(self, master, on_edit: Callable, on_delete: Callable,
                 on_run: Callable, on_toggle: Callable, on_refresh: Callable,
                 on_logs: Callable = None, on_settings: Callable = None, **kw):
        super().__init__(master, **kw)
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_run = on_run
        self.on_toggle = on_toggle
        self.on_refresh = on_refresh
        self.on_logs = on_logs
        self.on_settings = on_settings
        self._tasks: list[dict] = []
        self._refresh_id: Optional[str] = None
        self._toolbar_btns: list[ttk.Button] = []
        self._build_ui()

    def _build_ui(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 4))

        self._toolbar_btns = []
        btn_specs = [
            ("Refresh", lambda: self.on_refresh() if self.on_refresh else None),
            ("New Task", lambda: self.on_edit(None) if self.on_edit else None),
            ("Settings", lambda: self.on_settings() if self.on_settings else None),
        ]
        for text, cmd in btn_specs:
            btn = ttk.Button(toolbar, text=L.t(text), command=cmd)
            btn.pack(side=tk.LEFT, padx=2)
            self._toolbar_btns.append(btn)

        cols = ("name", "status", "schedule", "next_run", "countdown",
                "success_count", "failed_count", "last_result")
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                 selectmode="browse", height=15)

        self.tree.heading("name", text=L.t("Task Name"))
        self.tree.heading("status", text=L.t("Status"))
        self.tree.heading("schedule", text=L.t("Schedule"))
        self.tree.heading("next_run", text=L.t("Next Run"))
        self.tree.heading("countdown", text=L.t("Countdown"))
        self.tree.heading("success_count", text=L.t("OK"))
        self.tree.heading("failed_count", text=L.t("Fail"))
        self.tree.heading("last_result", text=L.t("Last Result"))

        self.tree.column("name", width=120, minwidth=80, anchor=tk.CENTER)
        self.tree.column("status", width=45, minwidth=35, anchor=tk.CENTER)
        self.tree.column("schedule", width=130, minwidth=75, anchor=tk.CENTER)
        self.tree.column("next_run", width=120, minwidth=70, anchor=tk.CENTER)
        self.tree.column("countdown", width=85, minwidth=60, anchor=tk.CENTER)
        self.tree.column("success_count", width=35, minwidth=30, anchor=tk.CENTER)
        self.tree.column("failed_count", width=35, minwidth=30, anchor=tk.CENTER)
        self.tree.column("last_result", width=65, minwidth=50, anchor=tk.CENTER)

        self.tree.tag_configure("running", foreground="#2196F3")
        self.tree.tag_configure("disabled", foreground="#999")

        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._menu = tk.Menu(self, tearoff=0)
        self._rebuild_menu()

        self.tree.bind("<Button-3>", self._post_menu)
        self.tree.bind("<Double-1>", self._on_double_click)

    def _rebuild_menu(self):
        self._menu.delete(0, tk.END)
        self._menu.add_command(label=L.t("Edit"), command=lambda: self._action("edit"))
        self._menu.add_command(label=L.t("Execute Once"), command=lambda: self._action("run"))
        self._menu.add_separator()
        self._menu.add_command(label=L.t("Enable/Disable"), command=lambda: self._action("toggle"))
        self._menu.add_separator()
        self._menu.add_command(label=L.t("View Logs"), command=lambda: self._action("logs"))
        self._menu.add_command(label=L.t("Delete Task"), command=lambda: self._action("delete"))

    def _post_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self._menu.post(event.x_root, event.y_root)

    def _on_double_click(self, event):
        """Double-click opens the execution logs for the selected task."""
        self._action("logs")

    def _selected_task(self):
        sel = self.tree.selection()
        if not sel:
            return None
        vals = self.tree.item(sel[0], "values")
        for t in self._tasks:
            if t["name"] == vals[0]:
                return t
        return None

    def _action(self, action: str):
        task = self._selected_task()
        if not task:
            return
        tid = task["id"]
        if action == "edit":
            self.on_edit(tid)
        elif action == "run":
            self.on_run(tid)
        elif action == "delete":
            self.on_delete(tid)
        elif action == "toggle":
            self.on_toggle(tid)
        elif action == "logs":
            if self.on_logs:
                self.on_logs(tid)

    def update_tasks(self, tasks: list[dict]):
        sel_name = None
        sel = self.tree.selection()
        if sel:
            vals = self.tree.item(sel[0], "values")
            if vals:
                sel_name = vals[0]

        self._tasks = tasks
        for item in self.tree.get_children():
            self.tree.delete(item)

        new_item_id = None
        for t in tasks:
            running = t.get("running", False)
            enabled = t.get("enabled", True)
            status_text = "▶" if running else ("●" if enabled else "○")
            last = t.get("last_status")
            last_map = {
                "running": L.t("Running"),
                "success": L.t("Success"),
                "failed": L.t("Failed"),
                "skipped": L.t("Skipped"),
            }
            last_text = last_map.get(last, "—")
            next_run = t.get("next_run", "")
            if next_run:
                try:
                    dt = datetime.fromisoformat(next_run)
                    next_run = dt.strftime("%m-%d %H:%M")
                except ValueError:
                    next_run = next_run[:19]
            else:
                next_run = "—"
            cd = _countdown_str(t.get("next_run"))
            sc = t.get("success_count", 0)
            fc = t.get("failed_count", 0)
            desc = _describe_schedule(t)
            tags = ()
            if running:
                tags = ("running",)
            elif not enabled:
                tags = ("disabled",)
            item_id = self.tree.insert("", tk.END, values=(
                t["name"], status_text, desc, next_run, cd,
                sc, fc, last_text,
            ), tags=tags)
            if sel_name and t["name"] == sel_name:
                new_item_id = item_id
        if new_item_id:
            self.tree.selection_set(new_item_id)

    def refresh_labels(self):
        btn_keys = ["Refresh", "New Task", "Settings"]
        for key, btn in zip(btn_keys, self._toolbar_btns):
            btn.configure(text=L.t(key))
        self.tree.heading("name", text=L.t("Task Name"))
        self.tree.heading("status", text=L.t("Status"))
        self.tree.heading("schedule", text=L.t("Schedule"))
        self.tree.heading("next_run", text=L.t("Next Run"))
        self.tree.heading("countdown", text=L.t("Countdown"))
        self.tree.heading("success_count", text=L.t("OK"))
        self.tree.heading("failed_count", text=L.t("Fail"))
        self.tree.heading("last_result", text=L.t("Last Result"))
        self._rebuild_menu()
        self.update_tasks(self._tasks)

    def start_auto_refresh(self, interval_ms: int = 5000):
        self.on_refresh()
        self._refresh_id = self.after(interval_ms,
                                      lambda: self.start_auto_refresh(interval_ms))

    def stop_auto_refresh(self):
        if self._refresh_id:
            self.after_cancel(self._refresh_id)
            self._refresh_id = None
