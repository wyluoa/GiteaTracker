# 06 — 分階段實作計畫

## 設計原則

1. **每個 phase 結束都能讓使用者實際試用**,不要做完整的後端再做前端
2. **資料先進來再說**:Phase 1 就把舊資料匯入,讓使用者第一眼看到熟悉的資料,才能給有效 feedback
3. **權限晚點做**:Phase 2 用 hard-code 的 super user,Phase 3 才完整實作帳號系統,避免一開始陷在帳號邏輯
4. **效能晚點優化**:先正常實作,Phase 6 視實測效能決定是否需要 virtual scrolling

---

## Phase 0 — 專案骨架(✅ 已完成)

**目標**:能跑但什麼功能都沒有的 Flask 專案,確認環境都對。

**產出**:
- 專案目錄結構
- `requirements.txt`(Flask 3、Jinja2、bcrypt、openpyxl、python-dotenv)
- `config.py`(從環境變數讀,支援 `.env`)
- `main.py` 入口
- `init_db.py` 建立空 DB
- `app/schema.sql` 12 張表的 CREATE TABLE
- `app/db.py` SQLite 連線 helper
- `app/__init__.py` Flask app factory
- `app/routes/main.py` 含 `/` 和 `/healthz`
- `app/templates/base.html` 含 HTMX + Alpine.js + Tabler CSS(CDN)
- `app/templates/index.html` placeholder
- `README.md` 安裝/執行/驗收說明

**驗收**:
1. `python init_db.py` 不報錯,建出 12 張表
2. `python main.py` 起得來
3. `http://localhost:5000` 顯示綠色 DB status
4. 12 張表 badge 顯示
5. Alpine.js 計數器按鈕能正常累加
6. HTMX ping 按鈕呼叫 `/healthz` 顯示 `{"status": "ok"}`

**現存程式碼**: `phase0_starter_code/`

---

## Phase 1 — 核心資料模型 + 主畫面唯讀版(2~3 天)

**目標**:把你的 excel 匯進來,在網頁上看到跟 excel 一樣的表格,但還不能編輯。

### 1.1 Models 層

建立 `app/models/` 子目錄,每個 model 一個 .py 檔(或合在一個 `models.py`):
- `User` — CRUD + 查詢 + 密碼驗證
- `Group` — CRUD + 成員管理
- `Node` — CRUD + active 篩選
- `Issue` — CRUD + 篩選 + 衍生欄位更新
- `IssueNodeState` — get/set state、check_in_date、short_note
- `TimelineEntry` — 新增 + 查詢
- `Setting` — key-value get/set

不一定要用 ORM(Flask-SQLAlchemy),用原生 sqlite3 + Row factory 也可以,根據實作者偏好。

### 1.2 Seed 資料

`seed.py` 腳本,執行後:
- 建立 10 個 nodes(`A10 / A12 / A14 / N2 / A16 / N3 / N4/N5 / N6/N7 / 000 / MtM`),`sort_order` 依序 10/20/30/40/50/60/70/80/90/100
- 建立一個 super user 帳號 `wy` / 密碼可暫定 `changeme`
- 建立一個 `legacy` 假帳號(status = `disabled`),用於匯入時掛舊資料

### 1.3 Excel 匯入腳本

`import_from_excel.py`,接受 `--file` 參數指定 xlsx 路徑。

**處理邏輯**:
1. 用 `openpyxl` 開啟檔案
2. 讀取所有 sheet(包含 Closed 分頁)
3. 對每個 sheet,先讀 `ws.merged_cells.ranges`,把合併儲存格範圍內所有 cell 都填回左上角的值
4. 解析 header row 確認欄位順序
5. 逐列處理:
   - 如果是 `wkXXX` 格式的 separator row,記住目前週次
   - 否則是題目列,建立 `issues` 記錄
   - 對每個 node 欄位,建立 `issue_node_states` 記錄
   - 從 cell 中拆出狀態文字和日期(例如 `UAT done\n2/20 Check in` → state=`uat_done`, check_in_date=`02-20`)
   - 如果在 Closed 分頁,設 `status = closed`
6. 所有歷史記錄的 `updated_by_user_id` 都設為 `legacy`,`updated_by_name_snapshot` 設為 `Legacy`
7. 更新衍生欄位 `latest_update_at`、`all_nodes_done`

**Idempotent 設計**:
- 用 `display_number` 當 natural key
- 重複執行時 UPDATE 而非 INSERT
- 已存在的 issue 會被覆蓋(這是預期行為,因為並行期間 Excel 仍是 source of truth)

**輸出**:
- 列出總共匯入幾題、幾個 cell、幾個 closed
- 列出失敗的列(例如格式錯誤)及原因

### 1.4 登入頁(簡易版)

