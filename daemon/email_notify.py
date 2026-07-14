"""Email notification via SMTP with detailed task reports."""

import smtplib
import logging
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_settings() -> dict:
    path = Path.home() / ".config" / "shellcrond" / "settings.json"
    try:
        if path.exists():
            import json
            return json.loads(path.read_text())
    except Exception:
        return {}
    return {}


def _send(subject: str, body: str, settings: dict):
    server = settings.get("smtp_server", "")
    port = int(settings.get("smtp_port", 465))
    user = settings.get("smtp_username", "")
    password = settings.get("smtp_password", "")
    recipient = settings.get("email_recipient", "")
    if not all([server, user, password, recipient]):
        logger.warning("email: incomplete SMTP config")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="shellcron.local")
    msg["X-Mailer"] = "ShellCron"
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL(server, port, timeout=15) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
        logger.info("email sent: %s", subject[:60])
    except Exception as e:
        logger.warning("email failed: %s", e)


def send_alert(task_name, status, *, scripts=None,
               failed_script=None, return_code=None,
               started_at=None, finished_at=None):
    """Send a detailed email report for a task execution.

    scripts: list of dicts with keys: script_path, return_code, stdout, stderr
    """
    settings = _load_settings()
    if not settings.get("notify_email", False):
        return

    status_icon = "OK" if status == "success" else "FAILED"
    subject = f"[ShellCron] {status_icon} {task_name}"

    lines = [
        f"ShellCron Task Report",
        f"",
        f"  Task:    {task_name}",
        f"  Status:  {status_icon}",
        f"  Start:   {started_at[:19] if started_at else '?'}",
        f"  End:     {finished_at[:19] if finished_at else '?'}",
        f"",
    ]

    if scripts:
        lines.append(f"  Scripts ({len(scripts)}):")
        lines.append("")
        for i, s in enumerate(scripts):
            sp = s.get("script_path", "?")
            rc = s.get("return_code")
            ok = "OK" if rc == 0 else f"FAILED (exit {rc})"
            lines.append(f"  [{i+1}] {Path(sp).name}  ({ok})")
            lines.append(f"       Path: {sp}")
            stdout = (s.get("stdout") or "").strip()
            stderr = (s.get("stderr") or "").strip()
            if stdout:
                lines.append(f"       stdout:")
                for line in stdout.split("\n")[:15]:
                    lines.append(f"         {line}")
            if stderr:
                lines.append(f"       stderr:")
                for line in stderr.split("\n")[:20]:
                    lines.append(f"         {line}")

    body = "\n".join(lines)
    logger.info("email: sending alert for %s (status=%s)", task_name, status)
    _send(subject, body, settings)


def send_test_email(settings: dict) -> str:
    subject = "[ShellCron] Test Email"
    body = "ShellCron Test Email\n\nIf you receive this, email notification is configured correctly."
    try:
        _send(subject, body, settings)
        return ""
    except Exception as e:
        return str(e)
