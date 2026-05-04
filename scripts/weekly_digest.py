"""Send weekly digest of upcoming launches to the meeting owner.

Two HTML tables:
  1. Next week (Mon-Sun after today)
  2. Next 30 days (today+1 .. today+30) — overlaps with table 1 on purpose
     so each table is self-contained.

Excludes cells already in 'done' or 'unneeded' state. Uses the same
check-in-date parsing as the calendar (handles both YYYY-MM-DD and MM-DD).

Cron (every Friday 15:00):
  0 15 * * 5 cd ~/GiteaTracker && venv/bin/python scripts/weekly_digest.py >> logs/digest.log 2>&1

Usage:
  venv/bin/python scripts/weekly_digest.py                           # send to default
  venv/bin/python scripts/weekly_digest.py --dry-run                 # print HTML, do not send
  venv/bin/python scripts/weekly_digest.py --to user@example.com     # override recipient
  venv/bin/python scripts/weekly_digest.py --save preview.html       # save HTML preview
  venv/bin/python scripts/weekly_digest.py --today 2026-05-08        # simulate a date
"""
import argparse
import sys
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app                       # noqa: E402
from app.db import get_db                        # noqa: E402
from app.mailer import send_mail                 # noqa: E402


DEFAULT_TO = "wyluoa@tsmc.com"

STATE_COLORS = {
    "done":       "#27ae60",
    "uat_done":   "#3498db",
    "uat":        "#e67e22",
    "developing": "#95a5a6",
    "tbd":        "#8e44ad",
    "unneeded":   "#bdc3c7",
}
STATE_LABELS = {
    "done": "Done", "uat_done": "UAT done", "uat": "UAT",
    "developing": "Dev", "tbd": "TBD", "unneeded": "Unneeded",
}


def parse_check_in_date(raw, today):
    if not raw:
        return None
    s = str(raw).strip()
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return datetime.strptime(s, "%Y-%m-%d").date()
        if len(s) == 5 and s[2] == "-":
            d = datetime.strptime(f"{today.year}-{s}", "%Y-%m-%d").date()
            if (d - today).days > 180:
                d = d.replace(year=today.year - 1)
            return d
    except ValueError:
        return None
    return None


def collect_launches(today, start, end):
    db = get_db()
    rows = db.execute(
        """SELECT s.issue_id, s.node_id, s.state, s.check_in_date, s.short_note,
                  i.display_number, i.topic, i.requestor_name,
                  n.display_name as node_name
           FROM issue_node_states s
           JOIN issues i ON s.issue_id = i.id
           JOIN nodes n ON s.node_id = n.id
           WHERE s.check_in_date IS NOT NULL AND s.check_in_date != ''
             AND (s.state IS NULL OR s.state NOT IN ('done', 'unneeded'))
             AND i.status = 'ongoing' AND i.is_deleted = 0"""
    ).fetchall()

    out = []
    for r in rows:
        d = parse_check_in_date(r["check_in_date"], today)
        if d and start <= d <= end:
            out.append({
                "date": d,
                "display_number": r["display_number"],
                "topic": r["topic"],
                "owner": r["requestor_name"] or "—",
                "node_name": r["node_name"],
                "state": r["state"] or "",
                "short_note": r["short_note"] or "",
            })
    out.sort(key=lambda x: (x["date"], x["display_number"]))
    return out


def chip_html(state):
    color = STATE_COLORS.get(state, "#cccccc")
    label = STATE_LABELS.get(state, "(空)")
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
        f'background:{color};color:#fff;font-size:11px;white-space:nowrap;">{escape(label)}</span>'
    )


def _group_key(r, group_by):
    if group_by == "node":
        return r["node_name"]
    if group_by == "issue":
        return f'#{r["display_number"]} {r["topic"]}'
    return None


