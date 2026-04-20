# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project snapshot

Internal Flask web tool replacing an Excel-based Gitea meeting control table. About 300 issues × 9 nodes × 3 years of history. Taiwan team, Chinese UI. Small number of concurrent users on corporate intranet.

Tech stack: Python 3.12 · Flask 3 + Jinja2 · HTMX + Alpine.js (no build step, loaded from CDN) · Tabler CSS · SQLite (single file).

## Running & common commands

All commands assume the project venv. **Use `venv/bin/python`, not bare `python`** — the corporate dev environment has multiple Pythons and bare `python` is not guaranteed to point at the venv.

```bash
# First time / fresh DB
venv/bin/python init_db.py                # creates DB, runs schema.sql + migrate.py
venv/bin/python seed.py                   # default nodes + super user (wy / changeme)

# Run dev server
venv/bin/python main.py                   # http://127.0.0.1:9987  (port from .env)

# DB migrations
venv/bin/python migrate.py --list         # show applied vs pending
venv/bin/python migrate.py --dry-run      # preview without applying
venv/bin/python migrate.py                # apply pending

# Production upgrade (one-shot)
./deploy/migrate.sh                       # backup → stop → git pull → migrate → start

# Service control (no sudo, uses logs/app.pid)
./deploy/start.sh / stop.sh / status.sh
./deploy/backup.sh                        # DB .backup + attachments tar.gz into backups/
./deploy/restore.sh <db.bak> <attachments.tar.gz>
```

There is no test suite yet. `pytest` is not configured.

## Architecture essentials

**App factory + blueprints** (`app/__init__.py`): `create_app()` wires 5 blueprints — `auth`, `main`, `issues`, `admin`, `attachments`. Swagger UI at `/apidocs/`. All HTML responses are `Cache-Control: no-cache`; static assets are cache-busted via `?v=<mtime>` computed at startup (see the inject_dynamic_settings context processor).

**Reverse-proxy path prefix**: `BASE_URL` env var drives `_ScriptNameMiddleware` — the proxy strips the prefix before forwarding, but `url_for()` must still emit prefixed URLs. Don't hand-build URLs; always go through `url_for()`.

**Data layer**: `app/models/*.py` holds query helpers (issue / node / user / timeline / issue_node_state / setting). DB access goes through `app.db.get_db()` which caches one sqlite3 connection per request on Flask's `g`, with `row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`. **Do not open ad-hoc `sqlite3.connect()` inside request handlers** — the teardown hook won't close it.

**Row-level cache columns on `issues`**: `latest_update_at`, `all_nodes_done`, and the 4 per-field meta timestamps (`topic_updated_at` / `owner_updated_at` / `jira_updated_at` / `uat_path_updated_at`) are caches. `issue_model.refresh_cache()` recomputes `latest_update_at` + `all_nodes_done` after cell changes; the per-field timestamps are bumped by `issue_model.update_issue()` via the `FIELD_TO_TS` mapping — **don't bump `issues.updated_at` on pure cell-state changes** (that would pollute the Owner/JIRA/Path highlight).

**Timeline is the audit trail**: `timeline_entries` stores state_change / comment / meeting_note rows with before/after snapshots, author snapshot (name at the time), and optional `node_id`. Never mutate history; append new rows. Attachments hang off timeline entries via `attachments.timeline_entry_id`.

**Soft delete only**: `issues.is_deleted = 1`. All queries must filter `is_deleted = 0`. Hard DELETE is not used anywhere in app code.

**Version-diff highlight**: `users.last_viewed_at` is the per-user baseline. Tracker renders `cell-new-change` yellow when `cell.updated_at > last_viewed_at` or `issues.<field>_updated_at > last_viewed_at`. New users get `last_viewed_at = now()` at creation so their first page load isn't a wall of yellow.

## Migration system

DB schema evolves through numbered migrations in `migrations/NNN_<name>.py`, applied by `migrate.py`. Full SOP with rollback and notes is in **@deploy/MIGRATION_SOP.md** — read it before adding a new migration or debugging an existing one.

Rules that matter day-to-day:
- **Every migration `up()` must be idempotent** — check `PRAGMA table_info` before `ALTER`, use `CREATE IF NOT EXISTS`, gate `UPDATE`s on state. Re-running must be a no-op.
- **Do not commit inside `up()`** — the runner handles commit/rollback around each migration.
- **Schema changes require updating both `app/schema.sql` AND a new `migrations/NNN_*.py`** — `schema.sql` is the ground truth for fresh DBs; migrations evolve existing ones. Fresh `init_db.py` loads schema.sql then runs migrate.py (idempotent checks skip ALTERs, but versions still get recorded).
- **No `DROP COLUMN`, no column-type changes** — SQLite makes these painful. Additive only; for real restructures, do "new column → backfill → cut over → leave old column dormant".
- **Never touch `data/attachments/` or `attachments.stored_path` from a migration** — attachments are on-disk files. File moves are separate one-shot scripts, never part of DB migrations.

There is a separate legacy migration in `app/db.py::_run_migrations` that runs on every app startup (adds `pending_close`, `is_manager` columns if missing). It predates `migrate.py`. Don't add new migrations there — use `migrations/` going forward.

## Permissions & roles

Three levels, set on `users`: `is_super_user` > `is_manager` > regular. Plus per-node `groups` + `user_groups` + `group_nodes` for node-scoped edit rights.

- `@login_required` / `@optional_login` / `@super_user_required` decorators in `app/routes/auth.py`
- `@can_edit_node("node_id")` checks group membership for cell edits
- State-transition role gate in `app/routes/issues.py::_state_change_allowed`: **Done** → super user only, **Unneeded** → super user or manager, other states → any editor.

When adding new admin/manager-gated actions, put the gate at the route level, not inside helpers.

## Things that are decided — don't re-open

See @docs/handoff/07_design_decisions_qa.md for the full list. High-impact ones:

- **Node names are org-specific vocabulary** (`N4/N5`, `A10`, `MtM`, etc.) — don't "improve" them.
- **State transitions are free-form** — `UAT done → UAT` is legal (requirement walked back). Don't add ordering constraints.
- **Chinese UI is a requirement**, not a preference. Error messages, labels, placeholders are in Chinese. Keep new text in Chinese unless user-facing code is explicitly English-only.
- **Cache columns are deliberate** — main tracker view must be fast, so aggregate fields on `issues` are recomputed by model helpers (not by SQL views / triggers).
- **No sudo on deploy machines** — all tooling must live in user space, run from `$HOME`, no systemd. See `deploy/*.sh`.

## File/directory pointers

- Production SOP — @deploy/MIGRATION_SOP.md
- Deployment guide — @deploy/DEPLOY.md
- Full schema — @app/schema.sql
- Handoff package (business context, UI wireframes, phase plan) — `docs/handoff/` (start at `README.md`)
- CSS live-edit target — `app/static/css/app.css` (bump its mtime or edit via deploy to trigger cache-bust)

## Local development notes

- Port 9987 by default (set in `.env`). README says 5000 but that's stale — check `.env.example` or `config.py`.
- `data/gitea_tracker_bp.db` is an old manual backup, not the live DB. The live file is `data/gitea_tracker.db`.
- `data/tmp/` holds Excel upload staging files (cleaned periodically).
