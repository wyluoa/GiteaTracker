# 08 — 術語對照表 (Glossary)

這份文件幫助接手者理解本專案的 domain 術語。有些詞是組織內慣用語,有些是這個專案創造的詞彙。

## 業務術語

| 術語 | 英文 | 說明 |
|---|---|---|
| **Gitea** | — | 開源的 Git 平台(類似 GitHub),團隊用來管理 issue。**不要混淆**:本專案名稱是 "Gitea Tracker",但它不是 Gitea 的 fork,也不直接整合 Gitea API,只是追蹤從 Gitea issue 衍生出來的會議討論題目 |
| **Gitea meeting** | — | 團隊每週召開的會議,討論 Gitea 上收到的 issue 要怎麼處理 |
| **題目 / Issue** | Issue (topic) | 一個需要追蹤的開發項目,通常對應一個 Gitea issue。這份文件裡「issue」和「題目」混用,意思相同 |
| **Node** | Node | 一個系統元件或子系統,每題需要在多個 node 上分別實作 / 測試 / 上線。具體 node 有 A10、A12、A14、N2、A16、N3、N4/N5、N6/N7、000、MtM,名稱來自組織內部歷史 |
| **Requestor** | Requestor | 提出題目的人(可能是使用者或開發者) |
| **Owner** | Owner | 題目的主要負責人 |
| **Coordinator** | Coordinator | 某個 section 的協調者(在原始泳道圖中的角色) |
| **UAT** | User Acceptance Test | 使用者驗收測試 |
| **UAT owner** | UAT owner | 負責執行 UAT 的人 |
| **QC Team / Automation Team** | QC / Automation Team | 專門做自動化測試腳本的團隊,本系統中被視為一個獨立 group,額外擁有編輯 UAT path 的權限 |
| **Check-in date** | Check-in date | 預計某 node 上線的日期。填寫者通常是該 node 的負責人,實際上線通常是批次進行 |
| **Impact survey** | Impact survey | 影響範圍調查,UAT 流程的一部分 |
| **JIRA** | JIRA | 專案管理工具,題目會對應到一個 JIRA ticket |
| **ICV** | ICV | 組織內部欄位,通常空白 |
| **MtM** | Mark-to-Market | 金融領域術語,此處是某個特定 node 的名稱 |

## 狀態術語

| 狀態 | 英文 | 說明 | 是否屬於「未完成」 |
|---|---|---|---|
| Done | `done` | **程式已上線**。完整結束 | 否(已完成) |
| UAT done | `uat_done` | **測試完成但還未上線**,等批次上線 | 否(但在 Ready to Close 檢查時算未完成,因為 != 'done' 也 != 'unneeded') |
| UAT | `uat` | 測試中 | 是 |
| Developing | `developing` | 開發中 | 是 |
| TBD | `tbd` | 未決定 / 等外部因素 | 是 |
| Unneeded | `unneeded` | 這個 node 不需要處理這題 | 否(不需要) |
| (空) | NULL | 還沒填 | 是 |

**重要**:Ready to Close 的判斷是「所有 node 狀態 ∈ {done, unneeded}」。`uat_done` **不**算完成,因為還沒真的上線。

## Issue 層級狀態

| 狀態 | 英文 | 說明 |
|---|---|---|
| Ongoing | `ongoing` | 進行中,顯示在主畫面 |
| On Hold | `on_hold` | 整題暫停(等外部、優先級下調、requestor 離職等)。顯示在主畫面下方收合區塊 |
| Closed | `closed` | 已關單,顯示在 Closed 分頁 |

## 系統術語