只支援 hard-code 的 super user。session 用 Flask 內建的 `flask.session`。完整帳號系統留到 Phase 3。

### 1.5 主畫面唯讀版

Route `/` 顯示主畫面,包含:
- Top bar(navbar)
- Toolbar(篩選 / 搜尋暫不實作,只放 placeholder)
- 表格:
  - 週次分組 header
  - 由舊到新排序
  - Cell 顯示狀態色塊 + check-in 日期(若有)+ short note(若有)
  - 紅線顯示(從 settings 讀,如果沒設定就不顯示)
  - 紅線以上 UAT/TBD 套紅色狀態色塊
- On Hold 區塊(空的也沒關係)

**禁用所有編輯**:cell 不可點擊,沒有 + 新增按鈕。

### 驗收

- 登入後看到熟悉的表格
- 資料跟 excel 對得起來(隨機抽 10 題比對)
- 紅線位置對(可在 DB 直接 `INSERT INTO settings VALUES ('red_line_week_year', '2025'), ('red_line_week_number', '20')` 測試)
- 顏色對

### 給接手 AI 的提醒

- Excel cell 的 state 文字可能有大小寫不一致(`UAT done` vs `uat done`),正規化
- 日期解析容錯:`2/20`、`02/20`、`2/20 check in`、`UAT done\n2/20 Check in` 都要能拆
- 如果某 cell 完全空白,`issue_node_states` 也要建立記錄,只是 state = NULL
- 注意 `wk321` 只是範例資料中的編號,實際資料的週次會有變化

---

## Phase 2 — Cell 編輯 + Timeline + 會議紀錄(2~3 天)

**目標**:系統真正能用了,只是還只有你一個人(super user)。

### 2.1 Cell 點擊 → Side Panel

- 點擊 cell 觸發 HTMX 請求 `/issues/<id>/cell/<node_id>`,server 回傳 partial HTML
- HTMX 把 partial 塞到右側 side panel container
- Side panel 用 Alpine.js 控制顯示/隱藏

### 2.2 Side Panel 編輯區

表單欄位:
- State(下拉選單,預設目前狀態)
- Check-in date(date input)
- Short note(text input)
- 更新說明(text input,選填,會記入 timeline)
- 附件(Phase 4 才做,先放 placeholder)

提交按鈕 → POST `/issues/<id>/cell/<node_id>` →
- 更新 `issue_node_states`
- 若 state / check_in_date / short_note 有變動,自動產生一筆 `state_change` 到 `timeline_entries`(記錄 old/new 值)
- 更新 issue 的 cache 欄位 `latest_update_at`、`all_nodes_done`
- HTMX 回傳更新後的 cell partial,只重繪該 cell

### 2.3 Side Panel Timeline

下方顯示該 issue 的所有 timeline entries,時間倒序。
- state_change:藍色 ◐ 圖示,顯示「誰把哪個 node 從什麼改成什麼」
- comment:💬 圖示
- meeting_note:📋 圖示 + 黃色背景

### 2.4 新增留言

`+ 一般留言` 按鈕展開 textarea + submit。
POST `/issues/<id>/timeline/comment` → 建立 entry_type = `comment`。

### 2.5 新增會議紀錄

`+ 會議紀錄` 按鈕展開 textarea + 會議週次選擇 + submit。
POST `/issues/<id>/timeline/meeting_note` → 建立 entry_type = `meeting_note`。

### 2.6 Timeline 篩選

下拉選單 → 改變 query string → HTMX 重新載入 timeline 區塊。

### 2.7 會議模式

獨立頁面 `/meeting/<year>/<week>`,列出該週題目,每題一個 textarea。提交時對每個有內容的 textarea 建立 meeting_note entry。

### 驗收

- 用 super user 改 cell 狀態,主畫面即時更新
- Timeline 顯示變更紀錄
- 留言、會議紀錄能正常記錄
- 會議模式能批次記錄

### 試用里程碑

Phase 2 結束後,Meeting Owner 自己用一週,取代 excel 當測試。

---

## Phase 3 — 帳號系統 + 權限 + Admin 後台(2~3 天)

### 3.1 註冊

- `/register` 頁面
- 表單欄位:username, email, display_name, password, password_confirm
- 驗證:email 格式、username 唯一、password 強度
- 建立 user,status = `pending`
- 顯示「審核中」訊息

### 3.2 登入 / 登出

- `/login` POST 驗證 username + password (bcrypt)
- 檢查 status:active 才允許登入
- session 設定 user_id
- `/logout` 清 session
- session 逾時 1 天

### 3.3 忘記密碼

- `/forgot_password` 輸入 email
- 系統產生 token,存 `password_reset_tokens` 表
- 寄信(透過 SMTP)
- `/reset_password/<token>` 驗證 + 設新密碼
- 設新密碼後 token 標記為 used

