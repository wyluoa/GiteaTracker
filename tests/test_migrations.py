"""
Migration safety tests — every migration must be idempotent.

Why it matters: MIGRATION_SOP.md makes idempotency a rule because
restores + partial failures force us to re-run migrations. A migration
that is NOT idempotent silently corrupts state. These tests make the
rule enforceable.

Strategy: spin up a tmp DB from schema.sql, run migrate() once, take a
schema snapshot, run migrate() again, verify nothing changed — neither
schema shape nor schema_version rows (beyond what was already applied).
"""
import importlib.util
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MIG_DIR = ROOT / "migrations"
SCHEMA_PATH = ROOT / "app" / "schema.sql"


def _schema_snapshot(db_path):
    """Return a string representing the full schema (tables + columns + indexes)
    so two snapshots can be compared by string equality."""
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {}
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ):
            name = r[0]
            cols = conn.execute(f"PRAGMA table_info({name})").fetchall()
            tables[name] = [(c[1], c[2], c[3], c[5]) for c in cols]  # name, type, notnull, pk
        indexes = sorted(r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ))
        return repr((tables, indexes))
    finally:
        conn.close()


def _row_counts(db_path, tables):
    conn = sqlite3.connect(str(db_path))
    try:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    finally:
        conn.close()


def test_fresh_db_has_all_migrations_applied_after_init(tmp_db_path, monkeypatch):
    """init_db.py pattern: schema.sql + migrate.py → every migration ends up
    in schema_version even when idempotent ALTERs are no-ops."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(tmp_db_path))
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()

    from config import Config
    monkeypatch.setattr(Config, "DB_PATH", str(tmp_db_path))

    from migrate import run as run_migrations
    run_migrations()

    expected = {p.name.split("_", 1)[0]
                for p in MIG_DIR.glob("[0-9]*.py")}
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    finally:
        conn.close()
    assert expected <= applied, f"missing versions: {expected - applied}"


def test_migrate_run_twice_is_noop(tmp_db_path, monkeypatch):
    """Idempotency rule: after one full migrate, a second migrate
    must not change schema OR add duplicate version rows."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(tmp_db_path))
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()

    from config import Config
    monkeypatch.setattr(Config, "DB_PATH", str(tmp_db_path))
    from migrate import run as run_migrations

    run_migrations()                          # first pass
    snap1 = _schema_snapshot(tmp_db_path)
    # Take row count of schema_version
    conn = sqlite3.connect(str(tmp_db_path))
    v_count_1 = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    conn.close()

    run_migrations()                          # second pass
    snap2 = _schema_snapshot(tmp_db_path)
    conn = sqlite3.connect(str(tmp_db_path))
    v_count_2 = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    conn.close()

    assert snap1 == snap2, "schema changed between two full migrate() runs"
    assert v_count_1 == v_count_2, "schema_version grew on second run"


# ─── Per-migration idempotency ────────────────────────────────────────

def _load_migration(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "migration_path",
    sorted(MIG_DIR.glob("[0-9]*.py")),
    ids=lambda p: p.name,
)
def test_each_migration_up_is_idempotent(migration_path, tmp_db_path):
    """Run schema.sql → up() once → snapshot → up() again → snapshot must match.

    Catches the classic bug: ALTER TABLE without PRAGMA-guard, INSERT
    without conflict guard, UPDATE without WHERE clause that re-overwrites.
    """
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(tmp_db_path))
    conn.executescript(schema_sql)
    conn.commit()
    # A minimum of 1 row in tables commonly touched by migrations,
    # so UPDATE-in-migration code paths exercise themselves.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO users (username, email, display_name, password_hash,
                              status, is_super_user, is_manager,
                              last_viewed_at, created_at, updated_at)
           VALUES ('u', 'u@x', 'U', 'hash', 'active', 0, 0, ?, ?, ?)""",
        (now, now, now),
    )
    conn.execute(
        """INSERT INTO issues (display_number, topic, week_year, week_number,
                                status, created_at, updated_at, latest_update_at,
                                topic_updated_at, owner_updated_at, jira_updated_at,
                                uat_path_updated_at)
           VALUES ('T1', 'x', 2024, 40, 'ongoing', ?, ?, ?, ?, ?, ?, ?)""",
        (now, now, now, now, now, now, now),
    )
    conn.commit()

    mod = _load_migration(migration_path)
    mod.up(conn)
    conn.commit()

    tables_for_counts = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )]
    conn.close()

    snap1 = _schema_snapshot(tmp_db_path)
    counts1 = _row_counts(tmp_db_path, tables_for_counts)

    # Second run — should be a no-op
    conn = sqlite3.connect(str(tmp_db_path))
    mod.up(conn)
    conn.commit()
    conn.close()

    snap2 = _schema_snapshot(tmp_db_path)
    counts2 = _row_counts(tmp_db_path, tables_for_counts)

    assert snap1 == snap2, f"{migration_path.name} changed schema on 2nd run"
    assert counts1 == counts2, f"{migration_path.name} changed row counts on 2nd run: {counts1} → {counts2}"


def test_every_migration_has_required_metadata():
    """Each migration file MUST declare SCHEMA_VERSION + DESCRIPTION,
    and the version prefix must match the filename. This is what migrate.py
    uses to detect + report migrations."""
    for path in sorted(MIG_DIR.glob("[0-9]*.py")):
        mod = _load_migration(path)
        assert hasattr(mod, "SCHEMA_VERSION"), f"{path.name}: missing SCHEMA_VERSION"
        assert hasattr(mod, "DESCRIPTION"),    f"{path.name}: missing DESCRIPTION"
        assert hasattr(mod, "up"),             f"{path.name}: missing up(conn)"
        prefix = path.name.split("_", 1)[0]
        assert mod.SCHEMA_VERSION == prefix, \
            f"{path.name}: SCHEMA_VERSION={mod.SCHEMA_VERSION} != filename prefix {prefix}"
