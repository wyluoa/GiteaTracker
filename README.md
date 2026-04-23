# Gitea Tracker

Internal web tool for tracking Gitea meeting topics, replacing the existing
Excel-based control table.

## Tech stack

- Python 3.12
- Flask 3 + Jinja2 (server-side rendering)
- HTMX + Alpine.js (frontend interactions, no build step)
- Tabler CSS (UI framework, loaded from CDN)
- SQLite (single-file database)

## Quick start (local development)

**bash：**

```bash
git clone https://github.com/wyluoa/GiteaTracker.git
cd GiteaTracker
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt
cp .env.example .env        # edit if needed; defaults work for local dev
python init_db.py && python seed.py
python main.py
```

**csh / tcsh：**

```csh
git clone https://github.com/wyluoa/GiteaTracker.git
cd GiteaTracker
python3 -m venv venv
source venv/bin/activate.csh
pip install --upgrade pip && pip install -r requirements.txt
cp .env.example .env        # edit if needed; defaults work for local dev
python init_db.py && python seed.py
python main.py
```

Open <http://localhost:9987> (port configured in `.env`). Default super user: `wy` / `changeme`.

Run the test suite any time:

```bash
venv/bin/pytest -q     # ~20s, no external services required
```

## Production deployment

See **[deploy/DEPLOY.md](deploy/DEPLOY.md)** for the full deployment guide
covering start/stop scripts, backup/restore, and upgrade procedures. No sudo required.

## Features

- **Tracker** — week-grouped table with colored status cells, red line display, side panel editing
- **Changes summary** (`/changes`) — aggregated view of all changes since last visit, with severity flags (red-line above / regression / check-in delay) and per-node filter
- **Dashboard** — per-node summary cards with red-line-above counts
- **Calendar** — monthly view of check-in dates with quick-done buttons
- **Meeting mode** — batch meeting note entry per week
- **Closed issues** — paginated list with search and reopen (super user)
- **Excel update** — upload new Excel to update data with diff preview and conflict detection (admin)
- **Admin backend** — user approval, groups, nodes, red line, SMTP, Excel update, audit log, error log
- **Accounts** — registration, login, forgot password, role-based permissions
- **Attachments** — file upload (png/jpg/pdf) with timeline display
- **Version diff** — yellow highlight for changes since last viewed
- **Search & filter** — keyword search, owner/state/week filters, advanced multi-filter
- **Export Excel** — download current view as .xlsx
- **Batch operations** — checkbox select + bulk state change
- **Soft delete** — super user only, with audit trail
- **CSRF protection** — all mutating routes gated (no new deps, pure `itsdangerous`)
- **Structured error log** — 500s append to `logs/errors.jsonl`; admin viewer at `/admin/errors`
- **Test suite** — pytest, 86+ tests, no external services

## Development phases

| Phase | Goal | Status |
|---|---|---|
| 0 | Project skeleton, DB init | done |
| 1 | Core data model + read-only main view + Excel import | done |
| 2 | Cell editing + timeline + meeting notes | done |
| 3 | Account system + permissions + admin backend | done |
| 4 | Attachments + diff highlighting + search/filter + export | done |
| 4.5 | Advanced filters + live cell sync + table UX | done |
| 5 | Dashboard + calendar + closed page + batch ops | done |
| 6 | Error pages + soft delete + deploy config + UX fixes | done |
| 6.5 | Excel upload update with diff preview (admin) | done |
| 7 | Email reminders, weekly summary, Gitea API, etc. | post-launch |

## Project layout

```
GiteaTracker/
├── main.py                # Entry point
├── config.py              # Configuration (reads env vars)
├── init_db.py             # Database initialization
├── migrate.py             # Migration runner (applies migrations/NNN_*.py)
├── seed.py                # Seed default nodes + super user
├── import_from_excel.py   # Excel import script
├── requirements.txt       # Includes pytest for tests
├── pytest.ini             # Test config
├── app/
│   ├── __init__.py        # Flask app factory
│   ├── db.py              # SQLite connection helper
│   ├── csrf.py            # CSRF protection (per-session token)
│   ├── errors.py          # Error handlers + logs/errors.jsonl writer
│   ├── excel.py           # Shared Excel parsing utilities
│   ├── schema.sql         # CREATE TABLE statements
│   ├── models/            # Data access layer (includes changes_summary)
│   ├── routes/            # Flask blueprints
│   ├── templates/         # Jinja2 templates
│   └── static/            # CSS, JS
├── migrations/            # Numbered DB migrations (NNN_*.py)
├── tests/                 # Pytest suite
├── scripts/               # Dev helpers (e.g. seed_simulated_changes.py)
├── data/                  # DB + attachments (gitignored)
├── deploy/                # start/stop, backup/restore, DEPLOY.md, releases/
├── docs/                  # Handoff + in-app HTML guides
└── samples/               # Sample Excel file
```
