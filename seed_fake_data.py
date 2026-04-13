"""
Seed script — generate fake closed & ongoing issues for dashboard demo.

Creates ~100 issues across wk2026-01 to wk2026-15 with ~46% closing rate.
Phases: Close, UAT, Dev, TBD distributed realistically.

Usage:
    python seed_fake_data.py
"""
import sys
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta, date

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app
from app.db import get_db

TOPICS = [
    "OLED panel flicker fix", "Battery drain on standby mode",
    "Touchscreen calibration offset", "Wi-Fi 6E antenna tuning",
    "Camera module white balance", "Fingerprint sensor latency",
    "NFC payment timeout issue", "Speaker distortion at max volume",
    "GPS signal drift indoors", "Bluetooth codec negotiation",
    "Display color accuracy calibration", "USB-C PD charging profile",
    "Accelerometer noise filtering", "Proximity sensor false trigger",
    "Ambient light sensor range", "Haptic feedback motor tuning",
    "Thermal throttling threshold", "Memory leak in camera service",
    "Audio routing during calls", "Screen rotation delay fix",
    "Fast charging compatibility", "Wireless charging alignment",
    "Power button double-tap", "Volume rocker sensitivity",
    "Boot animation optimization", "Factory reset data wipe",
    "OTA update package signing", "Baseband firmware update",
    "SIM tray detection logic", "eSIM provisioning flow",
    "Dark mode rendering fix", "Font scaling accessibility",
    "Notification LED pattern", "Always-on display burn-in",
    "Under-display camera quality", "Macro lens autofocus speed",
    "Night mode noise reduction", "Video stabilization EIS",
    "Slow-motion frame interpolation", "HDR tone mapping pipeline",
    "5G band switching logic", "VoLTE codec fallback",
    "WiFi calling handoff", "DNS-over-HTTPS config",
    "VPN split tunnel support", "App install verification",
    "Storage encryption migration", "Biometric auth timeout",
    "Location permission prompt", "Background app battery limit",
    "Adaptive brightness curve", "Refresh rate auto-switch",
    "Gesture navigation tuning", "Multi-window resize handle",
    "PIP mode aspect ratio", "Clipboard privacy warning",
    "Keyboard haptic latency", "Auto-rotate debounce fix",
    "Screenshot capture delay", "Screen recorder audio sync",
]

OWNERS = ["WY", "Kevin", "Jack", "Lisa", "Amy", "Tom", "Eric", "Vivian"]
JIRA_PREFIXES = ["PROJ", "HW", "SW", "FW"]


def iso_week_to_date(year, week, weekday=1):
    """Convert ISO year/week/weekday to a date. weekday: 1=Mon."""
    jan4 = date(year, 1, 4)
    start = jan4 - timedelta(days=jan4.isoweekday() - 1)
    return start + timedelta(weeks=week - 1, days=weekday - 1)


