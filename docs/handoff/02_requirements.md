# Gitea Meeting Tracker — 需求摘要 (v2)

## 系統目標

把目前用 Excel 維護的 Gitea meeting control table 數位化為內網 Web 服務,讓各 node 負責人能自主更新狀態、減輕單一維護者 (Meeting Owner) 的負擔,並提供歷史追蹤、統計摘要、會議紀錄等 Excel 難以做到的功能。

## 技術棧

- **後端**:Python 3.12 + Flask 3
- **模板**:Jinja2 (後端渲染)
- **前端互動**:HTMX + Alpine.js (無 build step)
- **CSS**:Tabler 或 Pico CSS
- **資料庫**:SQLite
- **附件儲存**:檔案系統 (`attachments/<year>/<month>/<uuid>.<ext>`)
- **部署環境**:RHEL 7/8 內網機器,無 sudo 權限,使用 nohup + PID file 管理,或透過 drone CI/CD 自動部署
- **郵件**:透過內部 mail server 寄發

## 角色與權限

| 角色 | 權限 |
|---|---|
| Super User (Meeting Owner) | 所有權限:新增題目、關單 / 反關單、管理 users 與 groups、指派 group 可編輯的 nodes、approve 註冊申請、後台管理、設定紅線、Excel 上傳更新 |
| Group 成員 | 只能編輯自己所屬 group 可管理的 node 的 cell;可在任何題目新增留言 / 會議紀錄 |
| 一般登入使用者 | 全部 read-only;可新增留言 |
| 未登入訪客 | 無法存取 |

- 一個 user 可以屬於多個 group
- 一個 group 對應多個 nodes
- 一個 node 可以被多個 group 編輯
- 開發者 (QC / Automation Team) 是獨立 group,額外擁有編輯 `UAT path` 欄位的權限

## 帳號管理

- **註冊**:自助註冊,帳號初始狀態為 `pending`,super user 在後台 approve 並指派 group 後才能登入
- **密碼忘記**:自助 reset,系統寄 reset link 到註冊 email
- **Session**:逾時 1 天自動登出

## Nodes (初始清單)

`A10` / `A12` / `A14` / `N2` / `A16` / `N3` / `N4/N5` / `N6/N7` / `000` / `MtM`

- `N4/N5` 和 `N6/N7` 各自是一個 node,名稱包含斜線是歷史命名
- 新增 / 改名 / 停用 node 由 super user 在 Admin 後台操作

## 狀態與顏色

| 狀態 | 顯示文字 | 顏色 | 意義 |
|---|---|---|---|
| Done | `Done` | 深綠 `#27ae60` | **程式已上線** |
| UAT done | `UAT✓` | 藍 `#3498db` | **測試完成但還沒上線**,等批次上線 |
| UAT | `UAT` | 橘 `#e67e22` | 測試中 |
| Developing | `Dev` | 灰 `#95a5a6` | 開發中 |
| TBD | `TBD` | 紫 `#8e44ad` | 未決定 / 等外部因素 |
| Unneeded | `—` | 淺灰 `#bdc3c7` | 這個 node 不需要處理這題 |
| (空) | `·` | 很淺灰 | 還沒填 |

- 狀態之間可以任意切換 (不強制順序)
- 新系統不做相鄰同狀態視覺合併,每個 cell 獨立顯示

## 紅線 (Red Line)

- Super user 手動設定一條 week 邊界 (ISO 年 + 週次)
- 紅線以上(較舊)的題目中,`UAT` 或 `TBD` 狀態的 cell **背景改為紅底白字**,強烈提醒負責人處理
- 紅線可隨時調整

## 資料模型 (高層概念)

### Issue (題目)
- 內部 ID (流水號,系統自動產生,用於外鍵與 URL)
- 顯示題號 (人工填,可跳號)
- Topic 標題
- Requestor 雙欄位:
  - `requestor_user_id` (可 null,連到 users 表)
  - `requestor_name` (自由文字,優先顯示;支援舊資料和外部合作者)
- Owner (系統使用者)
- Issue Status:`Ongoing` / `On Hold` / `Closed`
- Week (ISO 年 + 週次,新增時自動帶入當下週,可改)
- JIRA ticket、ICV、UAT path、Gitea issue 連結
- Cache 欄位:`latest_update_at`、`all_nodes_done`

### Node
- 固定 code (不變) + 顯示名稱 (可改) + 顯示順序 + 是否 active

### Issue Node State (每題 × 每 node 的狀態 cell)
- 狀態 (7 種之一或 null)
- Check-in 日期
- **Short note** (可選,短註記,例如「等廠商 3/15 回覆」,在 cell 下方用小字顯示)
- 最近更新時間、更新者 (user_id + name_snapshot)

