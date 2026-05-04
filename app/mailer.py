"""Send mail via the corporate ddi_api.pl wrapper.

Adapted from docs/reference/mailServer.py with these changes:
  - Default ContentType is text/html; charset=utf-8 (was text/plain; charset=big5)
    so we can send formatted tables.
  - Mail command path overridable via MAIL_CMD env var.

The wrapper writes a JSON-via-XML temp file and shells out to the perl CLI.
ElementTree handles XML escaping, so HTML in Body survives unchanged.
"""
import os
import subprocess
import tempfile
from xml.etree.ElementTree import Element, tostring


DEFAULT_MAIL_CMD = "/CAD/DCAD/bin/ddi_api.pl"


def _dict_to_xml(data):
    elem = Element("MAIL")
    for key, val in data.items():
        child = Element(str(key))
        child.text = "" if val is None else str(val)
        elem.append(child)
    return elem


def send_mail(
    to,
    subject,
    body,
    from_addr=None,
    cc="",
    bcc="",
    content_type="text/html; charset=utf-8",
    mail_cmd=None,
):
    """Send via ddi_api.pl. Returns True on success.

    Raises FileNotFoundError if the mail command binary is missing.
    """
    cmd = mail_cmd or os.environ.get("MAIL_CMD", DEFAULT_MAIL_CMD)
    if not os.path.isfile(cmd):
        raise FileNotFoundError(f"Mail command not found: {cmd}")

    data = {
        "From": from_addr or os.environ.get("MAIL_FROM") or to,
        "To": to,
        "Cc": cc or "",
        "Bcc": bcc or "",
        "Subject": subject,
        "Body": body,
        "ContentType": content_type,
    }

    xml_bytes = tostring(_dict_to_xml(data), encoding="utf-8")
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".xml", delete=True) as f:
        f.write(xml_bytes)
        f.flush()
        ret = subprocess.call([cmd, "MAIL", "-f", f.name])
    return ret == 0