| 術語 | 說明 |
|---|---|
| **Red line / 紅線** | 使用者手動設定的一條週次邊界。線之上(較舊)的題目中,`UAT` 或 `TBD` 狀態 cell 會用紅色色塊顯示,提醒負責人處理 |
| **Side panel** | 主畫面點擊 cell 後從右側滑出的編輯 + timeline 面板 |
| **Timeline** | 每題的事件歷史,包含狀態變更、一般留言、會議紀錄 |
| **Timeline entry** | timeline 裡的一筆事件。分三種 type:`state_change` / `comment` / `meeting_note` |
| **State change** | 狀態變更事件,系統自動產生的 timeline entry,記錄 old/new state/check_in_date/short_note |
| **Comment / 一般留言** | 人工建立的 timeline entry,用於非狀態變更的討論 |
| **Meeting note / 會議紀錄** | 人工建立的 timeline entry,附帶會議週次,用於記錄會議當下討論重點 |
| **Meeting mode / 會議模式** | 主畫面上一個特殊的批次記錄頁面,讓 meeting owner 在會議當下連續為多題記錄 meeting note |
| **Short note** | cell 層級的持續性短註記,會一直顯示在主畫面 cell 下方。跟 timeline 互補:timeline 是一次性事件,short note 是當前狀況 |
| **Ready to Close** | 一題的所有 node 狀態都是 `done` 或 `unneeded` 時,系統自動顯示的標記。Super user 看到後可手動關單 |
| **Reopen / Rollback** | 把已關單的題目拉回 Ongoing。Super user only,需要填理由 |
| **Version diff / 版本差異** | 自上次查看以來有變動的 cell 用黃色底標示。每個 user 獨立(你的黃底跟別人的不同) |
| **Batch operation / 批次操作** | 在主畫面勾選多題,一次把某個 node 改成某狀態 |
| **Meeting Owner** | 負責主持 Gitea meeting、維護追蹤表的人。在本系統中通常有 super user 權限 |
| **Super user** | 系統的管理員角色,能做所有事:管理 users/groups/nodes、關單/反關單、改紅線、查 audit log 等 |
| **Group** | 權限分組。一個 group 對應多個 node、包含多個 user。user 透過 group 取得編輯某 node 的權限 |
| **Excel Update** | Admin 後台的 Excel 上傳更新功能。上傳 .xlsx 後系統比對 DB 差異,顯示預覽,衝突欄位黃底標示,逐欄勾選後確認寫入。變更記錄在 timeline 及 audit log |
| **Legacy user** | 假帳號,狀態為 disabled,只用於匯入舊資料時的 `updated_by` 欄位 |

## 技術術語(常被混淆)

| 術語 | 說明 |
|---|---|
| **Issue ID(內部)** | `issues.id`,流水號、不可改、用於外鍵與 URL |
| **Display number(題號)** | `issues.display_number`,人工填寫的顯示題號,可跳號(例如 156、158、162),保留使用者現有的編號習慣 |
| **Node code** | `nodes.code`,固定內部識別符,例如 `n_a10`,不變 |
| **Node display name** | `nodes.display_name`,顯示用名稱,例如 `A10`、`N4/N5`,可改 |
| **ISO week / ISO 週次** | 遵循 ISO 8601 的週次定義,週一開始,每年有 52~53 週 |
| **Name snapshot** | 在 timeline / state 變更時儲存當下的 user display_name,離職或改名後仍能顯示當時名稱 |
| **Cache column** | `issues.latest_update_at`、`issues.all_nodes_done` 這類衍生欄位,每次相關變動時一起更新,避免查詢時重算 |
| **Soft delete** | 不真的 DELETE,只把 `is_deleted` 設為 1,資料仍在 |
| **Audit log** | 系統層級的操作紀錄,只有 super user 能看。跟 timeline 不同,timeline 是題目層級給所有人看 |
| **Settings 表** | Key-value 系統設定,用來存紅線位置、SMTP 設定等可動態調整的值 |

## 容易誤會的組合詞

### `N4/N5` 和 `N6/N7` 是 node 名稱,不是兩個 node 的合併

這兩個 node 的名稱恰好包含斜線,但在 DB 和系統中是**單一 node**,請當作一整個 token 處理。不要自作聰明去拆開或合併。

### `UAT done` 不是 `Done`

兩個是完全不同的狀態:
- `UAT done` = 測試完成,但程式還沒上線
- `Done` = 程式已上線

業務上有重要區別,請勿合併。

### `Meeting` 指的是 Gitea meeting,不是系統內的「會議模式」

- **Gitea meeting** = 真實世界的團隊會議
- **Meeting mode** = 系統裡為了在會議當下連續記錄 meeting note 而設計的 UI 頁面

### `Issue` 在本專案中同時可以指:
1. 題目(issues 表中的一筆記錄)
2. Gitea issue(Gitea 系統上的 issue,本系統可能有連結)

討論時通常指 (1),但 `gitea_issue_url` 欄位指的是 (2)。
