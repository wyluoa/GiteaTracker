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

```bash
# 1. Clone and create virtualenv
git clone https://github.com/wyluoa/GiteaTracker.git
cd GiteaTracker
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Configure (optional)
cp .env.example .env   # edit if needed; defaults work for local dev

# 4. Initialize database and seed data
python init_db.py
python seed.py

# 5. Import Excel data (optional)
python import_from_excel.py --file samples/tracker.xlsx

# 6. Run
python main.py
```

Open <http://localhost:5000>. Default super user: `wy` / `changeme`.

## Production deployment

See **[deploy/DEPLOY.md](deploy/DEPLOY.md)** for the full Linux deployment guide
covering systemd, Nginx reverse proxy, backup/restore, and upgrade procedures.

## Features

- **Tracker** — week-grouped table with colored status cells, red line display, side panel editing
- **Dashboard** — per-node summary cards with red-line-above counts
- **Calendar** — monthly view of check-in dates with quick-done buttons
- **Meeting mode** — batch meeting note entry per week
- **Closed issues** — paginated list with search and reopen (super user)
- **Admin backend** — user approval, groups, nodes, red line, SMTP, audit log
- **Accounts** — registration, login, forgot password, role-based permissions
- **Attachments** — file upload (png/jpg/pdf) with timeline display
- **Version diff** — yellow highlight for changes since last viewed
- **Search & filter** — keyword search, owner/state/week filters, advanced multi-filter
- **Export Excel** — download current view as .xlsx
- **Batch operations** — checkbox select + bulk state change
- **Soft delete** — super user only, with audit trail

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
| 7 | Email reminders, weekly summary, Gitea API, etc. | post-launch |

## Project layout

```
GiteaTracker/
├── main.py                # Entry point
├── config.py              # Configuration (reads env vars)
├── init_db.py             # Database initialization
├── seed.py                # Seed default nodes + super user
├── import_from_excel.py   # Excel import script
├── requirements.txt
├── app/
│   ├── __init__.py        # Flask app factory
│   ├── db.py              # SQLite connection helper
│   ├── schema.sql         # CREATE TABLE statements
│   ├── models/            # Data access layer
│   ├── routes/            # Flask blueprints
│   ├── templates/         # Jinja2 templates
│   └── static/            # CSS, JS
├── data/                  # DB + attachments (gitignored)
├── deploy/                # systemd, nginx, backup/restore, DEPLOY.md
├── docs/                  # Handoff documents and references
└── samples/               # Sample Excel file
```
