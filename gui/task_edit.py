"""Task creation/editing dialog."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

from daemon.models import SCHEDULE_TYPES
from daemon.models import (
    SCHEDULE_INTERVAL, SCHEDULE_CRON, SCHEDULE_FIXED_TIME,
    SCHEDULE_RELATIVE_INTERVAL,
)
from gui.lang import L

_SCHEDULE_KEYS = [k for k, _ in SCHEDULE_TYPES]


class TaskEditDialog(tk.Toplevel):

    def __init__(self, parent, task_data: Optional[dict] = None,
                 scripts: Optional[list[str]] = None):
        super().__init__(parent)
        self.withdraw()
        self.title(L.t("Edit Task") if task_data else L.t("New Task"))
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._task = task_data
        self._scripts = scripts or []
        self.result: Optional[dict] = None

        self._build_ui()
        if task_data:
            self._load_task(task_data)
        else:
            self._update_schedule_ui()

        self.update_idletasks()
        try:
            pw, ph = parent.winfo_width(), parent.winfo_height()
            px, py = parent.winfo_x(), parent.winfo_y()
            w, h = self.winfo_width(), self.winfo_height()
            self.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//2}")
        except Exception:
            pass

        self.deiconify()
        self.wait_window()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}
        main = ttk.Frame(self, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text=L.t("Task Name:")).grid(row=0, column=0, sticky=tk.W, **pad)
        self._name_var = tk.StringVar()
        ttk.Entry(main, textvariable=self._name_var, width=40).grid(
            row=0, column=1, columnspan=2, sticky=tk.EW, **pad)

        self._enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(main, text=L.t("Enabled"), variable=self._enabled_var).grid(
            row=1, column=0, columnspan=3, sticky=tk.W, **pad)

        ttk.Label(main, text=L.t("Schedule:")).grid(row=2, column=0, sticky=tk.W, **pad)
        self._schedule_type_var = tk.StringVar(value=SCHEDULE_INTERVAL)
        self._schedule_type_var.trace_add("write", lambda *a: self._update_schedule_ui())
        self._schedule_combo = ttk.Combobox(
            main, values=_SCHEDULE_KEYS, state="readonly", width=30)
        self._schedule_combo.grid(row=2, column=1, columnspan=2, sticky=tk.W, **pad)
        self._schedule_combo.set(SCHEDULE_INTERVAL)
        self._schedule_combo.bind("<<ComboboxSelected>>", self._on_type_selected)

        self._schedule_frame = ttk.Frame(main)
        self._schedule_frame.grid(row=3, column=0, columnspan=3, sticky=tk.EW, **pad)
        self._schedule_widgets = {}

        ttk.Label(main, text=L.t("Shell Scripts:")).grid(row=4, column=0, sticky=tk.NW, **pad)
        script_frame = ttk.Frame(main)
        script_frame.grid(row=4, column=1, columnspan=2, sticky=tk.EW, **pad)
        self._script_listbox = tk.Listbox(script_frame, height=4, width=40)
        self._script_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        script_btn_frame = ttk.Frame(script_frame)
        script_btn_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))
        ttk.Button(script_btn_frame, text=L.t("Add .sh"), command=self._add_script).pack(fill=tk.X, pady=2)
        ttk.Button(script_btn_frame, text=L.t("Remove"), command=self._remove_script).pack(fill=tk.X, pady=2)
        ttk.Button(script_btn_frame, text=L.t("Move Up"), command=self._move_up).pack(fill=tk.X, pady=2)
        ttk.Button(script_btn_frame, text=L.t("Move Down"), command=self._move_down).pack(fill=tk.X, pady=2)

        ttk.Label(main, text=L.t("Args:")).grid(row=5, column=0, sticky=tk.NW, **pad)
        self._args_text = tk.Text(main, height=3, width=40)
        self._args_text.grid(row=5, column=1, columnspan=2, sticky=tk.EW, **pad)
        ttk.Label(main, text=L.t("One arg per line")).grid(row=6, column=1, columnspan=2, sticky=tk.W, padx=10)

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=7, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(btn_frame, text=L.t("Confirm"), command=self._confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=L.t("Cancel"), command=self.destroy).pack(side=tk.LEFT, padx=4)
        main.columnconfigure(1, weight=1)

    def _on_type_selected(self, event):
        key = self._schedule_combo.get()
        self._schedule_type_var.set(key)

    def _update_schedule_ui(self, *args):
        for w in self._schedule_frame.winfo_children():
            w.destroy()
        self._schedule_widgets = {}
        stype = self._schedule_type_var.get()

        if stype in (SCHEDULE_INTERVAL, SCHEDULE_RELATIVE_INTERVAL):
            ttk.Label(self._schedule_frame, text=L.t("Interval:")).pack(side=tk.LEFT)
            val_var = tk.StringVar(value="10")
            ttk.Entry(self._schedule_frame, textvariable=val_var, width=6).pack(side=tk.LEFT, padx=(4, 2))
            unit_var = tk.StringVar(value=L.t("days"))
            unit_combo = ttk.Combobox(
                self._schedule_frame, textvariable=unit_var,
                values=[L.t("days"), L.t("hours"), L.t("minutes")],
                state="readonly", width=8)
            unit_combo.pack(side=tk.LEFT, padx=2)
            self._schedule_widgets["val"] = val_var
            self._schedule_widgets["unit"] = unit_var
            label = L.t("Every N days") if stype == SCHEDULE_INTERVAL else L.t("Run N days after finish")
            ttk.Label(self._schedule_frame, text=label).pack(side=tk.LEFT, padx=4)
        elif stype == SCHEDULE_CRON:
            ttk.Label(self._schedule_frame, text=L.t("Cron Expression:")).pack(side=tk.LEFT)
            var = tk.StringVar(value="0 23 */10 * *")
            ttk.Entry(self._schedule_frame, textvariable=var, width=24).pack(side=tk.LEFT, padx=4)
            self._schedule_widgets["expr"] = var
            ttk.Label(self._schedule_frame, text=L.t("Min Hour Day Mon Week")).pack(side=tk.LEFT, padx=4)
        elif stype == SCHEDULE_FIXED_TIME:
            ttk.Label(self._schedule_frame, text=L.t("Daily at")).pack(side=tk.LEFT)
            var = tk.StringVar(value="23:59")
            ttk.Entry(self._schedule_frame, textvariable=var, width=8).pack(side=tk.LEFT, padx=4)
            self._schedule_widgets["time"] = var
            ttk.Label(self._schedule_frame, text=L.t("Run at (HH:MM)")).pack(side=tk.LEFT, padx=4)

    def _add_script(self):
        path = filedialog.askopenfilename(
            title=L.t("Choose Shell Script"),
            filetypes=[(L.t("Shell Scripts (*.sh)"), "*.sh"), (L.t("All Files"), "*")])
        if path:
            self._scripts.append(path)
            self._refresh_script_list()

    def _remove_script(self):
        sel = self._script_listbox.curselection()
        if sel:
            del self._scripts[sel[0]]
            self._refresh_script_list()

    def _move_up(self):
        sel = self._script_listbox.curselection()
        if sel and sel[0] > 0:
            i = sel[0]
            self._scripts[i], self._scripts[i-1] = self._scripts[i-1], self._scripts[i]
            self._refresh_script_list()
            self._script_listbox.selection_set(i-1)

    def _move_down(self):
        sel = self._script_listbox.curselection()
        if sel and sel[0] < len(self._scripts) - 1:
            i = sel[0]
            self._scripts[i], self._scripts[i+1] = self._scripts[i+1], self._scripts[i]
            self._refresh_script_list()
            self._script_listbox.selection_set(i+1)

    def _refresh_script_list(self):
        self._script_listbox.delete(0, tk.END)
        for s in self._scripts:
            self._script_listbox.insert(tk.END, s)

    def _load_task(self, task: dict):
        self._name_var.set(task["name"])
        self._enabled_var.set(task["enabled"])
        stype = task["schedule_type"]
        self._schedule_combo.set(stype)

        cfg = task.get("schedule_config", {})
        if isinstance(cfg, str):
            import json
            try:
                cfg = json.loads(cfg)
            except json.JSONDecodeError:
                cfg = {}

        self._schedule_type_var.set(stype)

        if stype in (SCHEDULE_INTERVAL, SCHEDULE_RELATIVE_INTERVAL):
            d = float(cfg.get("days", 10))
            total_sec = int(round(d * 86400))
            if total_sec < 3600:
                display_val = max(1, total_sec // 60)
                display_unit = L.t("minutes")
            elif total_sec < 86400:
                display_val = max(1, total_sec // 3600)
                display_unit = L.t("hours")
            else:
                display_val = total_sec / 86400
                display_val = int(display_val) if display_val == int(display_val) else round(display_val, 1)
                display_unit = L.t("days")
            self._schedule_widgets["val"].set(str(display_val))
            self._schedule_widgets["unit"].set(display_unit)
        elif stype == SCHEDULE_CRON:
            self._schedule_widgets["expr"].set(cfg.get("expr", ""))
        elif stype == SCHEDULE_FIXED_TIME:
            self._schedule_widgets["time"].set(cfg.get("time", "23:59"))

        self._scripts = [s["script_path"] for s in task.get("_scripts", [])]
        self._refresh_script_list()

        args = cfg.get("script_args", [])
        self._args_text.delete("1.0", tk.END)
        if args:
            self._args_text.insert("1.0", "\n".join(args))

    def _confirm(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning(L.t("Warning"), L.t("Task name required"), parent=self)
            return

        stype = self._schedule_type_var.get()

        if stype in (SCHEDULE_INTERVAL, SCHEDULE_RELATIVE_INTERVAL):
            try:
                val = float(self._schedule_widgets["val"].get())
                if val <= 0:
                    raise ValueError
                unit = self._schedule_widgets["unit"].get()
            except (ValueError, KeyError):
                messagebox.showwarning(L.t("Warning"), L.t("Days must be >= 1"), parent=self)
                return
            if unit == L.t("minutes"):
                days = val / 1440.0
            elif unit == L.t("hours"):
                days = val / 24.0
            else:
                days = val
            schedule_config = {"days": max(days, 1/1440.0)}
        elif stype == SCHEDULE_CRON:
            expr = self._schedule_widgets.get("expr", tk.StringVar()).get().strip()
            if not expr:
                messagebox.showwarning(L.t("Warning"), L.t("Cron expression required"), parent=self)
                return
            schedule_config = {"expr": expr}
        elif stype == SCHEDULE_FIXED_TIME:
            time_str = self._schedule_widgets.get("time", tk.StringVar()).get().strip()
            if ":" not in time_str:
                messagebox.showwarning(L.t("Warning"), L.t("Time format: HH:MM"), parent=self)
                return
            schedule_config = {"time": time_str}
        else:
            messagebox.showwarning(L.t("Warning"), L.t("Please select a schedule type"), parent=self)
            return

        if not self._scripts:
            messagebox.showwarning(L.t("Warning"), L.t("At least one script required"), parent=self)
            return

        raw_args = self._args_text.get("1.0", tk.END).strip()
        script_args = [line.strip() for line in raw_args.split("\n") if line.strip()]
        schedule_config["script_args"] = script_args

        self.result = {
            "name": name,
            "enabled": self._enabled_var.get(),
            "schedule_type": stype,
            "schedule_config": schedule_config,
            "scripts": list(self._scripts),
        }
        self.destroy()
