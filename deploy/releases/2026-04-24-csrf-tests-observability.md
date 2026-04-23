# Release 2026-04-24 — CSRF · Tests · Observability

> 這是版本獨立的升版指南。常態升版流程在 [`deploy/DEPLOY.md`](../DEPLOY.md) §9，
> 本檔只列**本次升版的額外注意事項**與對照清單。

## 本次升版包含的 commit（依序）

| # | Commit | 內容 |
|---|---|---|
| 1 | `3c929c4` | `feat(changes)`：新增 `/changes` 變動總表頁面、node 篩選、顯示規則面板、dark mode 樣式 |
| 2 | `2154faf` | `test`：pytest 套件（68 tests）——smoke / state-transitions / issue_model / migrations / changes_summary |
| 3 | `c8ebeb4` | `security(csrf)`：所有 state-changing routes 加 CSRF token 檢查 |
| 4 | `e8d587c` | `deploy(backup)`：`backup.sh` 改用 Python（不依賴 `sqlite3` CLI）、新增 `GITEA_TRACKER_OFFSITE` 異地備份、`verify_backup.sh` |
| 5 | `64e45cd` | `refactor(changes)`：Navbar 徽章 + `/changes` 預設計入本人操作；migration 008 合併舊的 startup migration |
| 6 | `c7b1311` | `feat(observability)`：結構化錯誤 log (`logs/errors.jsonl`) + `/admin/errors` 頁面 |

---

## TL;DR 升版指令

```bash
cd ~/GiteaTracker
./deploy/backup.sh                                # 1. 備份
./deploy/stop.sh                                  # 2. 停服
git pull                                          # 3. 拉新 code
venv/bin/pip install -r requirements.txt          # 4. 裝 pytest（★ 本次新增步驟）
venv/bin/python migrate.py --dry-run              # 5. 預覽 migration 008
venv/bin/python migrate.py                        # 6. 套用
./deploy/start.sh                                 # 7. 啟動
```

> `./deploy/migrate.sh` 沒包 step 4 的 `pip install`，**本次請手動下**。
> 下次若 `requirements.txt` 沒再動，繼續用 `migrate.sh` 即可。

---

## 升版前自檢（建議本機模擬一次）

```bash
cp data/gitea_tracker.db /tmp/prerelease.db

# 預覽 migration
DB_PATH=/tmp/prerelease.db venv/bin/python migrate.py --dry-run
# → Found 1 pending migration(s): 008 consolidate_legacy_migrations...

# 套用
DB_PATH=/tmp/prerelease.db venv/bin/python migrate.py
# → OK — 008 applied

# 跑測試：新 code × 升級後的 DB
venv/bin/pytest -q
# → 86 passed
```

兩步都綠燈才上正式。

---

## 本次 4 個需要特別注意的地方

### ① 使用者必須硬重整瀏覽器（★ 重要）

**原因**：本次加了 CSRF 保護（`app/csrf.py`）。`base.html` 多了
`<meta name="csrf-token">` + fetch/HTMX wrapper。舊分頁的快取 HTML 沒這個
meta，POST 會拿 **403**。

**對策**：升版完成後立刻在群組/公告通知：

> 🔔 Gitea Tracker 已升版，請按 **Ctrl+Shift+R** 重新載入頁面。
> （Mac 使用者：Cmd+Shift+R）

沒照做的使用者會看到「403 CSRF token missing or invalid」，按 F5 即解。

### ② 會套用 Migration 008

```
Found 1 pending migration(s):
  008  008_consolidate_legacy_migrations.py  consolidate: ensure legacy cols...

Applying 008 (008_consolidate_legacy_migrations.py)...
  OK — 008 applied
```

**做什麼**：確認 `issues.pending_close` 與 `users.is_manager` 欄位存在
（其實本來就有）。

**副作用**：`app/db.py::_run_migrations` 啟動時例行 migration 已移除，
app 啟動會稍微快一點。**所有 schema 改動從此統一走 `migrations/` 目錄**。

### ③ 預設行為改變 — 使用者會察覺的三件事

- **Navbar `Changes` 徽章數字會變大**
  之前排除本人操作，現在**包含本人**。數字比以前多屬正常。
- **`/changes` 頁預設顯示全部操作（含本人）**
  這是預期行為。若只想看別人做的變動，點右上 **「隱藏本人操作」** 切換。
- **顯示規則面板已更新**（預設收合，點開可以看），說明這個行為改變。

### ④ 新工具：`verify_backup.sh` + 異地備份

**驗證備份真的能還原**（強烈建議設，不裝 cron 也至少手動跑一次）：
```bash
./deploy/verify_backup.sh
# → OK: backups/gitea_tracker_<TS>.db restored & queried — issues=N, users=M
```