def main():
    app = create_app()
    with app.app_context():
        db = get_db()

        existing = db.execute("SELECT COUNT(*) as cnt FROM issues").fetchone()["cnt"]
        if existing > 10:
            print(f"Already {existing} issues in DB. Skipping fake data.")
            print("Use 'python init_db.py --reset && python seed.py' to start fresh.")
            return

        nodes = db.execute(
            "SELECT * FROM nodes WHERE is_active = 1 ORDER BY sort_order"
        ).fetchall()
        if not nodes:
            print("ERROR: No nodes found. Run seed.py first.")
            return

        wy = db.execute("SELECT id FROM users WHERE username = 'wy'").fetchone()
        if not wy:
            print("ERROR: User 'wy' not found. Run seed.py first.")
            return
        wy_id = wy["id"]
        node_ids = [n["id"] for n in nodes]

        # Find max existing display_number
        row = db.execute(
            "SELECT MAX(CAST(display_number AS INTEGER)) as mx FROM issues"
        ).fetchone()
        start_num = (row["mx"] or 0) + 1

        random.seed(42)

        # ── Plan issues per week ──
        # Weeks 01-05 (old):  ~8/wk, ~65% closed
        # Weeks 06-10 (mid):  ~7/wk, ~43% closed
        # Weeks 11-15 (recent): ~5/wk, ~24% closed
        # Total ≈ 100, close rate ≈ 46%

        WEEK_PLAN = [
            # (week, count, closed_pct)
            (1,  8, 0.63), (2,  9, 0.67), (3,  8, 0.63), (4,  7, 0.71), (5, 8, 0.63),
            (6,  7, 0.43), (7,  7, 0.43), (8,  6, 0.50), (9,  7, 0.43), (10, 8, 0.38),
            (11, 5, 0.20), (12, 6, 0.17), (13, 5, 0.20), (14, 5, 0.20), (15, 4, 0.25),
        ]

        now = datetime.now(timezone.utc).isoformat()
        display_num = start_num
        counts = {"closed": 0, "uat": 0, "developing": 0, "tbd": 0}

        for wk_num, n_issues, closed_pct in WEEK_PLAN:
            n_closed = round(n_issues * closed_pct)

            # Distribute remaining among phases
            remaining = n_issues - n_closed
            if wk_num <= 5:
                # Old: mostly UAT
                n_uat = max(1, round(remaining * 0.6))
                n_dev = remaining - n_uat
                n_tbd = 0
            elif wk_num <= 10:
                # Mid: mix
                n_uat = max(1, round(remaining * 0.3))
                n_dev = max(1, round(remaining * 0.4))
                n_tbd = remaining - n_uat - n_dev
            else:
                # Recent: mostly TBD/Dev
                n_uat = 0 if remaining <= 2 else 1
                n_dev = max(1, round((remaining - n_uat) * 0.4))
                n_tbd = remaining - n_uat - n_dev

            phases = (
                ["closed"] * n_closed +
                ["uat"] * n_uat +
                ["developing"] * n_dev +
                ["tbd"] * max(0, n_tbd)
            )
            # Pad/trim
            while len(phases) < n_issues:
                phases.append("tbd")
            phases = phases[:n_issues]
            random.shuffle(phases)

            wk_date = iso_week_to_date(2026, wk_num)

            for phase in phases:
                created_at = datetime(
                    wk_date.year, wk_date.month, wk_date.day,
                    9, random.randint(0, 59), 0, tzinfo=timezone.utc
                ).isoformat()

                topic = random.choice(TOPICS)
                owner = random.choice(OWNERS)
                jira = f"{random.choice(JIRA_PREFIXES)}-{random.randint(1000, 9999)}"

                status = "closed" if phase == "closed" else "ongoing"
                closed_at = None
                if status == "closed":
                    delay = random.randint(7, 35)
                    cd = wk_date + timedelta(days=delay)
                    closed_at = datetime(
                        cd.year, cd.month, cd.day, 15, 0, 0, tzinfo=timezone.utc
                    ).isoformat()

                cur = db.execute(
                    """INSERT INTO issues
                       (display_number, topic, requestor_name,
                        owner_user_id, week_year, week_number, jira_ticket,
                        status, closed_at, closed_note,
                        is_deleted, all_nodes_done,
                        created_at, created_by_user_id, updated_at, latest_update_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?)""",
                    (str(display_num), topic, owner,
                     wy_id, 2026, wk_num, jira,
                     status, closed_at,
                     "Verified and closed" if status == "closed" else None,
                     1 if status == "closed" else 0,
                     created_at, wy_id, now, now),
                )
                issue_id = cur.lastrowid

                # ── Node states ──
                for nid in node_ids:
                    if phase == "closed":
                        st = "done"
                    elif phase == "uat":
                        st = random.choices(
                            ["done", "uat", "uat_done"],
                            weights=[0.55, 0.30, 0.15],
                        )[0]
                    elif phase == "developing":
                        st = random.choices(
                            ["done", "developing", "tbd"],
                            weights=[0.25, 0.55, 0.20],
                        )[0]
                    else:  # tbd
                        st = random.choices(
                            ["tbd", None],
                            weights=[0.7, 0.3],
                        )[0]

                    if st:
                        cin = None
                        if st in ("done", "uat_done", "uat"):
                            ci = wk_date + timedelta(days=random.randint(3, 21))
                            cin = ci.isoformat()
                        db.execute(
                            """INSERT INTO issue_node_states
                               (issue_id, node_id, state, check_in_date,
                                updated_at, updated_by_user_id,
                                updated_by_name_snapshot)
                               VALUES (?,?,?,?,?,?,?)""",
                            (issue_id, nid, st, cin, now, wy_id, "WY"),
                        )

                counts[phase] += 1
                display_num += 1

        db.commit()

        total = sum(counts.values())
        rate = counts["closed"] / total * 100
        print(f"\nFake data created:")
        print(f"  Closed:     {counts['closed']}")
        print(f"  UAT:        {counts['uat']}")
        print(f"  Developing: {counts['developing']}")
        print(f"  TBD:        {counts['tbd']}")
        print(f"  Total:      {total}")
        print(f"  Close rate: {rate:.1f}%")


if __name__ == "__main__":
    main()
