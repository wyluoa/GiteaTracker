"""
Initialise the SQLite database from schema.sql.

Usage:
    python init_db.py            # create DB if it doesn't exist
    python init_db.py --reset    # drop existing DB and recreate (DESTRUCTIVE)
"""
import argparse
import sqlite3
import sys
from pathlib import Path

from config import Config


def main():
    parser = argparse.ArgumentParser(description="Initialise the Gitea Tracker database")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop existing DB file and recreate. DESTRUCTIVE.",
    )
    args = parser.parse_args()

    db_path = Path(Config.DB_PATH)
    schema_path = Path(__file__).parent / "app" / "schema.sql"

    if not schema_path.exists():
        print(f"ERROR: schema.sql not found at {schema_path}")
        sys.exit(1)

    # Make sure the data directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    Path(Config.ATTACHMENT_DIR).mkdir(parents=True, exist_ok=True)

    if args.reset and db_path.exists():
        confirm = input(f"WARNING: This will delete {db_path}. Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)
        db_path.unlink()
        print(f"Deleted {db_path}")

    if db_path.exists():
        print(f"DB file already exists at {db_path}")
        print("Running schema.sql anyway (uses CREATE TABLE IF NOT EXISTS, so it's safe).")
    else:
        print(f"Creating new DB at {db_path}")

    schema_sql = schema_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()

        # Report what was created
        cur = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
        tables = [row[0] for row in cur.fetchall()]
        print(f"\nSchema loaded. {len(tables)} tables present:")
        for t in tables:
            print(f"  - {t}")
    finally:
        conn.close()

    # Apply any pending data migrations (also bootstraps schema_version table
    # so future `migrate.py` runs skip already-applied migrations). Idempotent.
    print("\nRunning migrations...")
    from migrate import run as run_migrations
    run_migrations()


if __name__ == "__main__":
    main()
