"""
Mail module — sends email via company SMTP server.

Uses smtplib with the internal mail relay.  SMTP host/port and
sender address are read from the settings table (configurable
via Admin > SMTP page).

Usage:
    from app.mail import send_mail
    success = send_mail(
        from_addr="tracker@company.com",
        to_addr="user@company.com",
        subject="Password Reset",
        body="Click here to reset ...",
    )
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# Defaults — overridden at runtime from settings table
DEFAULT_SMTP_HOST = "10.234.8.22"
DEFAULT_SMTP_PORT = 2525


def _read_smtp_settings():
    """Read SMTP host/port from settings table (safe outside app context)."""
    try:
        from app.models import setting as setting_model
        host = setting_model.get("smtp_host") or DEFAULT_SMTP_HOST
        port = int(setting_model.get("smtp_port") or DEFAULT_SMTP_PORT)
        return host, port
    except Exception:
        return DEFAULT_SMTP_HOST, DEFAULT_SMTP_PORT


def send_mail(*, from_addr, to_addr, subject, body,
              smtp_host=None, smtp_port=None):
    """Send an email via the company SMTP relay.

    Returns True on success, False on failure.
    If ``smtp_host`` / ``smtp_port`` are not provided, they are read from
    the settings table automatically.
    """
    if smtp_host is None or smtp_port is None:
        db_host, db_port = _read_smtp_settings()
        host = smtp_host or db_host
        port = int(smtp_port or db_port)
    else:
        host = smtp_host
        port = int(smtp_port)

    if not from_addr:
        print("[Mail] No from_addr configured, skipping")
        return False

    # Build MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr if isinstance(to_addr, str) else ", ".join(to_addr)
    msg.attach(MIMEText(body, "plain", "utf-8"))

    recipients = [to_addr] if isinstance(to_addr, str) else list(to_addr)

    try:
        s = smtplib.SMTP(host, port, timeout=15)
        s.sendmail(from_addr, recipients, msg.as_string())
        s.quit()
        print(f"[Mail] Sent to {msg['To']} — OK")
        return True
    except Exception as e:
        print(f"[Mail] Error: {e}")
        return False
