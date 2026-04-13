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
[ ] /admin    可進入管理後台
[ ] 上傳附件功能正常
```

> 同事在自己的電腦上用瀏覽器打開 `http://f12titan:5000` 即可使用。

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
- SQLite 資料庫（使用 `.backup` 指令，運行中也可安全備份）
- 附件目錄壓縮檔
- 自動保留最近 30 天的備份

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

以下指令 bash / csh 通用：

```
cd ~/gitea-tracker

# 1. 先備份
./deploy/backup.sh

# 2. 拉新版程式碼
git pull origin main

# 3. 更新 Python 套件（如果 requirements.txt 有變）
./venv/bin/pip install -r requirements.txt

# 4. 重啟服務
./deploy/stop.sh
./deploy/start.sh

# 5. 驗證
curl http://127.0.0.1:5000/healthz
```

> 如果升級後有問題，用 restore.sh 還原備份即可回滾。

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
└── deploy/                  # 部署工具
    ├── DEPLOY.md            #   本文件
    ├── start.sh             #   啟動腳本
    ├── stop.sh              #   停止腳本
    ├── status.sh            #   狀態檢查
    ├── backup.sh            #   備份腳本
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