def render_table(rows, with_short_note, group_by=None):
    """Render a launches table.

    group_by: None | "node" | "issue" — when set, rows are sorted by that key
    and a subheader band breaks each group. Within a group rows stay sorted by date.
    """
    if not rows:
        return '<p style="color:#888;margin:6px 0;">(無)</p>'

    headers = ["上線日期", "#", "Topic", "Node", "Owner", "狀態"]
    if with_short_note:
        headers.append("短註")

    th_style = (
        "padding:6px 10px;background:#ecebe5;border:1px solid #cdc9bf;"
        "text-align:left;font-size:13px;font-weight:bold;color:#3f3d38;"
    )
    td_style = (
        "padding:6px 10px;border:1px solid #dcd8cf;font-size:13px;"
        "vertical-align:top;color:#3f3d38;"
    )
    group_th_style = (
        "padding:6px 10px;background:#a8b5c0;color:#2f3a44;border:1px solid #8c9aa6;"
        "text-align:left;font-size:13px;font-weight:bold;"
    )

    if group_by:
        sorted_rows = sorted(rows, key=lambda r: (_group_key(r, group_by), r["date"], r["display_number"]))
    else:
        sorted_rows = rows  # caller already sorted by date

    parts = [
        '<table cellspacing="0" cellpadding="0" border="0" '
        'style="border-collapse:collapse;width:100%;'
        "font-family:Arial,'Microsoft JhengHei',sans-serif;\">",
        "<thead><tr>",
    ]
    for h in headers:
        parts.append(f'<th style="{th_style}">{escape(h)}</th>')
    parts.append("</tr></thead><tbody>")

    current_group = object()  # sentinel
    zebra = 0
    for r in sorted_rows:
        if group_by:
            key = _group_key(r, group_by)
            if key != current_group:
                # count remaining rows in this group
                count = sum(1 for x in sorted_rows if _group_key(x, group_by) == key)
                label = (f"Node: {key} ({count} 項)" if group_by == "node"
                         else f"{key}  ({count} 項)")
                parts.append(
                    f'<tr><td colspan="{len(headers)}" style="{group_th_style}">'
                    f"{escape(label)}</td></tr>"
                )
                current_group = key
                zebra = 0

        bg = "#f5f3ed" if zebra % 2 else "#ffffff"
        zebra += 1
        cells = [
            escape(r["date"].isoformat()),
            f'<b>{escape(r["display_number"])}</b>',
            escape(r["topic"]),
            escape(r["node_name"]),
            escape(r["owner"]),
            chip_html(r["state"]),
        ]
        if with_short_note:
            cells.append(escape(r["short_note"]))
        parts.append(f'<tr style="background:{bg};">')
        for c in cells:
            parts.append(f'<td style="{td_style}">{c}</td>')
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def render_email(today, next_week_rows, next_month_rows,
                 next_week_start, next_week_end, next_month_end,
                 group_by=None):
    owners = sorted({r["owner"] for r in next_month_rows
                     if r["owner"] and r["owner"] != "—"})
    owners_str = "、".join(escape(o) for o in owners) or "(無)"
    group_label = {"node": "依 Node 分類", "issue": "依題號分類"}.get(group_by, "依日期排序")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,'Microsoft JhengHei',sans-serif;color:#222;max-width:1100px;">
  <h2 style="border-bottom:2px solid #8c9aa6;padding-bottom:6px;margin-bottom:6px;color:#3f3d38;">
    Gitea Tracker — 週報 ({today.isoformat()})
  </h2>
  <p style="color:#85807a;font-size:12px;margin:0 0 24px;">
    自動寄送 — 排除已 Done / Unneeded 的 cell。「未來一個月」與「下周」會有重疊,各自獨立可讀。排版:{group_label}。
  </p>

  <h3 style="margin:24px 0 4px;">下周上線清單 ({next_week_start.isoformat()} ~ {next_week_end.isoformat()})</h3>
  <p style="color:#85807a;font-size:12px;margin:0 0 8px;">共 {len(next_week_rows)} 項</p>
  {render_table(next_week_rows, with_short_note=True, group_by=group_by)}

  <h3 style="margin:32px 0 4px;">未來一個月上線清單 ({(today + timedelta(days=1)).isoformat()} ~ {next_month_end.isoformat()})</h3>
  <p style="color:#85807a;font-size:12px;margin:0 0 8px;">
    共 {len(next_month_rows)} 項。Owner 名單:{owners_str}
  </p>
  {render_table(next_month_rows, with_short_note=False, group_by=group_by)}

  <hr style="margin-top:32px;border:none;border-top:1px solid #cdc9bf;">
  <p style="color:#9a958e;font-size:11px;">
    來源:check_in_date 欄位。如要調整寄送時間或內容,改 scripts/weekly_digest.py 與 user crontab。
  </p>
</body></html>
"""


def main():
    parser = argparse.ArgumentParser(description="Send weekly launch digest")
    parser.add_argument("--to", default=DEFAULT_TO,
                        help=f"Recipient (default {DEFAULT_TO})")
    parser.add_argument("--from", dest="from_addr", default=None,
                        help="From address (default = recipient or MAIL_FROM env)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print HTML, do not send")
    parser.add_argument("--save", help="Save HTML to file")
    parser.add_argument("--today", help="Override today (YYYY-MM-DD), for testing")
    parser.add_argument("--group-by", choices=["date", "node", "issue"], default="issue",
                        help="Row grouping (default: issue — multi-node rollouts cluster together)")
    args = parser.parse_args()

    today = (datetime.strptime(args.today, "%Y-%m-%d").date()
             if args.today else date.today())

    days_until_next_monday = (7 - today.weekday()) or 7
    next_week_start = today + timedelta(days=days_until_next_monday)
    next_week_end = next_week_start + timedelta(days=6)
    next_month_end = today + timedelta(days=30)

    app = create_app()
    with app.app_context():
        next_week_rows = collect_launches(today, next_week_start, next_week_end)
        next_month_rows = collect_launches(
            today, today + timedelta(days=1), next_month_end
        )

    group_by = None if args.group_by == "date" else args.group_by
    html = render_email(today, next_week_rows, next_month_rows,
                        next_week_start, next_week_end, next_month_end,
                        group_by=group_by)

    if args.save:
        Path(args.save).write_text(html, encoding="utf-8")
        print(f"Saved {args.save} ({len(html)} bytes)")

    if args.dry_run:
        print(html)
        print(f"\n[dry-run] would send to {args.to}", file=sys.stderr)
        print(f"  next week ({next_week_start} ~ {next_week_end}):  {len(next_week_rows)} items",
              file=sys.stderr)
        print(f"  next month (..{next_month_end}): {len(next_month_rows)} items",
              file=sys.stderr)
        return 0

    subject = (f"[Gitea Tracker] 週報 {today.isoformat()} — "
               f"下周 {len(next_week_rows)} 項 / 未來 30 天 {len(next_month_rows)} 項")
    try:
        ok = send_mail(
            to=args.to,
            subject=subject,
            body=html,
            from_addr=args.from_addr,
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("(set MAIL_CMD env var or use --dry-run / --save)", file=sys.stderr)
        return 1

    if not ok:
        print("ERROR: mail command returned non-zero", file=sys.stderr)
        return 2

    print(f"Sent: {subject} -> {args.to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
