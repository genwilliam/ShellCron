"""Custom theme-aware confirmation dialogs."""

import tkinter as tk
from tkinter import ttk

from gui.lang import L


class ConfirmDialog(tk.Toplevel):
    """Theme-aware yes/no confirmation dialog."""

    def __init__(self, parent, title: str, message: str, *,
                 yes_text: str = None, no_text: str = None):
        super().__init__(parent)
        self.withdraw()  # hide immediately, position before show
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.result = False

        if yes_text is None:
            yes_text = L.t("Confirm")
        if no_text is None:
            no_text = L.t("Cancel")

        f = ttk.Frame(self, padding=16)
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text=message, wraplength=400).pack(pady=8)

        bf = ttk.Frame(f)
        bf.pack(pady=(8, 0))
        ttk.Button(bf, text=yes_text, command=self._yes).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text=no_text, command=self._no).pack(side=tk.LEFT, padx=4)

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

    def _yes(self):
        self.result = True
        self.destroy()

    def _no(self):
        self.result = False
        self.destroy()


def askyesno(parent, title: str, message: str,
             yes_text: str = None, no_text: str = None) -> bool:
    """Shorthand: returns True if user clicked Yes."""
    d = ConfirmDialog(parent, title, message, yes_text=yes_text, no_text=no_text)
    return d.result
