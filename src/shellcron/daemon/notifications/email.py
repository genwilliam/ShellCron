"""Email notification via SMTP with detailed task reports."""

import json
import logging
import smtplib
import socket
import ssl
import urllib.request
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

logger = logging.getLogger(__name__)

# Surge / ClashX / Stash / similar proxies use the 198.18.0.0/15 range
# as "fake IPs" to intercept DNS for transparent proxying.  When these
# are present, SMTP connections typically fail because the proxy cannot
# forward SMTP/SSL traffic correctly.
_FAKE_IP_PREFIX = "198.18."
_DOH_URL = "https://dns.google/resolve?name={}&type=A"


def _load_settings() -> dict:
    path = Path.home() / ".config" / "shellcrond" / "settings.json"
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return {}


def _resolve_real_ip(hostname: str) -> tuple[str | None, bool]:
    """Resolve *hostname* to a real IP, bypassing proxy fake-IP DNS.

    Returns ``(real_ip, proxy_detected)`` where *real_ip* is the real
    address (or ``None``) and *proxy_detected* is ``True`` when all
    system-resolved addresses fell in the 198.18.0.0/15 fake-IP range.
    """
    import socket as _sk

    proxy_detected = False
    # 1 — system DNS, filter out Surge fake IPs
    try:
        results = _sk.getaddrinfo(hostname, 0, _sk.AF_INET, _sk.SOCK_STREAM)
        for res in results:
            ip = res[4][0]
            if not ip.startswith(_FAKE_IP_PREFIX):
                logger.debug("email: system DNS gave real IP %s for %s", ip, hostname)
                return ip, False
        # All returned IPs are in the fake range — proxy detected
        proxy_detected = True
        logger.info(
            "email: system DNS returned only fake IPs (198.18.x.x) for %s "
            "- proxy (Surge/Clash) likely active",
            hostname,
        )
    except Exception:
        pass

    # 2 — Google DoH (bypasses proxy DNS interception)
    try:
        url = _DOH_URL.format(hostname)
        req = urllib.request.Request(url, headers={"Accept": "application/dns-json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            for answer in data.get("Answer", []):
                if answer.get("type") == 1:  # A record
                    ip = answer["data"]
                    if not ip.startswith(_FAKE_IP_PREFIX):
                        logger.info(
                            "email: DoH resolved real IP %s for %s", ip, hostname
                        )
                        return ip, proxy_detected
    except Exception as exc:
        logger.debug("email: DoH resolution failed: %s", exc)

    logger.warning(
        "email: could not resolve real IP for %s "
        "(proxy may be intercepting SMTP traffic)",
        hostname,
    )
    return None, proxy_detected


def _proxy_bypass_hint() -> str:
    """Return a user-facing hint if a proxy (Surge/Clash/…) is detected."""
    import subprocess, os
    for proc in ["Surge", "ClashX", "Stash", "Clash"]:
        try:
            result = subprocess.run(
                ["pgrep", "-i", proc],
                capture_output=True, text=True, timeout=3,
            )
            if result.stdout.strip():
                hint = (
                    f"  Proxy detected: {proc} is running.\n"
                    f"  → Configure {proc} to bypass gmail SMTP traffic:\n"
                    f"    Add a bypass rule for 'smtp.gmail.com' "
                    f"or add port 465/587 to the 'bypass' / 'direct' list."
                )
                if proc == "Surge":
                    hint = (
                        f"  Proxy detected: Surge is running.\n"
                        f"  → Add a Surge bypass rule in your config:\n"
                        f"    DOMAIN-SUFFIX, gmail.com, DIRECT"
                    )
                elif proc == "ClashX":
                    hint = (
                        f"  Proxy detected: ClashX is running.\n"
                        f"  → Configure ClashX to bypass Gmail:\n"
                        f"    Add 'smtp.gmail.com' to the direct/basic-proxy ruleset."
                    )
                return hint
        except Exception:
            pass
    return ""


def _build_message(
    task_name: str,
    status: str,
    smtp_user: str,
    recipient: str,
    scripts: list | None = None,
    failed_script: str | None = None,
    return_code: int | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"[ShellCron] {status.upper()} - {task_name}"
    msg["From"] = smtp_user or "shellcron@localhost"
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    body = f"Task: {task_name}\nStatus: {status}\n"
    if started_at:
        body += f"Started: {started_at[:19]}\n"
    if finished_at:
        body += f"Finished: {finished_at[:19]}\n"

    if scripts:
        body += f"\nScripts ({len(scripts)}):\n"
        for s in scripts:
            rc = s.get("return_code", "?")
            dur = s.get("duration_ms", "")
            dur_str = f" ({dur}ms)" if dur else ""
            body += (
                f"  - {s.get('script_path', '?')} → exit={rc}{dur_str}\n"
            )
            out = (s.get("stdout") or "").strip()
            if out:
                body += f"      stdout: {out[:300]}\n"
            err = (s.get("stderr") or "").strip()
            if err:
                body += f"      stderr: {err[:300]}\n"

    if failed_script:
        body += f"\nFailed: {failed_script}"
        if return_code is not None:
            body += f" (exit {return_code})"
        body += "\n"

    msg.set_content(body)
    return msg


def _try_send(
    hostname: str,
    real_ip: str | None,
    port: int,
    use_ssl: bool,
    msg: EmailMessage,
    smtp_user: str,
    smtp_pass: str,
) -> bool:
    """Attempt SMTP delivery on *port* using SSL or STARTTLS.

    When *real_ip* is provided we connect to the IP directly (bypassing
    proxy fake-IP DNS) but still set *server_hostname* for proper SNI
    so TLS certificate validation works correctly.
    """
    connect_target = real_ip or hostname
    method = "SSL" if use_ssl else "STARTTLS"
    logger.info(
        "email: trying %s:%d (%s) [target=%s]",
        hostname, port, method, connect_target,
    )

    try:
        context = ssl.create_default_context()
        if use_ssl:
            # ---- SMTP over implicit TLS (port 465) ----
            # Create a raw TCP socket to the *real* IP, then wrap it
            # with SSL providing the *original hostname* for SNI.
            # Plug the wrapped socket into SMTP_SSL to bypass proxy DNS.
            raw = socket.create_connection((connect_target, port), timeout=15)
            ssock = context.wrap_socket(raw, server_hostname=hostname)
            server = smtplib.SMTP_SSL()
            server._host = hostname
            server.sock = ssock
            server.does_esmtp = True
        else:
            # ---- SMTP with STARTTLS (port 587) ----
            raw = socket.create_connection((connect_target, port), timeout=15)
            server = smtplib.SMTP()
            server._host = hostname
            server.sock = raw
            server.does_esmtp = True
            # Perform EHLO + STARTTLS
            code, _ = server.ehlo()
            if code == 250:
                server.starttls(context=context)
                server.ehlo()

        if smtp_user:
            server.login(smtp_user, smtp_pass)

        server.send_message(msg)
        server.quit()

        logger.info(
            "email: sent via %s:%d (%s) to %s",
            hostname, port, method, msg["To"],
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "email: auth failed on %s:%d — check username/password",
            hostname, port,
        )
        raise
    except Exception as exc:
        logger.warning(
            "email: %s:%d (%s) failed: %s",
            hostname, port, method, exc,
        )
        return False


def send_alert(
    task_name,
    status,
    *,
    scripts=None,
    failed_script=None,
    return_code=None,
    started_at=None,
    finished_at=None,
):
    """Send email notification about task execution."""
    settings = _load_settings()

    if not settings.get("notify_email", False):
        logger.info("email: notify_email disabled, skipping")
        return False

    smtp_host = settings.get("smtp_server", "").strip()
    smtp_port = int(settings.get("smtp_port", 465))
    smtp_user = settings.get("smtp_username", "").strip()
    smtp_pass = settings.get("smtp_password", "").strip()
    recipient = settings.get("email_recipient", "").strip()

    if not smtp_host or not recipient:
        logger.warning("email: SMTP host or recipient not configured")
        return False

    logger.info(
        "email: sending to %s via %s (port %d)",
        recipient, smtp_host, smtp_port,
    )

    msg = _build_message(
        task_name, status, smtp_user, recipient,
        scripts=scripts, failed_script=failed_script,
        return_code=return_code,
        started_at=started_at, finished_at=finished_at,
    )

    # Resolve real IP, bypassing proxy fake-IP DNS
    real_ip, proxy_detected = _resolve_real_ip(smtp_host)

    # Build ordered list of (port, use_ssl) attempts
    attempts: list[tuple[int, bool]] = []
    user_ssl = smtp_port == 465
    attempts.append((smtp_port, user_ssl))
    for fallback in [(587, False), (465, True)]:
        if fallback not in attempts:
            attempts.append(fallback)

    last_error: Exception | None = None
    for port, use_ssl in attempts:
        try:
            if _try_send(smtp_host, real_ip, port, use_ssl, msg, smtp_user, smtp_pass):
                return True
        except smtplib.SMTPAuthenticationError:
            return False
        except Exception as exc:
            last_error = exc

    # All attempts failed — build a helpful diagnostic message
    parts = [
        f"email: all ports failed for {smtp_host}. Last error: {last_error}",
    ]
    if proxy_detected:
        hint = _proxy_bypass_hint()
        if hint:
            parts.append(hint)
            for line in hint.split("\n"):
                logger.error("email: %s", line)
    logger.error(parts[0])
    return False


def send_test_email(settings: dict) -> str:
    """Send a test email using the provided settings dict (from Web UI).

    Returns an empty string on success or an error message on failure.
    """
    smtp_host = settings.get("smtp_server", "").strip()
    smtp_port = int(settings.get("smtp_port", 465))
    smtp_user = settings.get("smtp_username", "").strip()
    smtp_pass = settings.get("smtp_password", "").strip()
    recipient = settings.get("email_recipient", "").strip()

    msg = _build_message(
        "Test Email", "test", smtp_user, recipient,
    )

    real_ip, proxy_detected = _resolve_real_ip(smtp_host)
    use_ssl = smtp_port == 465

    try:
        ok = _try_send(
            smtp_host, real_ip, smtp_port, use_ssl, msg, smtp_user, smtp_pass,
        )
        if ok:
            return ""
        msg_parts = ["all connection attempts failed"]
        if proxy_detected:
            hint = _proxy_bypass_hint()
            if hint:
                msg_parts.append(hint)
        return "\n".join(msg_parts)
    except smtplib.SMTPAuthenticationError as e:
        return f"authentication failed: {e}"
    except Exception as e:
        return str(e)
