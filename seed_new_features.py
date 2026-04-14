"""
Seed script — add fake data for new features testing.

Adds:
  1. Issues with group_label (special project groups like "強身健體系列")
  2. Issues with multi-line JIRA tickets
  3. Closed issues with some nodes intentionally left empty (no state record)
  4. A few on_hold issues for variety

Usage:
    python seed_new_features.py
"""
import sys
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta, date

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app
from app.db import get_db


def iso_week_to_date(year, week, weekday=1):
    jan4 = date(year, 1, 4)
    start = jan4 - timedelta(days=jan4.isoweekday() - 1)
    return start + timedelta(weeks=week - 1, days=weekday - 1)


OWNERS = ["WY", "Kevin", "Jack", "Lisa", "Amy", "Tom", "Eric", "Vivian"]
JIRA_PREFIXES = ["PROJ", "HW", "SW", "FW"]

# ── Group-label project issues ──
GROUP_PROJECTS = [
    {
        "label": "強身健體系列",
        "issues": [
            ("Stress test 全機高溫運轉 72hr", "WY"),
            ("Vibration test IEC 60068", "Kevin"),
            ("Drop test 1.2m 六面", "Jack"),
            ("ESD immunity ±8kV contact", "Lisa"),
            ("Salt spray test 48hr", "Tom"),
        ],
    },
    {
        "label": "Security Hardening",
        "issues": [
            ("Secure boot chain verification", "Eric"),
            ("TEE firmware update signing", "Amy"),
            ("Kernel ASLR enforcement", "Vivian"),
        ],
    },
]

# ── Multi-line JIRA issues ──
MULTI_JIRA_ISSUES = [
    ("Dual-SIM RF switching optimization", "Kevin", "HW-5501\nSW-3320"),
    ("NFC + Wireless charging coil interference", "Lisa", "HW-5502\nFW-2210"),
    ("Camera + GPS concurrent power budget", "Tom", "PROJ-8801\nHW-5503"),
    ("BT audio codec + Wi-Fi coexistence", "Amy", "SW-3321\nFW-2211"),
]

# ── Closed issues with sparse node states ──
OLD_CLOSED_ISSUES = [
    ("Legacy UART debug port removal", "Jack", 2024, 38),
    ("eMMC 5.1 compatibility patch", "WY", 2024, 42),
    ("LCD backlight PWM frequency fix", "Eric", 2025, 3),
    ("Charger IC thermal shutdown threshold", "Vivian", 2025, 8),
    ("SPI flash boot fallback logic", "Kevin", 2025, 12),
]