### Timeline Entry
- 三種類型:
  - **state_change** (自動產生)
  - **comment** (人工,文字 + 最多 3 附件)
  - **meeting_note** (人工,特殊標記,帶會議週次)
- 存 user_id + name snapshot
- 附件:png / jpg / pdf,單檔 ≤ 5 MB,每筆 ≤ 3 個

### Group / User
- 見前文權限說明
- User 有 `last_viewed_at` 供版本差異黃底使用

## 主畫面 (Ongoing 列表)

- Excel-like 表格,列是題目、欄是 nodes
- **排序**:由舊到新
- **分組**:依 week 分組,可收合展開的 header row
- **Cell 顯示**:狀態色塊 + check-in 日期小字 + short note 小字 + timeline 更新計數 badge
- **版本差異**:自上次查看以來有變動的 cell 用黃底標示,有「標記全部為已讀」按鈕
- **點擊 cell**:開 side panel (詳後)
- **批次操作**:
  - 每列前面有 checkbox
  - 選取多題後上方出現批次動作列「將選取題目的 [某 node] 改成 [某狀態]」
  - 共用同一則更新說明,狀態變更仍會逐題寫入 timeline
- **篩選 / 搜尋**:owner、status、node、週次範圍、topic 關鍵字
- **紅線**:用紅色虛線分隔線標示
- **On Hold 區塊**:Ongoing 下方收合區塊「⏸ On Hold (N)」,預設收合

## Side Panel (點擊 cell)

- 上半:題目 metadata + 該 node 的狀態編輯表單 (狀態、check-in 日期、short note、更新說明、附件)
- 下半:Timeline,時間倒序,三種類型不同樣式,可篩選
- Timeline 上方有 `[+ 一般留言] [+ 會議紀錄]` 按鈕,會議紀錄表單多一個「會議週次」欄位

## 會議模式 (Meeting Mode)

- 主畫面上方有「進入 wkXXX 會議模式」按鈕
- 進入後列出指定週次要討論的所有題目
- 每題旁邊都有快速輸入框,可連續記錄
- 送出後系統自動把每筆分散存到對應題目的 timeline (entry_type = meeting_note)
- 平時用 side panel 個別記,會議當下用會議模式連續記

## Summary Dashboard (登入首頁)

- 每個 node 一張卡片,內容:
  - **紅線以上未完成數** (大字 + 紅色,最搶眼)
  - 總未完成數 (中字)
  - UAT / TBD 細分 (小字)
- 特殊卡片:
  - **Ready to Close** (黃) — 所有 node 完成的題目,可跳到列表手動關單
  - **On Hold** (紅) — 暫停中題目
- 點卡片跳到已篩選的主畫面

## 上線行事曆 (Calendar)

- 月曆檢視,顯示所有有 check-in 日期的 cell
- Cell 改 check-in 日期即時反映
- **快速標記**:可直接在行事曆上把 cell 從 `UAT` / `UAT done` 改成 `Done`,不用進 side panel

## Closed 分頁

- 獨立頁面,預設載入最近 N 筆
- 可搜尋 / 篩選
- **Reopen / Rollback**(super user only):需填理由 (寫入 timeline + audit log)

## Ready to Close 流程

- 所有 node 都是 `Done` 或 `Unneeded` 時自動顯示「✓ Ready to Close」標記
- Super user 手動關單,可填 closed_note
- 關單後題目進入 Closed 分頁

## 匯入

- CLI 腳本 `import_from_excel.py`,可重複執行 (idempotent),用於初始匯入
- **合併儲存格處理**:讀 `ws.merged_cells.ranges`,把範圍內所有 cell 填回左上角的值
- 歷史資料的 updated_by 全部掛在 `legacy` 假帳號
- 已關單題目一併匯入到 Closed 分頁

## Excel 上傳更新(Web)

- Admin → Excel Update,super user 可透過網頁上傳新 Excel 更新現有資料
- 上傳後顯示差異預覽:新增 issue、修改欄位、node 狀態變更
- 衝突標示:DB 值與 Excel 值都不同時黃底標示,讓使用者自行決定
- 逐欄勾選要套用的變更,確認後才寫入
- 所有變更記錄在 timeline 及 audit log

## 切換策略

1. Day 1:用 CLI `import_from_excel.py` 一次匯入作初始資料
2. 並行期:Excel 仍是 source of truth
3. 穩定後:重新匯入覆蓋,停用 Excel
4. 切換後:如需用 Excel 更新,透過 Admin → Excel Update 網頁介面操作

## 其他功能

- **匯出 Excel**
- **軟刪除**
- **Audit log** (super user 敏感操作)
- **寄信提醒** (Phase 7)

## 不在本次範圍

- LDAP / SSO
- Gitea API 整合
- 行動 app
