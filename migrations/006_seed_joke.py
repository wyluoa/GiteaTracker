"""Seed jokes table with one default warm-up joke so /fun isn't empty on
the first visit after migration 003 created the table.

Uses the classic "QA 工程師走進酒吧" joke — well-known in the engineering
community, edge-case / boundary-testing themed, which suits a QC Script
Request tracking team.

Guarded by "only seed if table is empty" so:
  - Re-running this migration (if schema_version lost) won't duplicate.
  - If super user has already added their own jokes, we don't overwrite
    or add noise — we only seed when /fun is truly empty.
"""
from datetime import datetime, timezone

SCHEMA_VERSION = "006"
DESCRIPTION = "seed one default AI-generated warm-up joke if jokes table is empty"


SEED_BODY = """一位 QA 工程師走進酒吧。

他點了 1 杯啤酒、0 杯啤酒、999999 杯啤酒、-1 杯啤酒、NULL 杯啤酒、一隻蜥蜴、⎯⎯⎯ ; DROP TABLE beer; ⎯⎯⎯。
一切運作正常。

接著真正的使用者走進酒吧問：「廁所在哪裡？」

酒吧瞬間爆炸。"""


def up(conn):
    count = conn.execute("SELECT COUNT(*) FROM jokes WHERE is_deleted = 0").fetchone()[0]
    if count > 0:
        return  # super user already curated; leave them be
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO jokes (body, author_user_id, author_name_snapshot, created_at)
           VALUES (?, NULL, ?, ?)""",
        (SEED_BODY, "AI-seed", now),
    )
