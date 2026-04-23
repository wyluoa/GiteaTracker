# Gitea Tracker — Migration SOP

部署新版本（含程式碼 + DB schema 變動）的標準流程。適用於正式機器，也適用於 staging / 本機驗證。

---

## TL;DR

```bash
cd ~/GiteaTracker         # 或 app 實際路徑
./deploy/migrate.sh       # 一鍵：backup → stop → pull → migrate → start
```

失敗時回滾：

```bash
./deploy/stop.sh || true
./deploy/restore.sh backups/gitea_tracker_<TIMESTAMP>.db backups/attachments_<TIMESTAMP>.tar.gz
git checkout <前一個 commit hash>
./deploy/start.sh
```

---

## 正式部署 SOP

### 前置準備（第一次使用才做）

1. **確認 deploy 腳本可執行**
   ```bash
   chmod +x deploy/migrate.sh deploy/backup.sh deploy/verify_backup.sh \
            deploy/restore.sh deploy/start.sh deploy/stop.sh
   ```
2. **確認 `backups/` 目錄存在並有寫入權限**（`backup.sh` 會自動建立）
3. **備份不再依賴 `sqlite3` CLI**：`backup.sh` 從 2026-04-24 版起改用
   Python `sqlite3.backup()`，機器沒裝 `sqlite3` 指令也能跑。
4. **如果是第一次升到有 `migrate.py` 的版本**：`deploy/migrate.sh` 會自動
   bootstrap `schema_version` 表，不用額外動作。

### 正式升版流程

**Step 0 — 升版前確認**
- [ ] 看一下 **`deploy/releases/YYYY-MM-DD-*.md`** 是否有這次版本的專屬說明
- [ ] 本機已測過這次變動（可以 `cp data/gitea_tracker.db /tmp/t.db && DB_PATH=/tmp/t.db venv/bin/python migrate.py --dry-run` 模擬）
- [ ] 跑 `venv/bin/pytest -q`，全綠才繼續
- [ ] 通知使用者升版時段（會停機 10~30 秒）
- [ ] 確認有可用的 `backups/` 磁碟空間（至少 DB + 1 個 attachments tar.gz 大小）
- [ ] 若 `requirements.txt` 有變動：手動分步（§「手動分步流程」）而非一鍵 migrate.sh

**Step 1 — 執行一鍵 migrate**
```bash
cd ~/GiteaTracker
./deploy/migrate.sh
```

這會依序：
1. `backup.sh` — SQLite online backup（不用停機）+ attachments tar.gz
2. `stop.sh` — 停 Flask/gunicorn
3. `git pull` — 拉新 code
4. `migrate.py --dry-run` — 列出要跑哪些 migration（**先看清楚**）
5. `migrate.py` — 實際套用
6. `start.sh` — 啟動

**Step 2 — 升版後驗證**
```bash
./deploy/status.sh                            # 確認 service 起來了
venv/bin/python migrate.py --list             # 確認 migration 都是 applied
tail -20 logs/app.log                         # 沒有 ERROR / Traceback
curl -s http://127.0.0.1:5000/ -o /dev/null -w "%{http_code}\n"   # 200
```

- [ ] 進 web 開 dashboard、tracker 頁面確認能載入
- [ ] 測試編輯一個 issue 的 JIRA / Owner / Path，確認 highlight 有出來
- [ ] 測試上傳附件確認 `data/attachments/` 路徑沒斷
- [ ] 通知使用者升版完成、提醒「首次進入可能需要點『標記已讀』」（若有適用）

---

## 手動分步流程（不用一鍵腳本時）

如果 `migrate.sh` 某一步失敗，可以從那步接手：

```bash
cd ~/GiteaTracker

# 1. 手動備份
./deploy/backup.sh

# 2. 手動停機
./deploy/stop.sh

# 3. 手動拉 code
git pull

# 4. 預覽 migrations
venv/bin/python migrate.py --list         # 看目前狀態
venv/bin/python migrate.py --dry-run      # 看會跑哪些

# 5. 執行 migrations
venv/bin/python migrate.py

# 6. 啟動
./deploy/start.sh
```

---

## Rollback 流程（升版失敗救援）

1. **停機**
   ```bash
   ./deploy/stop.sh || true
   ```