def main():
    app = create_app()
    with app.app_context():
        db = get_db()

        nodes = db.execute(
            "SELECT * FROM nodes WHERE is_active = 1 ORDER BY sort_order"
        ).fetchall()
        if not nodes:
            print("ERROR: No nodes. Run seed.py first.")
            return

        wy = db.execute("SELECT id FROM users WHERE username = 'wy'").fetchone()
        if not wy:
            print("ERROR: User 'wy' not found. Run seed.py first.")
            return
        wy_id = wy["id"]
        node_ids = [n["id"] for n in nodes]

        # Find max display_number
        row = db.execute(
            "SELECT MAX(CAST(display_number AS INTEGER)) as mx FROM issues"
        ).fetchone()
        display_num = (row["mx"] or 0) + 1

        now = datetime.now(timezone.utc).isoformat()
        random.seed(99)
        created = 0

        # ────────────────────────────────────────────
        # 1. Group-label project issues (ongoing)
        # ────────────────────────────────────────────
        print("\n── Group-label projects ──")
        for proj in GROUP_PROJECTS:
            label = proj["label"]
            for topic, owner in proj["issues"]:
                wk_year, wk_num = 2026, random.randint(10, 14)
                wk_date = iso_week_to_date(wk_year, wk_num)
                jira = f"{random.choice(JIRA_PREFIXES)}-{random.randint(6000, 6999)}"

                created_at = datetime(
                    wk_date.year, wk_date.month, wk_date.day,
                    10, random.randint(0, 59), 0, tzinfo=timezone.utc
                ).isoformat()

                cur = db.execute(
                    """INSERT INTO issues
                       (display_number, topic, requestor_name,
                        owner_user_id, week_year, week_number, jira_ticket,
                        status, group_label, is_deleted, all_nodes_done,
                        created_at, created_by_user_id, updated_at, latest_update_at)
                       VALUES (?,?,?,?,?,?,?,?,?,0,0,?,?,?,?)""",
                    (str(display_num), topic, owner,
                     wy_id, wk_year, wk_num, jira,
                     "ongoing", label,
                     created_at, wy_id, now, now),
                )
                issue_id = cur.lastrowid

                # Random node states (some done, some developing, some empty)
                for nid in node_ids:
                    if random.random() < 0.3:
                        continue  # skip — leave some nodes empty
                    st = random.choice(["done", "developing", "uat", "tbd"])
                    cin = None
                    if st in ("done", "uat"):
                        ci = wk_date + timedelta(days=random.randint(3, 14))
                        cin = ci.isoformat()
                    db.execute(
                        """INSERT INTO issue_node_states
                           (issue_id, node_id, state, check_in_date,
                            updated_at, updated_by_user_id, updated_by_name_snapshot)
                           VALUES (?,?,?,?,?,?,?)""",
                        (issue_id, nid, st, cin, now, wy_id, "WY"),
                    )

                print(f"  #{display_num} [{label}] {topic}")
                display_num += 1
                created += 1

        # ────────────────────────────────────────────
        # 2. Multi-line JIRA issues (ongoing)
        # ────────────────────────────────────────────
        print("\n── Multi-line JIRA issues ──")
        for topic, owner, jira_multi in MULTI_JIRA_ISSUES:
            wk_year, wk_num = 2026, random.randint(12, 15)
            wk_date = iso_week_to_date(wk_year, wk_num)

            created_at = datetime(
                wk_date.year, wk_date.month, wk_date.day,
                11, random.randint(0, 59), 0, tzinfo=timezone.utc
            ).isoformat()

            cur = db.execute(
                """INSERT INTO issues
                   (display_number, topic, requestor_name,
                    owner_user_id, week_year, week_number, jira_ticket,
                    status, is_deleted, all_nodes_done,
                    created_at, created_by_user_id, updated_at, latest_update_at)
                   VALUES (?,?,?,?,?,?,?,?,0,0,?,?,?,?)""",
                (str(display_num), topic, owner,
                 wy_id, wk_year, wk_num, jira_multi,
                 "ongoing",
                 created_at, wy_id, now, now),
            )
            issue_id = cur.lastrowid

            for nid in node_ids:
                st = random.choice(["developing", "uat", "tbd", "done"])
                cin = None
                if st in ("done", "uat"):
                    ci = wk_date + timedelta(days=random.randint(3, 14))
                    cin = ci.isoformat()
                db.execute(
                    """INSERT INTO issue_node_states
                       (issue_id, node_id, state, check_in_date,
                        updated_at, updated_by_user_id, updated_by_name_snapshot)
                       VALUES (?,?,?,?,?,?,?)""",
                    (issue_id, nid, st, cin, now, wy_id, "WY"),
                )

            print(f"  #{display_num} JIRA: {jira_multi.replace(chr(10), ', ')}")
            display_num += 1
            created += 1

        # ────────────────────────────────────────────
        # 3. Old closed issues with sparse node states
        #    (simulates issues created before some nodes existed)
        # ────────────────────────────────────────────
        print("\n── Old closed issues (sparse nodes) ──")
        for topic, owner, wk_year, wk_num in OLD_CLOSED_ISSUES:
            wk_date = iso_week_to_date(wk_year, wk_num)
            jira = f"{random.choice(JIRA_PREFIXES)}-{random.randint(1000, 1999)}"

            created_at = datetime(
                wk_date.year, wk_date.month, wk_date.day,
                9, 0, 0, tzinfo=timezone.utc
            ).isoformat()
            closed_date = wk_date + timedelta(days=14)
            closed_at = datetime(
                closed_date.year, closed_date.month, closed_date.day,
                15, 0, 0, tzinfo=timezone.utc
            ).isoformat()

            cur = db.execute(
                """INSERT INTO issues
                   (display_number, topic, requestor_name,
                    owner_user_id, week_year, week_number, jira_ticket,
                    status, closed_at, closed_note,
                    is_deleted, all_nodes_done,
                    created_at, created_by_user_id, updated_at, latest_update_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,0,1,?,?,?,?)""",
                (str(display_num), topic, owner,
                 wy_id, wk_year, wk_num, jira,
                 "closed", closed_at, "Verified",
                 created_at, wy_id, now, now),
            )
            issue_id = cur.lastrowid

            # Only add states for the first 5-7 nodes (simulate old issues
            # that predate newer nodes)
            n_nodes_with_state = random.randint(4, 7)
            for nid in node_ids[:n_nodes_with_state]:
                st = random.choice(["done", "done", "done", "unneeded"])
                db.execute(
                    """INSERT INTO issue_node_states
                       (issue_id, node_id, state,
                        updated_at, updated_by_user_id, updated_by_name_snapshot)
                       VALUES (?,?,?,?,?,?)""",
                    (issue_id, nid, st, now, wy_id, "WY"),
                )

            print(f"  #{display_num} [closed wk{wk_year - 2020}{wk_num:02d}] {topic} ({n_nodes_with_state}/{len(node_ids)} nodes)")
            display_num += 1
            created += 1

        # ────────────────────────────────────────────
        # 4. A couple on_hold issues
        # ────────────────────────────────────────────
        print("\n── On Hold issues ──")
        on_hold_topics = [
            ("Supplier PCB revision pending", "Jack", 2026, 11),
            ("Regulatory approval waiting (FCC)", "Lisa", 2026, 13),
        ]
        for topic, owner, wk_year, wk_num in on_hold_topics:
            wk_date = iso_week_to_date(wk_year, wk_num)
            jira = f"{random.choice(JIRA_PREFIXES)}-{random.randint(7000, 7999)}"

            created_at = datetime(
                wk_date.year, wk_date.month, wk_date.day,
                10, 30, 0, tzinfo=timezone.utc
            ).isoformat()

            cur = db.execute(
                """INSERT INTO issues
                   (display_number, topic, requestor_name,
                    owner_user_id, week_year, week_number, jira_ticket,
                    status, is_deleted, all_nodes_done,
                    created_at, created_by_user_id, updated_at, latest_update_at)
                   VALUES (?,?,?,?,?,?,?,?,0,0,?,?,?,?)""",
                (str(display_num), topic, owner,
                 wy_id, wk_year, wk_num, jira,
                 "on_hold",
                 created_at, wy_id, now, now),
            )
            issue_id = cur.lastrowid

            for nid in node_ids:
                if random.random() < 0.4:
                    continue
                st = random.choice(["developing", "tbd"])
                db.execute(
                    """INSERT INTO issue_node_states
                       (issue_id, node_id, state,
                        updated_at, updated_by_user_id, updated_by_name_snapshot)
                       VALUES (?,?,?,?,?,?)""",
                    (issue_id, nid, st, now, wy_id, "WY"),
                )

            print(f"  #{display_num} [on_hold] {topic}")
            display_num += 1
            created += 1

        db.commit()

        print(f"\n  Total new issues created: {created}")
        print("  Features covered:")
        print("    - group_label projects: 強身健體系列 (5), Security Hardening (3)")
        print("    - multi-line JIRA: 4 issues")
        print("    - old closed with sparse nodes: 5 issues")
        print("    - on_hold: 2 issues")
        print("\nDone. Restart the dev server and check:")
        print("  - Tracker: group sections, inline edit, JIRA newlines, wk format")
        print("  - Closed: empty cells for missing nodes")


if __name__ == "__main__":
    main()