### 3.4 SMTP 設定

`config.py` 讀環境變數,Admin 後台可在 settings 表動態調整。寄信用 stdlib `smtplib`。

### 3.5 權限 middleware

每個 route 加裝飾器:
- `@login_required`:未登入導向 `/login`
- `@super_user_required`:只允許 super user
- `@can_edit_node(node_id)`:檢查目前 user 是否屬於某個能編輯該 node 的 group

權限檢查邏輯:
```python
def can_edit_node(user_id, node_id):
    """user 屬於任一 group, 且該 group 在 group_nodes 表中對應該 node。"""
    sql = """
    SELECT 1 FROM user_groups ug
    JOIN group_nodes gn ON ug.group_id = gn.group_id
    WHERE ug.user_id = ? AND gn.node_id = ?
    LIMIT 1
    """
```

### 3.6 Admin 後台

`/admin` 路由群組,super user only。包含:
- `/admin/pending_users` — approve / reject + 順便指派 group
- `/admin/users` — CRUD + disable + 設為 super user
- `/admin/groups` — CRUD + 成員管理 + 指派 nodes
- `/admin/nodes` — CRUD
- `/admin/red_line` — 紅線設定(寫 settings 表 + audit_log)
- `/admin/smtp` — SMTP 設定 + 寄測試信
- `/admin/audit` — audit log 查看

### 3.7 Audit log

定義 helper function `log_audit(actor_user_id, action, target_type, target_id, details)`,在所有敏感操作後呼叫。

### 驗收

- 能註冊新帳號、能 approve、能登入
- 能改密碼、能忘記密碼 reset
- 不同 group 的 user 只能改自己 group 管的 node
- super user 全開
- 一般 user(沒 group)只能讀

### 試用里程碑

Phase 3 結束後,邀 2~3 個信任的同事一起試用。

---

## Phase 4 — 附件 + 版本差異 + 搜尋篩選 + 匯出(2~3 天)

### 4.1 附件上傳

- Side panel 表單支援檔案上傳
- 支援拖拉、點擊選擇、貼上(JS clipboard API)
- 限制:png/jpg/jpeg/pdf,單檔 ≤ 5MB,每筆 entry ≤ 3 個
- 儲存到 `data/attachments/<year>/<month>/<uuid>.<ext>`
- 寫入 `attachments` 表,關聯到對應 timeline_entry
- Timeline 顯示縮圖或檔名,點擊下載

附件下載 route `/attachments/<id>` 要做權限檢查(登入即可,不要讓 attachment URL 被外洩)。

### 4.2 版本差異黃底

- 主畫面載入時讀取目前 user 的 `last_viewed_at`
- 對每個 cell,若 `updated_at > last_viewed_at`,加上 `new-change` CSS class
- Toolbar 上「標記全部已讀」按鈕,POST `/mark_all_read` → 更新 `users.last_viewed_at = NOW()`,然後 reload

### 4.3 搜尋

Toolbar 的搜尋框,支援:
- 題號(精確)
- Topic 關鍵字(LIKE)
- JIRA ticket(精確或部分)

### 4.4 篩選

Toolbar 的下拉選單:
- Owner(從 issues 裡的 distinct owner 列出)
- 狀態(任一 cell 為某狀態)
- 週次範圍(從 / 到)
- 包含某 node 的某狀態

### 4.5 匯出 Excel

按鈕「匯出 Excel」→ POST 當前篩選條件 → server 用 openpyxl 產生 .xlsx → 直接 send_file。

格式儘量接近原始 Excel 排版,讓使用者可以離線檢視或寄給沒帳號的主管。

### 驗收

- 能上傳截圖、能下載
- 黃底正常顯示自上次查看以來的變動
- 搜尋與篩選正常
- 匯出的 xlsx 能用 Excel 開且資料正確

---

## Phase 5 — Dashboard + Calendar + Closed + 批次操作(2~3 天)

### 5.1 Summary Dashboard

`/dashboard` 路由,變成登入後的預設首頁(把 `/` 改成 redirect 到 `/dashboard`,主畫面改路由為 `/issues`)。

實作每個 active node 一張卡片的 grid,計算邏輯:
```sql
-- 紅線以上未完成
SELECT COUNT(DISTINCT i.id)
FROM issues i
JOIN issue_node_states s ON i.id = s.issue_id
WHERE s.node_id = ?
  AND i.status = 'ongoing'
  AND s.state NOT IN ('done', 'unneeded')
  AND ((i.week_year < ?) OR (i.week_year = ? AND i.week_number <= ?))
```

特殊卡片:Ready to Close、On Hold。

### 5.2 上線行事曆

`/calendar?year=2025&month=5` 月曆檢視。