2. **還原 DB + attachments**
   ```bash
   ls -lt backups/ | head -5     # 找到最新的備份
   ./deploy/restore.sh backups/gitea_tracker_<TIMESTAMP>.db backups/attachments_<TIMESTAMP>.tar.gz
   ```
   `restore.sh` 會複製 DB 檔 + 解壓 attachments + 自動啟動 service。

3. **還原程式碼**
   ```bash
   git log --oneline -5          # 找到升版前的 commit
   git checkout <前一個 commit hash>
   ./deploy/start.sh             # 如果 restore.sh 已經起過就跳過這步
   ```

**重要**：restore 後 `schema_version` 表會回到升版前的狀態，下次 migrate 會把 pending 的那些重跑一遍。若 migration 是冪等的（應該都是），再跑一次不會壞。若不是，先解決那個 migration 的 bug 再升。

---

## 注意事項（重要）

### Attachment 檔案
- **DB migration 不會動 `data/attachments/` 下的任何檔案**，也不改 `attachments.stored_path` 欄位。
- 這是規則，不是技術強制。寫 migration 時要自律。
- 若要搬動 attachment 實際路徑（例如換 `ATTACHMENT_DIR` 位置），**不要寫進 migration**；寫獨立的 one-shot script 並備份兩次（DB + 檔案）。

### SQLite 的 schema 限制
- **可以**：`ADD COLUMN`、`CREATE TABLE`、`CREATE INDEX`、`RENAME COLUMN`（3.25+）、`RENAME TABLE`
- **不行 / 很麻煩**：`DROP COLUMN`（3.35+ 才有，且不是所有版本都有）、改欄位型別、改 constraint
- 要做不支援的改動時，標準模式是「新表 + 複製資料 + 切換名字」（寫 migration 時會很繁瑣，審慎評估是否真的需要）

### 冪等性（idempotent）是鐵律
每個 migration 的 `up()` 必須滿足「**跑 N 次和跑 1 次效果相同**」：
- 新增欄位前 `PRAGMA table_info` 先檢查
- 新增表用 `CREATE TABLE IF NOT EXISTS`
- 新增 index 用 `CREATE INDEX IF NOT EXISTS`
- UPDATE/INSERT 資料時加條件避免覆蓋已處理過的 row

範例（`001_issue_meta_timestamps.py`）：
```python
def up(conn):
    cur = conn.execute("PRAGMA table_info(issues)")
    existing = {row[1] for row in cur.fetchall()}
    for col in NEW_COLS:
        if col not in existing:                                  # 關鍵：先檢查
            conn.execute(f"ALTER TABLE issues ADD COLUMN {col} TEXT")
            conn.execute(f"UPDATE issues SET {col} = updated_at WHERE {col} IS NULL")
```

### 升版順序鐵則
1. **一定先 backup 再 migrate**。`migrate.sh` 第一步就是 backup，絕對不要跳過。
2. **Migration 失敗時不要硬跑**。看錯誤訊息、修 migration code、或 restore 後重新規劃。
3. **不要同時多人在正式機器操作 DB**。migrate 期間 service 是停機狀態，沒人看到不一致畫面，但並行寫檔會壞資料。

### 新使用者 / 既有使用者的 `last_viewed_at`
- **002 migration 會把所有使用者的 `last_viewed_at` 統一設成 migrate 時間點**（等同全員被系統幫忙按了一次「標記已讀」）
- 意思是升版後進頁面，**看不到任何 migrate 之前的變動為黃底**
- 之後新的 cell / meta 變動才會顯示為新
- 若某位使用者原本刻意把某些變動留在未讀狀態（沒按「標記已讀」），這個 migration 會把他的未讀狀態全部清掉 — 這是刻意的設計，升版前請先通知

### `data/gitea_tracker_bp.db` 是什麼
那是之前開發時手動留的備份檔（`_bp` = backup），不是正式檔。可以放著或搬到 `backups/`。正式的自動備份會在 `backups/` 底下、檔名帶時間戳。

---

## 新增 Migration（開發者指南）

### 步驟

1. **定編號**：看 `migrations/` 目錄，下一個三位數編號（例如已有 001、002，下一個就 003）

2. **建檔**：`migrations/003_<short_name>.py`，複製這個模板：
   ```python
   """<一句話說明這個 migration 做什麼 + 為什麼>"""

   SCHEMA_VERSION = "003"
   DESCRIPTION = "<一行描述，會顯示在 migrate.py --list>"


   def up(conn):
       # 必須冪等！執行前檢查狀態，跳過已處理過的。
       cur = conn.execute("PRAGMA table_info(your_table)")
       existing = {row[1] for row in cur.fetchall()}
       if "new_col" not in existing:
           conn.execute("ALTER TABLE your_table ADD COLUMN new_col TEXT")
   ```

