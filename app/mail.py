"""
Mail module — sends email via company ddi_api.pl command.

The mail server uses an XML-based API:
  1. Build XML with From, To, Subject, Body, Bcc, ContentType
  2. Write to temp file
  3. Call: /CAD/DCAD/bin/ddi_api.pl MAIL -f <tempfile>

Usage:
    from app.mail import send_mail
    success = send_mail(
        from_addr="tracker@company.com",
        to_addr="user@company.com",
        subject="Password Reset",
        body="Click here to reset ...",
    )
"""
import os
import subprocess
import tempfile
from xml.etree.ElementTree import Element, tostring

MAIL_CMD = "/CAD/DCAD/bin/ddi_api.pl"


def send_mail(*, from_addr, to_addr, subject, body):
    """Send an email via the company ddi_api.pl command.

    Returns True on success, False on failure.
    """
    data = {
        "From": from_addr,
        "To": to_addr,
        "Subject": subject,
        "Body": body,
        "Bcc": "",
        "ContentType": "text/plain; charset=utf-8",
    }

    elem = Element("MAIL")
    for key, val in data.items():
        child = Element(str(key))
        child.text = "" if val is None else str(val)
        elem.append(child)

    xml_bytes = tostring(elem, encoding="utf-8")

    if not os.path.isfile(MAIL_CMD):
        # Fallback: log to console when command not available (dev environment)
        print(f"[Mail] ddi_api.pl not found, logging instead:")
        print(f"  To: {to_addr}")
        print(f"  Subject: {subject}")
        print(f"  Body: {body[:200]}")
        return False

    try:
        with tempfile.NamedTemporaryFile(mode="wb", delete=True, suffix=".xml") as f:
            f.write(xml_bytes)
            f.flush()
            ret = subprocess.call([MAIL_CMD, "MAIL", "-f", f.name])
        return ret == 0
    except Exception as e:
        print(f"[Mail] Error: {e}")
        return False
