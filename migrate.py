"""
Migration runner — applies pending schema migrations from migrations/.

Usage:
    venv/bin/python migrate.py              # apply all pending migrations
    venv/bin/python migrate.py --list       # show status of every migration
    venv/bin/python migrate.py --dry-run    # preview pending without applying

Migration file convention:
    migrations/NNN_short_name.py
        SCHEMA_VERSION = "NNN"
        DESCRIPTION    = "<one-line summary>"
        def up(conn): ...   # must be idempotent

Design notes:
    - schema_version table records which migrations have been applied.
    - Each migration must be idempotent so re-running on an already-migrated
      DB is a no-op (protects against crash mid-run or accidental re-execution).
    - No down-scripts: rollback is done via deploy/restore.sh (DB backup).
"""
import argparse
import importlib.util
import io
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure stdout/stderr can emit non-ASCII (em-dashes, Chinese descriptions, etc.).
# On hosts with LANG=C / POSIX locale, Python defaults stdout to ascii or latin-1
# and every print() of an em-dash ('\u2014') blows up the deploy with
# UnicodeEncodeError: 'latin-1' codec can't encode character '\u2014'.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if _stream.encoding and _stream.encoding.lower() not in ("utf-8", "utf8"):
        setattr(sys, _stream_name,
                io.TextIOWrapper(_stream.buffer, encoding="utf-8", errors="replace"))

from config import Config

BASE_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = BASE_DIR / "migrations"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _connect():
    db_path = Path(Config.DB_PATH)
    if not db_path.exists():
        print(f"ERROR: DB not found at {db_path}. Run init_db.py first.")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_version_table(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_version (
             version     TEXT PRIMARY KEY,
             applied_at  TEXT NOT NULL,
             description TEXT
           )"""
    )
    conn.commit()


def _applied(conn):
    cur = conn.execute("SELECT version, applied_at FROM schema_version")
    return {r[0]: r[1] for r in cur.fetchall()}


def _load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _discover():
    """Return [(version, path, module), ...] sorted by version."""
    files = sorted(
        p for p in MIGRATIONS_DIR.glob("[0-9]*.py") if p.name != "__init__.py"
    )
    out = []
    for p in files:
        mod = _load(p)
        v = getattr(mod, "SCHEMA_VERSION", None)
        if not v:
            print(f"WARN: {p.name} missing SCHEMA_VERSION, skipping")
            continue
        prefix = p.name.split("_", 1)[0]
        if v != prefix:
            print(f"WARN: {p.name} SCHEMA_VERSION={v} mismatches filename prefix {prefix}")
        out.append((v, p, mod))
    return out


def run(dry_run=False):
    conn = _connect()
    try:
        _ensure_version_table(conn)
        applied = _applied(conn)
        migrations = _discover()
        pending = [(v, p, m) for v, p, m in migrations if v not in applied]

        if not pending:
            print("DB is up to date. No migrations to run.")
            return

        print(f"Found {len(pending)} pending migration(s):")
        for v, p, m in pending:
            desc = getattr(m, "DESCRIPTION", "")
            print(f"  {v}  {p.name}  {desc}")

        if dry_run:
            print("\n(dry-run — no changes applied)")
            return

        for v, p, mod in pending:
            print(f"\nApplying {v} ({p.name})...")
            try:
                mod.up(conn)
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at, description)"
                    " VALUES (?, ?, ?)",
                    (v, _now(), getattr(mod, "DESCRIPTION", None)),
                )
                conn.commit()
                print(f"  OK — {v} applied")
            except Exception as e:
                conn.rollback()
                print(f"  FAIL — {v} rolled back: {e}")
                print("Migration aborted. Fix the issue (or restore from backup) and re-run.")
                sys.exit(1)

        print(f"\nDone. {len(pending)} migration(s) applied.")
    finally:
        conn.close()


def list_status():
    conn = _connect()
    try:
        _ensure_version_table(conn)
        applied = _applied(conn)
        migrations = _discover()
        print(f"{'Version':<8} {'Status':<9} {'Applied At':<32} Description")
        print("-" * 90)
        for v, p, mod in migrations:
            status = "applied" if v in applied else "pending"
            at = applied.get(v, "-")
            desc = getattr(mod, "DESCRIPTION", "")
            print(f"{v:<8} {status:<9} {at:<32} {desc}")
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="Gitea Tracker DB migration runner")
    ap.add_argument("--list", action="store_true", help="list migrations + status")
    ap.add_argument("--dry-run", action="store_true", help="show pending without applying")
    args = ap.parse_args()

    if args.list:
        list_status()
    else:
        run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
