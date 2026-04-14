"""
Attachment routes — upload and download.
"""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Blueprint, request, send_file, abort, current_app, g
)
from app.db import get_db
from app.routes.auth import login_required

bp = Blueprint("attachments", __name__)

ALLOWED_EXT = {"png", "jpg", "jpeg", "pdf"}
MIME_MAP = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "pdf": "application/pdf",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def save_attachments(timeline_entry_id, files):
    """Save uploaded files and create attachment records. Returns list of attachment IDs."""
    db = get_db()
    max_mb = current_app.config.get("ATTACHMENT_MAX_MB", 5)
    max_per_entry = current_app.config.get("ATTACHMENT_MAX_PER_ENTRY", 3)
    base_dir = current_app.config["ATTACHMENT_DIR"]

    saved = []
    for i, f in enumerate(files):
        if i >= max_per_entry:
            break
        if not f or not f.filename:
            continue

        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in ALLOWED_EXT:
            continue

        data = f.read()
        if len(data) > max_mb * 1024 * 1024:
            continue

        now = datetime.now(timezone.utc)
        sub_dir = os.path.join(base_dir, str(now.year), f"{now.month:02d}")
        os.makedirs(sub_dir, exist_ok=True)

        filename = f"{uuid.uuid4().hex}.{ext}"
        stored_path = os.path.join(sub_dir, filename)
        with open(stored_path, "wb") as out:
            out.write(data)

        cur = db.execute(
            """INSERT INTO attachments
               (timeline_entry_id, original_filename, stored_path, mime_type, size_bytes, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (timeline_entry_id, f.filename, stored_path,
             MIME_MAP.get(ext, "application/octet-stream"), len(data), _now()),
        )
        saved.append(cur.lastrowid)

    db.commit()
    return saved


@bp.route("/attachments/<int:attachment_id>")
@login_required
def download(attachment_id):
    """下載附件
    ---
    tags:
      - Attachments
    parameters:
      - name: attachment_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: 回傳檔案內容 (inline)
      404:
        description: 附件不存在或檔案遺失
    """
    db = get_db()
    att = db.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
    if not att:
        abort(404)

    if not os.path.exists(att["stored_path"]):
        abort(404)

    return send_file(
        att["stored_path"],
        mimetype=att["mime_type"],
        as_attachment=False,
        download_name=att["original_filename"],
    )
