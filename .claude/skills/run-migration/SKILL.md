---
name: run-migration
description: 依 deploy/MIGRATION_SOP.md 執行 DB migration（含備份與驗證）。用於正式機升版。
disable-model-invocation: true
allowed-tools: Bash Read
---

# /run-migration

執行 DB migration 的受控流程。**只能由使用者手動 `/run-migration` 觸發**（`disable-model-invocation: true`），避免我自作主張動 DB。

完整規範與失敗 rollback 見 @deploy/MIGRATION_SOP.md。

## 步驟

### 0. 先問使用者目前的情境
- 是本機測試還是正式機？
- 有通知其他使用者準備停機嗎？
- `backups/` 磁碟空間夠嗎？

使用者確認後繼續。

### 1. 檢查當下狀態（read-only）
```bash
venv/bin/python migrate.py --list          # 看已套用 / pending 清單
git status --short                          # 確認 working tree 乾淨
ls -lt backups/ 2>/dev/null | head -5       # 看最近備份時間
```

### 2. 預覽要跑什麼
```bash
venv/bin/python migrate.py --dry-run
```
**把 pending 清單列給使用者看，讓他確認**。使用者明確同意後才繼續。

### 3. 正式升版（選項 A — 一鍵）
```bash
./deploy/migrate.sh
```
這會執行：backup → stop → `git pull` → `migrate.py --dry-run` → `migrate.py` → start。

**不要**在使用者沒要 `git pull` 時跑 `migrate.sh`（例如本機改動還沒 commit），改走選項 B。

### 3'. 本機 / 手動（選項 B — 分步）
```bash
./deploy/backup.sh                          # 一定要先備份
./deploy/stop.sh || true
venv/bin/python migrate.py                  # 套用
./deploy/start.sh
```

### 4. 升版後驗證
```bash
venv/bin/python migrate.py --list           # 全部 applied
./deploy/status.sh                          # service 有起來
tail -20 logs/app.log                       # 沒 ERROR / Traceback
```
回報使用者：
- 套用了哪幾個 migration
- 備份檔位置（`backups/gitea_tracker_<TIMESTAMP>.db` / `attachments_<TIMESTAMP>.tar.gz`）
- Service 狀態

### 5. 失敗時的處理
**不要**硬跑第二次。先停下來看錯誤：
- 是 migration `up()` 本身有 bug → 修 migration code，重跑
- 是 DB 狀態和 migration 預期不符 → `./deploy/restore.sh <db.bak> <attachments.tar.gz>` 回到備份，再重新規劃
- 任何失敗都要把完整 error 回報使用者後再決定下一步

## 不要做的事
- ❌ 沒 backup 就跑 `migrate.py`
- ❌ `--dry-run` 輸出沒給使用者看就直接跑正式 migrate
- ❌ 跑失敗後重新 `migrate.py` 試運氣
- ❌ 用 `rm`、`DROP TABLE`、`git reset --hard` 等破壞性指令「清乾淨狀態」
- ❌ 修改 `data/attachments/` 底下任何檔案
