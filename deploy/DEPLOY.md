# Gitea Tracker 部署指南

## 前置需求

- Python 3.10+
- SQLite 3
- Nginx (reverse proxy)
- systemd (process manager)

## 安裝步驟

```bash
# 1. 複製程式碼
sudo mkdir -p /opt/gitea-tracker
sudo chown www-data:www-data /opt/gitea-tracker
cd /opt/gitea-tracker
git clone <repo_url> .

# 2. 建立 Python 虛擬環境
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 3. 初始化資料庫
./venv/bin/python init_db.py
./venv/bin/python seed.py

# 4. 匯入 Excel 資料（如有）
./venv/bin/python import_from_excel.py --file /path/to/tracker.xlsx

# 5. 建立資料目錄
mkdir -p data/attachments backups
```

## 設定 systemd

```bash
sudo cp deploy/gitea-tracker.service /etc/systemd/system/
# 修改 SECRET_KEY 等環境變數
sudo vim /etc/systemd/system/gitea-tracker.service
sudo systemctl daemon-reload
sudo systemctl enable gitea-tracker
sudo systemctl start gitea-tracker
```

## 設定 Nginx

```bash
sudo cp deploy/nginx-gitea-tracker.conf /etc/nginx/sites-available/gitea-tracker
sudo ln -s /etc/nginx/sites-available/gitea-tracker /etc/nginx/sites-enabled/
# 修改 server_name
sudo vim /etc/nginx/sites-available/gitea-tracker
sudo nginx -t
sudo systemctl reload nginx
```

## 備份

```bash
# 手動備份
./deploy/backup.sh /opt/gitea-tracker/backups

# 設定 cron 每日凌晨 2 點自動備份
sudo crontab -u www-data -e
# 加入: 0 2 * * * /opt/gitea-tracker/deploy/backup.sh /opt/gitea-tracker/backups
```

## 還原

```bash
./deploy/restore.sh backups/gitea_tracker_20260411_020000.db backups/attachments_20260411_020000.tar.gz
```

## 升級

```bash
cd /opt/gitea-tracker
git pull origin main
./venv/bin/pip install -r requirements.txt
sudo systemctl restart gitea-tracker
```

## 常用指令

```bash
# 查看狀態
sudo systemctl status gitea-tracker

# 查看日誌
sudo journalctl -u gitea-tracker -f

# 重啟
sudo systemctl restart gitea-tracker
```
