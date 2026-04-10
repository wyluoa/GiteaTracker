# Gitea Tracker

Internal web tool for tracking Gitea meeting topics, replacing the existing
Excel-based control table.

**Current status: Phase 0 — project skeleton.** Only a placeholder homepage and
DB initialisation work. Real features come in Phase 1+.

## Tech stack

- Python 3.12
- Flask 3 + Jinja2 (server-side rendering)
- HTMX + Alpine.js (frontend interactions, no build step)
- Tabler CSS (UI framework, loaded from CDN)
- SQLite (single-file database)

## Setup

### 1. Clone and create a virtualenv

```bash
git clone <repo-url> gitea-tracker
cd gitea-tracker

# Use Python 3.12 (or 3.9/3.14 — but 3.12 is recommended)
python3.12 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure (optional)

Copy `.env.example` to `.env` and edit if you want to override defaults:

```bash
cp .env.example .env
# edit .env
```

The defaults work fine for local development — DB and attachments end up in
`data/`.

### 4. Initialise the database

```bash
python init_db.py
```

You should see something like:

```
Creating new DB at /path/to/data/gitea_tracker.db

Done. 11 tables present:
  - attachments
  - audit_log
  - groups
  - group_nodes
  - issue_node_states
  - issues
  - nodes
  - password_reset_tokens
  - settings
  - timeline_entries
  - user_groups
  - users
```

To wipe and recreate the DB (destructive):

```bash
python init_db.py --reset
```

### 5. Run the server

```bash
python main.py
```

Open <http://localhost:5000> in your browser. You should see the Phase 0
placeholder page with system status, table list, and two test buttons (Alpine.js
counter + HTMX ping).

## Project layout

```
gitea-tracker/
├── README.md
├── requirements.txt
├── config.py              # Configuration (reads env vars)
├── main.py                # Entry point: `python main.py`
├── init_db.py             # `python init_db.py` to create the DB
├── .env.example           # Copy to .env for local config
├── .gitignore
├── data/                  # DB file and attachments live here (gitignored)
└── app/
    ├── __init__.py        # Flask app factory
    ├── db.py              # SQLite connection helper
    ├── schema.sql         # All CREATE TABLE statements
    ├── routes/
    │   ├── __init__.py
    │   └── main.py        # Routes (Phase 0: placeholder only)
    ├── templates/
    │   ├── base.html      # Layout
    │   └── index.html     # Phase 0 placeholder
    └── static/
        ├── css/app.css
        └── js/
```

## Development phases

| Phase | Goal | Status |
|---|---|---|
| 0 | Project skeleton, DB init, placeholder page | ✅ done |
| 1 | Core data model + read-only main view + Excel import | next |
| 2 | Cell editing + timeline + meeting notes | |
| 3 | Account system + permissions + admin backend | |
| 4 | Attachments + diff highlighting + search/filter + export | |
| 5 | Dashboard + calendar + closed page + batch ops | |
| 6 | Polish + deployment + go-live | |
| 7 | Email reminders, weekly summary, etc. (post-launch) | |

## Phase 0 acceptance checklist

- [ ] `python init_db.py` runs without error and creates the DB file
- [ ] `python main.py` starts the server
- [ ] <http://localhost:5000> loads with green DB status
- [ ] All 12 tables show up as badges
- [ ] The "Alpine.js click" button counter increases when clicked
- [ ] The "HTMX ping" button populates the result span with `{"status": "ok"}`

If all six pass, Phase 0 is done.
