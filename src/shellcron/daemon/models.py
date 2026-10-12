"""Data models and constants."""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta
import json

# ── Schedule types ──────────────────────────────────────────────
SCHEDULE_INTERVAL = "interval"
SCHEDULE_CRON = "cron"
SCHEDULE_FIXED_TIME = "fixed_time"
SCHEDULE_RELATIVE_INTERVAL = "relative_interval"

SCHEDULE_TYPES = [
    (SCHEDULE_INTERVAL, "每 N 天执行"),
    (SCHEDULE_CRON, "Cron 表达式"),
    (SCHEDULE_FIXED_TIME, "固定时间执行"),
    (SCHEDULE_RELATIVE_INTERVAL, "完成后等待 N 天"),
]

# ── Execution states ────────────────────────────────────────────
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

TRIGGER_SCHEDULED = "scheduled"
TRIGGER_MANUAL = "manual"


def parse_schedule_config(schedule_type: str, config_str: str) -> dict:
    """Parse JSON schedule config, return dict with defaults."""
    try:
        config = json.loads(config_str) if isinstance(config_str, str) else config_str
    except (json.JSONDecodeError, TypeError):
        config = {}
    return config


def build_schedule_config(schedule_type: str, config: dict) -> str:
    """Validate and serialize schedule config to JSON string."""
    if schedule_type in (SCHEDULE_INTERVAL, SCHEDULE_RELATIVE_INTERVAL):
        days = float(config.get("days", 1))
        if days < 1 / 1440.0:
            days = 1 / 1440.0
        days = round(days, 6)
        result = {"days": days}
        for key in ("script_args", "misfire_policy"):
            if key in config:
                result[key] = config[key]
        return json.dumps(result)
    elif schedule_type == SCHEDULE_CRON:
        expr = config.get("expr", "0 0 * * *")
        result = {"expr": expr}
        for key in ("script_args", "misfire_policy"):
            if key in config:
                result[key] = config[key]
        return json.dumps(result)
    elif schedule_type == SCHEDULE_FIXED_TIME:
        time_str = config.get("time", "00:00")
        result = {"time": time_str}
        for key in ("script_args", "misfire_policy"):
            if key in config:
                result[key] = config[key]
        return json.dumps(result)
    return json.dumps(config)


def _fmt_interval(days: float, lang: str) -> str:
    """Format an interval value in the given language."""
    total_m = int(round(days * 1440))
    if total_m < 1:
        total_m = 1
    if lang == "zh":
        if total_m < 60:
            return f"每 {total_m} 分钟"
        elif total_m < 1440:
            h = total_m // 60
            return f"每 {h} 小时"
        d_int = int(days)
        if days == d_int:
            return f"每 {d_int} 天"
        return f"每 {round(days, 1)} 天"
    else:
        if total_m < 60:
            return f"Every {total_m}m"
        elif total_m < 1440:
            h = total_m // 60
            m = total_m % 60
            return f"Every {h}h{m}m" if m else f"Every {h}h"
        d = days if days == int(days) else round(days, 1)
        return f"Every {d}d"


def describe_schedule(schedule_type: str, config_str: str, lang: str = "zh") -> str:
    """Return human-readable schedule description in given language."""
    config = parse_schedule_config(schedule_type, config_str)
    if schedule_type == SCHEDULE_INTERVAL:
        return _fmt_interval(config.get("days", 1), lang)
    elif schedule_type == SCHEDULE_CRON:
        return f"Cron: {config.get('expr', '?')}"
    elif schedule_type == SCHEDULE_FIXED_TIME:
        t = config.get("time", "?")
        return f"每天 {t}" if lang == "zh" else f"Daily {t}"
    elif schedule_type == SCHEDULE_RELATIVE_INTERVAL:
        total_m = int(round(config.get("days", 1) * 1440))
        if total_m < 1:
            total_m = 1
        if lang == "zh":
            if total_m < 60:
                return f"完成后等待 {total_m} 分钟"
            elif total_m < 1440:
                return f"完成后等待 {total_m // 60} 小时"
            d = config.get("days", 1)
            return f"完成后等待 {int(d)} 天" if d == int(d) else f"完成后等待 {round(d,1)} 天"
        else:
            if total_m < 60:
                return f"Wait {total_m}m after finish"
            elif total_m < 1440:
                h = total_m // 60
                m = total_m % 60
                return f"Wait {h}h{m}m" if m else f"Wait {h}h"
            d = config.get("days", 1)
            return f"Wait {d}d after finish"
    return "未知" if lang == "zh" else "Unknown"


def get_start_interval_seconds(schedule_type: str, config_str: str) -> Optional[int]:
    """Return interval in seconds for APScheduler IntervalTrigger if applicable."""
    config = parse_schedule_config(schedule_type, config_str)
    if schedule_type == SCHEDULE_INTERVAL:
        return timedelta(days=config.get("days", 1)).total_seconds()
    return None