3. **同步 `app/schema.sql`**：如果是新增欄位/表，也要加到 schema.sql — 確保 fresh DB（`init_db.py`）一次到位，不用再跑 migration 補。`init_db.py` 跑完 schema.sql 後會自動呼叫 `migrate.py`，把已「被 schema.sql 建好」的那幾個 migration 標成 applied（因為 idempotent check 會跳過 ALTER），所以不會重複。

4. **本機測試**：
   ```bash
   cp data/gitea_tracker.db /tmp/test.db
   DB_PATH=/tmp/test.db venv/bin/python migrate.py --dry-run
   DB_PATH=/tmp/test.db venv/bin/python migrate.py
   DB_PATH=/tmp/test.db venv/bin/python migrate.py    # 再跑一次，確認 no-op
   ```

5. **Commit 時分開**：migration 單獨一個 commit，message 格式：
   ```
   migrate(003): <short description>
   ```
   方便之後 review 和 cherry-pick。

### 常見陷阱

- ❌ `UPDATE users SET last_viewed_at = 'some_fixed_string'` — 沒判斷，跑兩次會覆蓋第二次的值（雖然此例是幂等，但要養成習慣）
- ❌ `DROP TABLE old_t; CREATE TABLE new_t AS ...` — 重跑會資料消失
- ❌ 在 `up()` 裡 `conn.commit()` — runner 會統一 commit，你自己 commit 會把 rollback 的能力弄壞
- ❌ 在 `up()` 拋一半錯（比方先 ALTER 後 UPDATE，ALTER 成功 UPDATE 失敗）— 雖然 runner 會 rollback DDL 在 SQLite 裡支援有限，盡量把所有動作放在同一個 transaction 裡讓 rollback 乾淨
- ✅ 大資料量的 `UPDATE` 要分 batch，避免鎖死：
  ```python
  while True:
      cur = conn.execute("UPDATE ... WHERE id > ? LIMIT 1000", (last_id,))
      if cur.rowcount == 0: break
      last_id += 1000
  ```

---

## 相關檔案清單

| 檔案 | 用途 |
|---|---|
| `migrate.py` | Migration runner（`--list` / `--dry-run` / 直接跑） |
| `migrations/` | Migration 檔案目錄（`001_*.py`, `002_*.py`, ...） |
| `app/schema.sql` | Fresh DB 的完整 schema（migration 有加欄位就要同步） |
| `init_db.py` | 新建 DB 時用，會自動呼叫 migrate |
| `deploy/migrate.sh` | 一鍵升版 workflow |
| `deploy/backup.sh` / `restore.sh` | 備份還原（backup 用 Python，不需 `sqlite3` CLI） |
| `deploy/verify_backup.sh` | 驗證最新一份備份能還原 + 開啟（建議每週 cron） |
| `deploy/releases/*.md` | 每次升版的專屬說明（commit 清單 / 行為改變 / 特殊注意） |
| `deploy/start.sh` / `stop.sh` / `status.sh` | Service 控制 |
| `tests/` + `pytest.ini` | Pytest 測試套件；`venv/bin/pytest -q` 可跑 |
| `backups/` | 自動產生的備份檔（DB + attachments tar.gz） |

---

## 疑難排解

### `migrate.py` 說 "DB not found"
`DB_PATH` 沒指到正確的 DB 檔。檢查 `.env` 或 `config.py`。

### `migrate.py --list` 顯示某 migration 是 applied，但實際欄位沒出現
有人手動改過 DB 或 restore 用錯備份。建議 `./deploy/restore.sh <正確備份>` 回到已知良好狀態，再 `migrate.py` 重跑。

### Fresh DB 執行 `init_db.py` 後看到 "Found 2 pending migration(s)..."
正常 — schema.sql 已建好最新 schema，migration 的 idempotent check 會跳過 ALTER，但會把 version 記到 `schema_version`。下次 `migrate.py` 就 no-op。

### 升版後使用者說看不到任何 highlight
正常 — migration 002 把大家的 `last_viewed_at` 重設為 migrate 時間了。有新變動後才會看到黃底。
