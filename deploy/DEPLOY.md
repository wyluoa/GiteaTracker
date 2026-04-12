# Gitea Tracker — Linux 部署指南

本文件說明如何在公司 Linux 主機上部署 Gitea Tracker，涵蓋從零安裝到日常維運的完整流程。

---

## 目錄

1. [環境需求](#1-環境需求)
2. [安裝程式碼](#2-安裝程式碼)
3. [設定環境變數](#3-設定環境變數)
4. [初始化資料庫與匯入資料](#4-初始化資料庫與匯入資料)
5. [用 systemd 管理服務](#5-用-systemd-管理服務)
6. [用 Nginx 做反向代理](#6-用-nginx-做反向代理)
7. [防火牆設定](#7-防火牆設定)
8. [驗證部署](#8-驗證部署)
9. [日常維運](#9-日常維運)
10. [備份與還原](#10-備份與還原)
11. [升級流程](#11-升級流程)
12. [疑難排解](#12-疑難排解)

---

## 1. 環境需求

| 項目 | 最低需求 |
|------|---------|
| OS | CentOS 7+ / RHEL 7+ / Ubuntu 20.04+ |
| Python | 3.10 以上（建議 3.12） |
| SQLite | 3.35+（通常隨 Python 內建） |
| Nginx | 任意穩定版本 |
| 磁碟空間 | 500 MB（含附件預留空間） |
| RAM | 256 MB 以上即可 |

確認 Python 版本：

```bash
python3 --version
# 如果版本太舊，CentOS/RHEL 可用：
# sudo yum install python3.12
# Ubuntu 可用：
# sudo apt install python3.12 python3.12-venv
```

確認 Nginx 已安裝：

```bash
nginx -v
# 如果未安裝：
# CentOS/RHEL: sudo yum install nginx
# Ubuntu:      sudo apt install nginx
```

---

## 2. 安裝程式碼

```bash
# 建立應用目錄
sudo mkdir -p /opt/gitea-tracker
sudo chown $USER:$USER /opt/gitea-tracker

# 取得程式碼
cd /opt/gitea-tracker
git clone https://github.com/wyluoa/GiteaTracker.git .

# 建立 Python 虛擬環境並安裝套件
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

建立資料目錄：

```bash
mkdir -p data/attachments
mkdir -p backups
```

---

## 3. 設定環境變數

環境變數可透過 systemd unit file 或 `.env` 設定。以下是所有可用的設定項：

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

產生隨機 SECRET_KEY：

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 4. 初始化資料庫與匯入資料

```bash
cd /opt/gitea-tracker

# 建立資料表
./venv/bin/python init_db.py

# 建立預設 nodes + super user (wy / changeme)
./venv/bin/python seed.py

# 匯入 Excel 資料（把 xlsx 檔上傳到主機後執行）
./venv/bin/python import_from_excel.py --file /path/to/tracker.xlsx
```

> **首次登入後請立即到 Admin 修改 super user 密碼。**

---

## 5. 用 systemd 管理服務

### 5.1 安裝 service 檔

```bash
sudo cp deploy/gitea-tracker.service /etc/systemd/system/
```

### 5.2 修改設定

```bash
sudo vim /etc/systemd/system/gitea-tracker.service
```

需要修改的項目：

```ini
[Service]
# 改成實際運行的使用者（如果不用 www-data）
User=www-data
Group=www-data

# 務必改成隨機字串
Environment="SECRET_KEY=你產生的隨機字串"

# 確認路徑正確
WorkingDirectory=/opt/gitea-tracker
Environment="DB_PATH=/opt/gitea-tracker/data/gitea_tracker.db"
Environment="ATTACHMENT_DIR=/opt/gitea-tracker/data/attachments"
```

### 5.3 啟動服務

```bash
sudo systemctl daemon-reload
sudo systemctl enable gitea-tracker   # 開機自動啟動
sudo systemctl start gitea-tracker    # 立即啟動
```

### 5.4 確認服務狀態

```bash
sudo systemctl status gitea-tracker
# 應該顯示 active (running)

# 測試本地連線
curl http://127.0.0.1:5000/healthz
# 應回傳 {"status": "ok"}
```

---

## 6. 用 Nginx 做反向代理

### 6.1 安裝設定檔

**Ubuntu / Debian：**

```bash
sudo cp deploy/nginx-gitea-tracker.conf /etc/nginx/sites-available/gitea-tracker
sudo ln -s /etc/nginx/sites-available/gitea-tracker /etc/nginx/sites-enabled/
```

**CentOS / RHEL：**

```bash
sudo cp deploy/nginx-gitea-tracker.conf /etc/nginx/conf.d/gitea-tracker.conf
```

### 6.2 修改 server_name

```bash
# Ubuntu/Debian:
sudo vim /etc/nginx/sites-available/gitea-tracker
# CentOS/RHEL:
sudo vim /etc/nginx/conf.d/gitea-tracker.conf
```

把 `server_name` 改成實際的主機名稱或 IP：

```nginx
server_name tracker.your-company.com;
# 或直接用 IP:
# server_name 10.x.x.x;
```

### 6.3 測試並啟用

```bash
sudo nginx -t          # 檢查設定語法
sudo systemctl reload nginx
```

現在可以用瀏覽器打開 `http://tracker.your-company.com` 存取系統。

---

## 7. 防火牆設定

如果主機有防火牆，需要開放 HTTP 埠：

```bash
# firewalld (CentOS/RHEL):
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --reload

# ufw (Ubuntu):
sudo ufw allow 'Nginx HTTP'
```

> **注意：** Flask 的 5000 埠只綁定 127.0.0.1，外部無法直接存取，所有流量都透過 Nginx 進來，這是正確的。

---

## 8. 驗證部署

部署完成後，依序確認：

```
[ ] http://主機位址/healthz 回傳 {"status": "ok"}
[ ] http://主機位址/login   顯示登入頁
[ ] 用 wy 帳號登入成功
[ ] /dashboard 顯示 node 統計
[ ] /tracker  顯示追蹤表，資料與 Excel 一致
[ ] 點擊 cell 可開啟側面板
[ ] /admin    可進入管理後台
[ ] 上傳附件功能正常
```

---

## 9. 日常維運

### 查看服務狀態

```bash
sudo systemctl status gitea-tracker
```

### 即時查看 log

```bash
sudo journalctl -u gitea-tracker -f
```

### 查看最近 100 行 log

```bash
sudo journalctl -u gitea-tracker -n 100 --no-pager
```

### 重啟服務

```bash
sudo systemctl restart gitea-tracker
```

### 資料庫位置

```
/opt/gitea-tracker/data/gitea_tracker.db     # 主資料庫
/opt/gitea-tracker/data/attachments/          # 附件檔案
```

---

## 10. 備份與還原

### 手動備份

```bash
/opt/gitea-tracker/deploy/backup.sh /opt/gitea-tracker/backups
```

備份內容：
- SQLite 資料庫（使用 `.backup` 指令，運行中也可安全備份）
- 附件目錄壓縮檔
- 自動保留最近 30 天的備份

### 設定每日自動備份（cron）

```bash
sudo crontab -e
# 加入以下這行（每天凌晨 2 點備份）：
0 2 * * * /opt/gitea-tracker/deploy/backup.sh /opt/gitea-tracker/backups
```

### 還原

```bash
# 還原資料庫 + 附件（會自動停止並重啟服務）
/opt/gitea-tracker/deploy/restore.sh \
  backups/gitea_tracker_20260412_020000.db \
  backups/attachments_20260412_020000.tar.gz

# 只還原資料庫（不動附件）
/opt/gitea-tracker/deploy/restore.sh \
  backups/gitea_tracker_20260412_020000.db
```

---

## 11. 升級流程

```bash
cd /opt/gitea-tracker

# 1. 先備份
./deploy/backup.sh ./backups

# 2. 拉新版程式碼
git pull origin main

# 3. 更新 Python 套件（如果 requirements.txt 有變）
./venv/bin/pip install -r requirements.txt

# 4. 重啟服務
sudo systemctl restart gitea-tracker

# 5. 驗證
curl http://127.0.0.1:5000/healthz
```

> 如果升級後有問題，用 restore.sh 還原備份即可回滾。

---

## 12. 疑難排解

### 服務啟動失敗

```bash
# 查看詳細錯誤
sudo journalctl -u gitea-tracker -n 50 --no-pager

# 常見原因：
# - Python 路徑錯誤 → 確認 venv/bin/python 存在
# - DB_PATH 目錄不存在 → mkdir -p data
# - 權限不足 → chown www-data:www-data /opt/gitea-tracker/data -R
```

### Nginx 502 Bad Gateway

```bash
# 確認 Flask 有在跑
curl http://127.0.0.1:5000/healthz

# 如果沒回應，重啟 Flask
sudo systemctl restart gitea-tracker

# 確認 Nginx 設定中的 proxy_pass 埠號與 Flask PORT 一致
```

### 檔案上傳失敗

```bash
# 確認附件目錄存在且有寫入權限
ls -la /opt/gitea-tracker/data/attachments/

# 確認 Nginx 允許足夠的上傳大小（預設設定為 10MB）
# 在 nginx conf 中: client_max_body_size 10M;
```

### 資料庫被鎖定 (database is locked)

```bash
# SQLite 同時只允許一個寫入。正常使用不會發生此問題。
# 如果發生，確認沒有其他程序正在存取 DB：
fuser /opt/gitea-tracker/data/gitea_tracker.db
```

---

## 附錄：完整檔案結構

```
/opt/gitea-tracker/
├── main.py                  # 應用程式入口
├── config.py                # 設定（讀環境變數）
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
├── backups/                 # 備份檔案
└── deploy/                  # 部署設定範本
    ├── DEPLOY.md            #   本文件
    ├── gitea-tracker.service#   systemd unit
    ├── nginx-gitea-tracker.conf # Nginx 設定
    ├── backup.sh            #   備份腳本
    └── restore.sh           #   還原腳本
```