**異地備份**（避免主機 = 備份 = 同個硬碟的單點故障）：
```bash
crontab -e

# 每日 2 AM 備份 + 推 NAS
0 2 * * * GITEA_TRACKER_OFFSITE="user@nas:/backups/giteatr" ~/GiteaTracker/deploy/backup.sh

# 每週一 3 AM 驗證最新備份可讀
0 3 * * 1 ~/GiteaTracker/deploy/verify_backup.sh
```

`GITEA_TRACKER_OFFSITE` 可以是：
- `user@host:/path` — SSH rsync（需先設好 ssh key）
- 本地 mount 點（如 `/mnt/nas/giteatracker`）

機器沒裝 rsync 會印 warning 但本機備份仍照常完成。

---

## 升版後驗證清單

```bash
# 1. migration 狀態（001–008 全 applied）
venv/bin/python migrate.py --list

# 2. 服務健康
curl -s http://127.0.0.1:5000/healthz       # → {"status": "ok"}

# 3. logs 沒噴錯
tail -30 logs/app.log                       # 沒 ERROR / Traceback
tail logs/errors.jsonl 2>/dev/null || true  # 新檔案，應該不存在或空的

# 4. 備份確實生成
ls -lt backups/ | head -3
```

進 web 以 super user 登入，測 4 件事：

- [ ] **硬重整後**，改一個 cell 狀態 → 正常更新（不跳 403）
- [ ] `/changes` 能開、頂端 CHANGES kicker 顯示紅字、navbar 徽章數字合理
- [ ] `/admin/errors` 能打開（本次新頁面）
- [ ] 附件上傳測試一筆 → `data/attachments/` 有新檔

---

## Rollback

本次升版的 rollback 沒有特殊步驟，用標準流程：

```bash
./deploy/stop.sh || true

# 還原 DB + attachments 到升版前
ls -lt backups/ | head -3
./deploy/restore.sh backups/gitea_tracker_<TIMESTAMP>.db \
                    backups/attachments_<TIMESTAMP>.tar.gz

# 回到升版前的 commit（本次前一個是 6ebd313）
git log --oneline -10
git checkout 6ebd313
./deploy/start.sh
```

Restore 後 `schema_version` 會回到升版前狀態；下次 `migrate.py` 會把 008
重跑——migration 008 是冪等的（`PRAGMA table_info` 保護），重跑沒事。

---

## 疑難排解（本次特有）

### 使用者回報「按 button 跳 403 CSRF token missing」
**原因**：他們沒硬重整，快取 HTML 沒 CSRF token。
**解**：按 Ctrl+Shift+R。

### Chart/HTMX cell 編輯 POST 返回 403
**原因**：HTMX 請求沒帶 `X-CSRFToken`。理論上 `base.html` 有註冊
`htmx:configRequest` listener 自動注入；若失敗通常是 JS error。
**檢查**：Chrome DevTools → Console 看有沒有 JS error；
Network 看失敗的請求 Request Headers 有沒有 `X-CSRFToken`。

### `logs/errors.jsonl` 檔案累積過大
**對策**：本次刻意沒自動 rotate。大小變大前手動 rotate：
```bash
cd ~/GiteaTracker/logs
mv errors.jsonl errors.$(date +%Y%m).jsonl
gzip errors.2026*.jsonl
```
或用 logrotate 使用者組態。

### Migration 008 遇到錯誤
008 只做 `ALTER TABLE ADD COLUMN`，有 idempotent guard。遇錯通常是
DB 檔權限問題，檢查：
```bash
ls -la data/gitea_tracker.db
# 應該是 app user 可讀寫
```

---

## 這次升版帶進來的測試

`venv/bin/pytest -q` → **86 tests passing**。跑完 ~20 秒。

| 測試檔 | 數量 | 涵蓋 |
|---|---|---|
| `tests/test_smoke.py` | 7 | 測試基礎設施本身 |
| `tests/test_state_transitions.py` | 20 | Done/Unneeded 權限閘門、強制 note |
| `tests/test_issue_model.py` | 15 | Per-field timestamp、refresh_cache、field_change |
| `tests/test_migrations.py` | 10 | 所有 migration 冪等性（parametrized，新 migration 自動納入） |
| `tests/test_changes_summary.py` | 21 | Aggregation / folding / severity / node filter / include_own |
| `tests/test_csrf.py` | 9 | CSRF 攻擊面全覆蓋 |
| `tests/test_error_log.py` | 3 | 結構化 error log |
| `tests/test_smoke.py` 1 | (infra) | pytest fixture chain |

正式機器升版前，在本機或 staging 跑一次：
```bash
venv/bin/pytest -q
```
任何 fail 都要先排除才上線。
