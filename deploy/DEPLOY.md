# Gitea Tracker — 部署指南（f12titan）

本文件說明如何在 f12titan 主機上部署 Gitea Tracker。
全程**不需要 sudo / root 權限**。

> **Shell 說明**：本文件同時提供 **bash** 和 **csh/tcsh** 兩種指令。
> f12titan 使用 csh，請依照標示 `csh` 的區塊操作。
> 部署腳本（`start.sh`、`stop.sh` 等）內部使用 bash（有 shebang），
> 從 csh 直接呼叫即可正常執行，不需要切換 shell。

---

## 目錄

1. [環境需求](#1-環境需求)
2. [安裝程式碼](#2-安裝程式碼)
3. [設定環境變數](#3-設定環境變數)
4. [初始化資料庫與匯入資料](#4-初始化資料庫與匯入資料)
5. [啟動與停止服務](#5-啟動與停止服務)
6. [驗證部署](#6-驗證部署)
7. [日常維運](#7-日常維運)
8. [備份與還原](#8-備份與還原)
9. [升級流程](#9-升級流程)
10. [疑難排解](#10-疑難排解)

---

## 1. 環境需求

| 項目 | 最低需求 |
|------|---------|
| OS | Linux（f12titan 現有系統即可） |
| Python | 3.10 以上（建議 3.12） |
| SQLite | 3.35+（通常隨 Python 內建） |
| 磁碟空間 | 500 MB（含附件預留空間） |

確認 Python 版本：

```
python3 --version
```

> 如果版本低於 3.10 且無法請 IT 升級，可用 [pyenv](https://github.com/pyenv/pyenv) 在自己的 home 目錄安裝新版 Python，不需要 sudo。

---

## 2. 安裝程式碼

**bash：**

```bash
cd ~
git clone https://github.com/wyluoa/GiteaTracker.git gitea-tracker
cd ~/gitea-tracker

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p data/attachments
mkdir -p backups
```

**csh / tcsh：**

```csh
cd ~
git clone https://github.com/wyluoa/GiteaTracker.git gitea-tracker
cd ~/gitea-tracker

python3 -m venv venv
source venv/bin/activate.csh
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p data/attachments
mkdir -p backups
```

> **差異**：csh 要用 `source venv/bin/activate.csh`（不是 `activate`）。

---

## 3. 設定環境變數

### 方式 A：使用 .env 檔（推薦）

應用程式透過 python-dotenv 讀取 `.env`，跟你的 shell 無關，**bash 和 csh 通用**：

```
cd ~/gitea-tracker
cp .env.example .env
```

編輯 `.env`：

```ini
SECRET_KEY=（貼上下方指令產生的隨機字串）
HOST=0.0.0.0
PORT=5000
```

產生隨機 SECRET_KEY：

```
./venv/bin/python -c "import secrets; print(secrets.token_hex(32))"
```

> `HOST=0.0.0.0` 表示接受來自內網其他機器的連線。
> 其他設定項（DB_PATH、ATTACHMENT_DIR 等）使用預設值即可，不需要額外設定。

### 方式 B：使用 shell 環境變數（臨時測試用）

如果你不想建 `.env` 檔，可以直接在 shell 設定：

**bash：**

```bash
export SECRET_KEY="your-secret-key-here"
export HOST="0.0.0.0"
export PORT="5000"
```

**csh / tcsh：**

```csh
setenv SECRET_KEY "your-secret-key-here"
setenv HOST "0.0.0.0"
setenv PORT "5000"
```

> 注意：shell 環境變數在登出後會消失，正式部署建議用方式 A（`.env` 檔）。

### 所有可用設定項（參考）

| 變數名 | 說明 | 預設值 |
|--------|------|--------|
| `SECRET_KEY` | Flask session 加密金鑰，**必須修改** | `dev-secret-change-me-in-production` |
| `FLASK_DEBUG` | 除錯模式（正式環境必須為 `0`） | `0` |
| `HOST` | 監聽位址 | `127.0.0.1` |
| `PORT` | 監聽埠 | `5000` |
| `DB_PATH` | SQLite 資料庫路徑 | `data/gitea_tracker.db` |
| `ATTACHMENT_DIR` | 附件存放路徑 | `data/attachments` |
| `ATTACHMENT_MAX_MB` | 單檔上限（MB） | `5` |
| `SESSION_HOURS` | Session 有效時數 | `24` |

---

## 4. 初始化資料庫與匯入資料

以下指令 bash / csh 通用（直接呼叫 venv 裡的 python）：

```
cd ~/gitea-tracker

# 建立資料表
./venv/bin/python init_db.py

# 建立預設 nodes + super user (wy / changeme)
./venv/bin/python seed.py

# 匯入 Excel 資料（把 xlsx 檔上傳到主機後執行）
./venv/bin/python import_from_excel.py --file /path/to/tracker.xlsx
```

> **首次登入後請立即到 Admin 修改 super user 密碼。**
>
> **後續更新**：上線後如需用 Excel 更新資料，可透過 Admin → Excel Update
> 網頁介面上傳，系統會顯示差異預覽、標示衝突，確認後才寫入。
> 不需要再用 CLI 指令。

---

## 5. 啟動與停止服務

以下指令 bash / csh 通用（腳本內部使用 `#!/bin/bash`，從 csh 呼叫也可以正常執行）：

### 啟動

```
cd ~/gitea-tracker
./deploy/start.sh
```

啟動後會顯示 PID，程式在背景執行。即使 SSH 斷線也不會停止。

### 停止

```
~/gitea-tracker/deploy/stop.sh
```

### 查看狀態

```
~/gitea-tracker/deploy/status.sh
```

### 查看 log

```
# 即時追蹤
tail -f ~/gitea-tracker/logs/app.log

# 最近 100 行
tail -100 ~/gitea-tracker/logs/app.log
```

---

## 6. 驗證部署

部署完成後，依序確認：

```
[ ] http://f12titan:5000/healthz 回傳 {"status": "ok"}
[ ] http://f12titan:5000/login   顯示登入頁
[ ] 用 wy 帳號登入成功
[ ] /dashboard 顯示 node 統計
[ ] /tracker  顯示追蹤表，資料與 Excel 一致
[ ] 點擊 cell 可開啟側面板
[ ] /changes  變動總表可打開、navbar 徽章數字合理
[ ] /admin    可進入管理後台
[ ] /admin/excel_update  Excel 上傳更新功能正常
[ ] /admin/errors        錯誤日誌頁面可打開（super user）
[ ] 上傳附件功能正常
[ ] tail logs/errors.jsonl — 沒剛冒出的新錯誤
```

> 同事在自己的電腦上用瀏覽器打開 `http://f12titan:5000` 即可使用。
> **首次升版或有大改動後，提醒使用者 `Ctrl+Shift+R` 硬重整**，
> 否則 CSRF token 相關的操作可能回 403。

---

## 7. 日常維運

### 資料庫位置

```
~/gitea-tracker/data/gitea_tracker.db     # 主資料庫
~/gitea-tracker/data/attachments/          # 附件檔案
~/gitea-tracker/logs/app.log              # 應用 log
```

### 重啟服務

```
~/gitea-tracker/deploy/stop.sh
~/gitea-tracker/deploy/start.sh
```

---

## 8. 備份與還原

### 手動備份

```
~/gitea-tracker/deploy/backup.sh
```

備份內容：
- SQLite 資料庫（Python `sqlite3.backup()` 線上備份；**不**依賴 `sqlite3` CLI，在沒裝 `sqlite3` 指令的機器也能跑）
- 附件目錄壓縮檔
- 自動保留最近 30 天的備份

### ⚠ 異地備份（避免單點故障）

本機 `backups/` 跟 live DB 在同一台機器上——硬碟毀損/主機遺失時備份一起沒。
設 `GITEA_TRACKER_OFFSITE` 讓 backup.sh 額外 rsync 到別處：

```
# crontab -e：每天 2 AM 備份 + 推一份到 NAS
0 2 * * * GITEA_TRACKER_OFFSITE="user@nas:/backups/giteatr" ~/gitea-tracker/deploy/backup.sh
```

`GITEA_TRACKER_OFFSITE` 可以是：
- `user@host:/path` — SSH rsync 到另一台機器（需設好 ssh key）
- 本地路徑 `/mnt/nas/gitea` — 網路掛載的 NAS / 網芳
- 公司檔案伺服器上的路徑

如果環境沒裝 rsync，腳本會印 warning 但本機備份仍會完成。

### 驗證備份真的可用

```
~/gitea-tracker/deploy/verify_backup.sh
```

腳本會拿最新一份備份 DB，開啟並跑 sanity SELECT（檢查 schema + 資料可讀）。
建議 **每週 cron 跑一次**，出問題 cron 會發 mail 通知：

```
0 3 * * 1 ~/gitea-tracker/deploy/verify_backup.sh
```

> 「沒驗證過的備份，出事那天才發現不能用」是常見災難。

### 設定每日自動備份（user crontab）

```
crontab -e
# 加入以下這行（每天凌晨 2 點備份）：
0 2 * * * ~/gitea-tracker/deploy/backup.sh
```

> `crontab` 跟你的 login shell 無關，上面的指令 bash/csh 都一樣。
> crontab 預設以 `/bin/sh` 執行，而 `backup.sh` 有 `#!/bin/bash` shebang，所以不受影響。

### 還原

```
# 還原資料庫 + 附件
~/gitea-tracker/deploy/restore.sh \
  backups/gitea_tracker_20260412_020000.db \
  backups/attachments_20260412_020000.tar.gz

# 只還原資料庫（不動附件）
~/gitea-tracker/deploy/restore.sh \
  backups/gitea_tracker_20260412_020000.db
```

> csh 中反斜線換行（`\`）也可以使用，語法相同。
> 還原時腳本會自動停止並重啟服務。

---

## 9. 升級流程

> 完整的升版 SOP（含 rollback、新增 migration 規範、各種注意事項、疑難排解）
> 寫在 **`deploy/MIGRATION_SOP.md`**。本節是快速操作摘要。
>
> **每次正式升版還會有獨立的版本說明**，放在 **`deploy/releases/YYYY-MM-DD-*.md`**。
> 升版前務必看一下該版本的說明，會列出那次額外要注意的事（新套件、行為改變、
> 使用者要做什麼等）。

### 9.1 一鍵升版（推薦）

```
cd ~/gitea-tracker
./deploy/migrate.sh
```

這會依序執行：

1. `backup.sh` — SQLite online backup + attachments tar.gz 進 `backups/`
2. `stop.sh` — 停服務
3. `git pull` — 拉新 code
4. `migrate.py --dry-run` — 列出要套用哪些 DB migration（**看一下 terminal 輸出的 pending 清單是否合理**）
5. `migrate.py` — 實際套用
6. `start.sh` — 啟動

若某一步失敗，service 會停在停機狀態，不會在半套 migration 的狀況下被啟動。

> ⚠ **`migrate.sh` 不會跑 `pip install`**。當 `requirements.txt` 有變動時
> （通常會在 `deploy/releases/*.md` 點出），用 §9.2 手動分步流程，在
> `git pull` 之後多跑一次 `venv/bin/pip install -r requirements.txt`。

### 9.2 手動分步（升版腳本失敗時接手）

```
cd ~/gitea-tracker

# 1. 備份
./deploy/backup.sh

# 2. 停機
./deploy/stop.sh

# 3. 拉新 code
git pull origin main

# 4. 更新 Python 套件（如果 requirements.txt 有變）
./venv/bin/pip install -r requirements.txt

# 5. 檢查要跑哪些 migration
./venv/bin/python migrate.py --list          # 看已套用 / pending
./venv/bin/python migrate.py --dry-run       # 預覽要跑什麼

# 6. 套用 migration
./venv/bin/python migrate.py

# 7. 啟動
./deploy/start.sh

# 8. 驗證
curl http://127.0.0.1:5000/healthz
./venv/bin/python migrate.py --list          # 應該全部 applied
tail -20 logs/app.log                        # 沒 ERROR / Traceback
```

### 9.3 Rollback（升版失敗救援）

```
./deploy/stop.sh || true

# 還原 DB + attachments 到備份時間點
./deploy/restore.sh backups/gitea_tracker_<TIMESTAMP>.db \
                    backups/attachments_<TIMESTAMP>.tar.gz

# 視情況回 code
git log --oneline -5
git checkout <前一個 commit 的 hash>

./deploy/start.sh
```

Restore 後 `schema_version` 也會回到升版前狀態；下次 `migrate.py` 會把 pending 的那幾個 migration 重跑一遍（每個 migration 都是冪等的，重跑不會壞）。若某個 migration 有 bug 導致這次 rollback，**先修那支 migration 的 code 再升**，不要把同一個壞版本再跑一次。

### 9.4 升版前檢查清單

- [ ] 通知使用者即將停機（10-30 秒）
- [ ] 確認 `backups/` 磁碟空間夠（至少 DB + 1 份 attachments tar.gz 大小）
- [ ] 本機已測過這次 release（或在 staging / `DB_PATH` 指 `/tmp/xxx.db` 模擬 `migrate.py --dry-run`）
- [ ] 看完 pending migration 清單，理解每個在做什麼

### 9.5 DB migration 的特殊注意事項

- **Attachment 檔案絕對不會被 migration 動**（規則寫在 MIGRATION_SOP.md）。
- **新欄位加在 `app/schema.sql` + 一個 `migrations/NNN_*.py` 檔**，兩邊都要同步；詳見 MIGRATION_SOP 的「新增 Migration」章節。
- **Migration 必須冪等** — 加欄位前 `PRAGMA table_info` 檢查、加表用 `CREATE IF NOT EXISTS`、資料更新要有條件避免覆蓋。
- 所有 schema 變動一律走 `migrations/NNN_*.py`；`app/db.py` 過去的 startup-time migration 已於 migration 008 時合併移除。

---

## 10. 疑難排解

### 服務啟動失敗

```
# 查看 log
cat ~/gitea-tracker/logs/app.log

# 常見原因：
# - Python 路徑錯誤 → 確認 venv/bin/python 存在
# - DB_PATH 目錄不存在 → mkdir -p data
# - PORT 被占用 → 改 .env 中的 PORT，或找出占用的程序：
#   lsof -i :5000
```

### 無法從其他電腦連線

```
# 確認 .env 中 HOST=0.0.0.0（不是 127.0.0.1）
grep HOST .env

# 確認服務有在跑
curl http://127.0.0.1:5000/healthz

# 如果本機 OK 但其他電腦連不到，可能是防火牆問題
# → 請 IT 確認 f12titan 的 port 5000 有開放內網存取
```

### 檔案上傳失敗

```
# 確認附件目錄存在且有寫入權限
ls -la ~/gitea-tracker/data/attachments/
```

### 資料庫被鎖定 (database is locked)

```
# SQLite 同時只允許一個寫入。正常使用不會發生此問題。
# 如果發生，確認沒有其他程序正在存取 DB：
fuser ~/gitea-tracker/data/gitea_tracker.db
```

### ImportError: cannot import name 'db' from 'app'

```
# 這通常是 __pycache__ 殘留或目錄下有名為 app.py 的檔案衝突。
# 清除所有快取：
find ~/gitea-tracker -type d -name __pycache__ -exec rm -rf {} +
find ~/gitea-tracker -name "*.pyc" -delete
```

### `backup.sh` 報 `UnicodeEncodeError` / `'latin-1' codec can't encode / decode...`

**現象**：手動或 cron 執行 `./deploy/backup.sh` / `./deploy/verify_backup.sh`
出現類似

```
UnicodeEncodeError: 'latin-1' codec can't encode character '→' ...
UnicodeEncodeError: 'ascii'   codec can't encode character '→' ...
```

**原因**：Python 的 `sys.stdout.encoding` 跟著系統 locale / `PYTHONIOENCODING` 決定。
在 cron 或 POSIX / C / latin-1 locale 的機器上，stdout 會被視為 ASCII/latin-1，
只要 `print()` 出現非 ASCII 字元（例如箭頭 `→`）就會炸掉。

**修正**：
1. `deploy/backup.sh` 與 `deploy/verify_backup.sh` 在最上面 `set -euo pipefail` 後
   **強制 `export PYTHONIOENCODING=utf-8`**（已加上，新版預設有）。
2. 腳本裡嵌入的 Python heredoc 若要 print，**全部用 ASCII**。不要再用 `→`、
   `・`、`「」` 等非 ASCII 符號；用 `->`、`-` 代替。

**寫新 deploy 腳本時記得**：
- shebang `#!/bin/bash` 下第一段就 `export PYTHONIOENCODING=utf-8`。
- Python heredoc 裡的 `print()` 字串維持 ASCII（反正這些訊息是給 log 看的，不用炫）。
- 若真的要輸出中文，要多加一句 `sys.stdout.reconfigure(encoding="utf-8")`
  並確認執行環境的 locale 允許 UTF-8 輸出。

> 這個坑踩過一次就好。新寫 `.sh` 裡的 Python 訊息前先看這一節。

---

## 附錄 A：完整檔案結構

```
~/gitea-tracker/
├── main.py                  # 應用程式入口
├── config.py                # 設定（讀環境變數）
├── .env                     # 環境變數設定（部署時建立）
├── init_db.py               # 初始化資料庫
├── seed.py                  # 建立預設資料
├── import_from_excel.py     # Excel 匯入腳本
├── requirements.txt         # Python 套件清單
├── venv/                    # Python 虛擬環境
├── app/                     # Flask 應用程式碼
│   ├── excel.py             #   Excel 解析共用模組
│   ├── schema.sql
│   ├── routes/
│   ├── models/
│   ├── templates/
│   └── static/
├── data/                    # 執行時資料（勿刪除）
│   ├── gitea_tracker.db     #   SQLite 資料庫
│   └── attachments/         #   上傳的附件
├── logs/                    # 應用 log
│   └── app.log
├── backups/                 # 備份檔案
├── migrations/              # DB migration 檔案
├── tests/                   # pytest 測試套件
└── deploy/                  # 部署工具
    ├── DEPLOY.md            #   本文件（常態升版流程）
    ├── MIGRATION_SOP.md     #   Migration 完整 SOP
    ├── releases/            #   每次升版的專屬說明
    ├── start.sh             #   啟動腳本
    ├── stop.sh              #   停止腳本
    ├── status.sh            #   狀態檢查
    ├── migrate.sh           #   一鍵升版
    ├── backup.sh            #   備份（Python-based，不需 sqlite3 CLI）
    ├── verify_backup.sh     #   驗證最新備份能還原
    └── restore.sh           #   還原腳本
```

## 附錄 B：bash vs csh 對照速查

| 用途 | bash | csh / tcsh |
|------|------|------------|
| 啟用 virtualenv | `source venv/bin/activate` | `source venv/bin/activate.csh` |
| 設定環境變數 | `export VAR="value"` | `setenv VAR "value"` |
| 取消環境變數 | `unset VAR` | `unsetenv VAR` |
| 查看環境變數 | `echo $VAR` | `echo $VAR` |
| 查看所有環境變數 | `env` | `env` |
| 背景執行 | `command &` | `command &` |
| 重導向（stdout+stderr） | `cmd >> file 2>&1` | `cmd >>& file` |
| 條件判斷 | `if [ -f file ]; then ... fi` | `if ( -f file ) then ... endif` |
| 迴圈 | `for f in *.log; do ... done` | `foreach f (*.log) ... end` |

> 部署腳本（`.sh`）有 `#!/bin/bash` shebang，從 csh 直接 `./deploy/start.sh` 即可，不需要切 shell。