查詢:
```sql
SELECT s.*, i.display_number, i.topic
FROM issue_node_states s
JOIN issues i ON s.issue_id = i.id
WHERE s.check_in_date BETWEEN ? AND ?
  AND i.status = 'ongoing'
ORDER BY s.check_in_date
```

每個項目顯示 `#題號 node 狀態 ✓按鈕`,✓ 按鈕觸發 HTMX `POST /issues/<id>/cell/<node_id>/quick_done`,直接改 state = `done`。

### 5.3 Closed 分頁

`/closed` 路由,跟主畫面結構類似但只顯示 `status = closed`。

- 預設 LIMIT 50 + 分頁
- 搜尋 / 篩選同主畫面
- Reopen 按鈕(super user only):彈 modal 要求填理由,POST `/issues/<id>/reopen`
- Reopen 後:status = `ongoing`,closed_at / closed_by_user_id / closed_note 清空,寫一筆 timeline + audit_log

### 5.4 關單流程

主畫面的 Ready to Close 標記 + 關單按鈕:
- 在 issues 列表 query 時,把 `all_nodes_done = 1` 的題目特別標記
- 點擊「關單」按鈕 → 彈 modal 填 closed_note → POST `/issues/<id>/close`
- 邏輯:status = `closed`、closed_at = NOW、closed_by_user_id = current_user、closed_note 寫入,寫一筆 timeline(可選 author_name = system)+ audit_log

### 5.5 批次操作

主畫面每列前面加 checkbox,Alpine.js 管理選取狀態。
選取後 toolbar 出現批次動作列:
- Node 下拉
- 狀態下拉
- 共用更新說明
- 套用按鈕

POST `/issues/batch_update`,body 包含 issue_ids、node_id、new_state、note。
邏輯:對每個 issue 都更新 state 並寫一筆 state_change(共用同一個 note)。

### 驗收

- Dashboard 數字正確
- Calendar 顯示正確,快速 ✓ 能改狀態
- Closed 分頁能搜尋,reopen 能正常運作
- Ready to Close 標記正確,關單流程正常
- 批次操作能一次改多題

---

## Phase 6 — 精修 + 部署(1~2 天)

### 6.1 效能優化(視需要)

- 主畫面實測效能,如果 300 題 + 9 node 載入超過 1 秒,加 virtual scrolling
- DB 加適當 index(已在 schema 預留)
- Static asset 加 cache header

### 6.2 錯誤頁

- `/errors/404.html`、`/errors/500.html`、`/errors/403.html`
- Flask error handler 註冊

### 6.3 軟刪除

- 主畫面 query 加 `WHERE is_deleted = 0`
- 刪除按鈕(super user only)只 UPDATE `is_deleted = 1`,不真的 DELETE
- 寫 audit_log

### 6.4 部署

- `.drone.yml` 範例:checkout、install deps、跑 tests(如有)、deploy 到目標機器
- systemd unit file 範例
- nginx reverse proxy 範例
- 部署 / 升級流程文件
- 備份 / 還原流程

### 6.5 正式切換

最後一次從 Excel 匯入覆蓋 DB,停用 Excel。

### 驗收

- 系統穩定運行
- 部署流程能重現

---

## Phase 7 — 後續迭代(post-launch)

不是一次做完,是上線後看實際使用情況決定。可能項目:

- **寄信提醒**:紅線以上題目負責人提醒、每週摘要
- **週報自動產生**:整合 timeline 產生會議週報
- **Gitea API 整合**:讀 Gitea issue 狀態自動同步
- **更多統計圖表**:每週完成題數趨勢、每個 owner 的負擔
- **離職帳號 disable 流程**:批次處理離職員工
- **匯入更多歷史資料**(如果有更早之前的)

---

## 時程粗估

| Phase | 工作日 | 累計 |
|---|---|---|
| 0 | 0.5~1 | 1 |
| 1 | 2~3 | 4 |
| 2 | 2~3 | 7 |
| 3 | 2~3 | 10 |
| 4 | 2~3 | 13 |
| 5 | 2~3 | 16 |
| 6 | 1~2 | 18 |

**全職投入約 3~4 週,兼職約 1.5~2 個月。**

## 試用里程碑

- **Phase 2 結束** → Meeting Owner 自己試用一週
- **Phase 3 結束** → 邀 2~3 個同事試用
- **Phase 5 結束** → 全組推廣,Excel 並行作為 backup
- **Phase 6 結束** → 正式切換,Excel 封存

## 切換策略

1. Day 1:Excel 一次匯入新系統作初始資料
2. 並行期間:Excel 仍是 single source of truth,新系統用來驗證功能
3. 穩定後:重新從 Excel 匯入覆蓋,停用 Excel,正式切換

並行期間如果發現匯入有 bug,在新系統修一次匯入腳本就好,不影響 Excel。
