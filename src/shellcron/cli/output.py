"""Terminal output helpers — colored text and tables."""

import sys

# ANSI escape codes
class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    class FG:
        GREEN = "\033[32m"
        RED = "\033[31m"
        YELLOW = "\033[33m"
        CYAN = "\033[36m"
        MAGENTA = "\033[35m"
        GRAY = "\033[90m"
        WHITE = "\033[97m"

    class BG:
        GREEN = "\033[42m"
        RED = "\033[41m"
        YELLOW = "\033[43m"


def _s(text: str, *codes: str) -> str:
    """Apply ANSI codes to text, with auto-reset."""
    if not sys.stdout.isatty():
        return text
    return "".join(codes) + text + Style.RESET


def green(text: str) -> str:
    return _s(text, Style.FG.GREEN)


def red(text: str) -> str:
    return _s(text, Style.FG.RED)


def yellow(text: str) -> str:
    return _s(text, Style.FG.YELLOW)


def cyan(text: str) -> str:
    return _s(text, Style.FG.CYAN)


def magenta(text: str) -> str:
    return _s(text, Style.FG.MAGENTA)


def gray(text: str) -> str:
    return _s(text, Style.FG.GRAY)


def bold(text: str) -> str:
    return _s(text, Style.BOLD)


def dim(text: str) -> str:
    return _s(text, Style.DIM)


# ── Status symbols ──────────────────────────────────────────────

def status_symbol(enabled: bool, last_status: str = None) -> str:
    """Return a colored status symbol for a task."""
    if not enabled:
        return gray("○")
    if last_status == "running":
        return green("▶")
    if last_status == "failed":
        return red("✕")
    if last_status == "success":
        return green("●")
    return yellow("◌")


def status_text(enabled: bool, last_status: str = None) -> str:
    """Return colored status text."""
    if not enabled:
        return gray("Disabled")
    if last_status == "running":
        return green("Running")
    if last_status == "failed":
        return red("Failed")
    if last_status == "success":
        return green("Enabled")
    return yellow("Waiting")


# ── Table helpers ───────────────────────────────────────────────

def print_table(rows: list[list[str]], headers: list[str]):
    """Print a formatted table with aligned columns."""
    if not rows:
        return

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            # Strip ANSI codes when calculating width
            clean = cell
            for code in [Style.RESET, Style.BOLD, Style.DIM,
                         Style.FG.GREEN, Style.FG.RED, Style.FG.YELLOW,
                         Style.FG.CYAN, Style.FG.GRAY, Style.FG.WHITE,
                         Style.BG.GREEN, Style.BG.RED, Style.BG.YELLOW]:
                clean = clean.replace(code, "")
            visible_len = len(clean)
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], visible_len)

    # Header separator
    sep = "─" * (sum(col_widths) + 3 * (len(headers) - 1) + 4)

    # Print header
    header_line = " " + "   ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print(sep)

    # Print rows
    for row in rows:
        line_parts = []
        for i, cell in enumerate(row):
            if i < len(col_widths):
                # Pad with spaces, accounting for ANSI codes
                clean = cell
                for code in [Style.RESET, Style.BOLD, Style.DIM,
                             Style.FG.GREEN, Style.FG.RED, Style.FG.YELLOW,
                             Style.FG.CYAN, Style.FG.GRAY, Style.FG.WHITE,
                             Style.BG.GREEN, Style.BG.RED, Style.BG.YELLOW]:
                    clean = clean.replace(code, "")
                padding = col_widths[i] - len(clean)
                if padding > 0:
                    cell = cell + " " * padding
                line_parts.append(cell)
        print(" " + "   ".join(line_parts))
