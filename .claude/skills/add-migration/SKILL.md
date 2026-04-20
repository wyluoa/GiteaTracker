---
name: add-migration
description: 新增一個 DB migration 檔案，依 deploy/MIGRATION_SOP.md 的模板與檢查表。
allowed-tools: Read Write Edit Bash Grep Glob
---

# /add-migration

建立新的 migration 檔。完整規範見 @deploy/MIGRATION_SOP.md「新增 Migration」章節。

## 流程

### 1. 取得使用者需求
問清楚：
- 要改什麼（加欄位 / 加表 / 加 index / 回填資料 / ...）
- 哪個 table
- 既有資料要不要 backfill，用什麼規則

**若是 SQLite 不支援的改動**（DROP COLUMN、改欄位型別、改 constraint），先告訴使用者替代方案（新欄位 + 複製 + 切換），讓使用者確認再動手。

### 2. 決定編號
```bash
ls migrations/[0-9]*.py 2>/dev/null | sort | tail -1
```
看到最後一個就 +1。維持三位數（`001`、`002`、...、`099`、`100`）。

### 3. 建檔
路徑：`migrations/<NNN>_<short_snake_name>.py`

模板：
```python
"""<一句話說明這個 migration 做什麼 + 為什麼，動機比手段重要>"""

SCHEMA_VERSION = "<NNN>"   # 和檔名前綴一致
DESCRIPTION = "<一行描述，會顯示在 migrate.py --list>"


def up(conn):
    # ⚠️ 必須冪等 — 跑 N 次和跑 1 次等效
    # 只讀取和寫入 conn，不要 conn.commit()（runner 會處理）
    cur = conn.execute("PRAGMA table_info(<table>)")
    existing = {row[1] for row in cur.fetchall()}
    if "<new_col>" not in existing:
        conn.execute("ALTER TABLE <table> ADD COLUMN <new_col> <TYPE>")
        # Backfill：若要預設值用邏輯產生，寫在這裡
        conn.execute("UPDATE <table> SET <new_col> = ? WHERE <new_col> IS NULL", (<default>,))
```

### 4. 同步 `app/schema.sql`
若是新欄位 / 新表，**一定要**在 `app/schema.sql` 裡也加上 — fresh DB 靠 schema.sql 一次到位，既有 DB 靠 migration 補。兩者都要有才會對稱。

找到對應的 `CREATE TABLE` 區塊，加上欄位（注意 SQL 語法）：
```sql
CREATE TABLE IF NOT EXISTS <table> (
    ...
    <new_col>  <TYPE>    -- 加在對應位置
);
```

### 5. 本機測試（一定要做）
```bash
# 在 /tmp 複本測，不動正式 DB
cp data/gitea_tracker.db /tmp/migtest.db
DB_PATH=/tmp/migtest.db venv/bin/python migrate.py --list
DB_PATH=/tmp/migtest.db venv/bin/python migrate.py --dry-run
DB_PATH=/tmp/migtest.db venv/bin/python migrate.py
# 冪等性驗證：再跑一次，應該 no-op
DB_PATH=/tmp/migtest.db venv/bin/python migrate.py
```
第二次執行必須輸出 `DB is up to date. No migrations to run.`，這才證明是冪等的。

### 6. Fresh DB 驗證
確認 schema.sql 的變更能讓全新 DB 跑起來：
```bash
rm -f /tmp/fresh.db
DB_PATH=/tmp/fresh.db venv/bin/python init_db.py
DB_PATH=/tmp/fresh.db venv/bin/python migrate.py --list    # 應該全部 applied
```

### 7. Commit
用專門的 commit message 格式：
```
migrate(<NNN>): <short description>

<body — 解釋 why 和 how backfill>
```
只把 migration 相關的檔案放進去：`migrations/<NNN>_*.py` + `app/schema.sql` 的那段變更。**不要**把其他 app 改動混進來。

## 冪等性檢查清單

寫完 `up()` 問自己這四個問題，都是「是」才算過關：

- [ ] 加欄位前有 `PRAGMA table_info` 檢查？
- [ ] 加表用 `CREATE TABLE IF NOT EXISTS`？
- [ ] 加 index 用 `CREATE INDEX IF NOT EXISTS`？
- [ ] UPDATE / INSERT 有條件避免覆蓋已處理的 row（例如 `WHERE col IS NULL`）？

## 不要做的事

- ❌ `conn.commit()` 放在 `up()` 裡（會搞壞 runner 的 rollback）
- ❌ 一次做多個不相關的改動（一個 migration 解一個問題）
- ❌ 直接動 `data/attachments/` 檔案（attachment 永遠不走 migration）
- ❌ `DROP COLUMN` / 改欄位型別（SQLite 會痛苦，走「新欄位 + 切換」）
- ❌ 在 migration 裡 import app code（會引入啟動時副作用）— 只用 `sqlite3` 和 stdlib

## 參考
- 完整 SOP：@deploy/MIGRATION_SOP.md
- 現有範例：`migrations/001_issue_meta_timestamps.py`（加欄位 + 回填）、`migrations/002_baseline_last_viewed_at.py`（純資料更新）
