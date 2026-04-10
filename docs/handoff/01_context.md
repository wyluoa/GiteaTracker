# 01 — 業務背景與現有系統

## 業務背景

**Gitea Meeting** 是一個內部團隊每週舉辦的會議,用來追蹤開發題目(來自使用者透過 Gitea issue 提出的需求)在多個系統 node 上的開發、測試、上線狀態。

每個題目通常是一個改動或新功能,需要在多個 node 上分別實作、測試、上線。每個 node 由不同的負責人(coordinator + UAT owner)管理。Meeting Owner 在每次會議前收集議題、開會時主持討論並更新狀態,會後追蹤進度直到所有 node 都完成、最終 close 該 Gitea issue。

這個流程已經運作將近 3 年,累積近 300 個題目。所有狀態目前都記錄在一份 Excel 試算表中,由 Meeting Owner 一人維護。

## 現有流程(Swimlane)

原始的會議流程被畫成一張泳道圖(在原始討論中由使用者拍照分享),分為四個階段、五個角色:

### 階段
1. **Before Gitea meeting** — 會議前準備
2. **Gitea Meeting** — 會議當下
3. **Script development + UAT** — 開發 + 使用者驗收測試
4. **Close Gitea** — 結案

### 角色與職責

| 角色 | Before meeting | Gitea Meeting | Script development + UAT | Close Gitea |
|---|---|---|---|---|
| **Gitea meeting owner** | 收集 Gitea topic、通知參與者 | Summary status | | 所有 node 都決定後(Done/Unneeded),通知第一位 requestor 關單 |
| **Coordinator (各 section)** | 收集 Gitea status、指派 UAT owner、邀請與會 | 更新每個 Gitea item 的狀態 | | |
| **Gitea requestor (first)** | 填初版 spec | 釐清討論 issue / spec | UAT(建立 good/bad case + impact survey)→ 視 spec 是否需更新 → Done | |
| **QA script owner** | | Check feasibility | Script development | |
| **Gitea UAT owner (non-first requestor)** | File spec(based on UAT result) | Discuss spec | UAT(最低要做 impact survey)→ 視 spec 是否需更新 → Done | Close Gitea |

### 真實情況 vs 理想流程

使用者明確表示:**這張泳道圖是理想流程,實際運作時並沒有完全照走**,很多步驟比較鬆散或靠團隊默契完成。系統化的目的不是強制遵守流程,而是讓記錄、追蹤、提醒變得更有結構,降低 Meeting Owner 的維護負擔。

## 現有 Excel 結構

使用者提供了一份簡化的範例 Excel(`gitea_table.xlsx`),欄位如下:

### 欄位

| 欄位 | 內容 | 範例 |
|---|---|---|
| (第一欄,無 header) | 題號 或 週次 separator | `156` / `wk321` |
| Status | 題目狀態 | `Ongoing` |
| Owner | 題目負責人 | `WY`、`Stan`、`SH`、`IC`、`Ivy` |
| **A10** | Node 1 狀態 | `Done` / `Developing` / `UAT` / `UAT done` / `Unneeded` / 空 |
| **A14** | Node 2 狀態 | (同上) |
| **N2** | Node 3 狀態 | (同上) |
| **A16** | Node 4 狀態 | (同上) |
| **N3** | Node 5 狀態 | (同上) |
| **N4/N5** | Node 6 狀態(注意這是**一個** node 不是兩個) | (同上) |
| **N6/N7** | Node 7 狀態(同上) | (同上) |
| **000** | Node 8 狀態 | (同上) |
| **MtM** | Node 9 狀態 | (同上) |
| JIRA | JIRA ticket 編號 | `N2-001`、`N3-102` |
| ICV | (補充欄位,通常空) | |
| UAT path | UAT 測試路徑 | `path1`、`path2` |
| Topic | 題目標題 | `request title` |

**注意**:在新系統中,使用者要求**新增 A12** 這個 node,所以最終 node 順序是:
`A10 / A12 / A14 / N2 / A16 / N3 / N4/N5 / N6/N7 / 000 / MtM`

### 範例資料(從原始 Excel 截取)

```
            Status   Owner  A10        A14   N2          A16   N3              ...
wk321
156         Ongoing  WY     Done       Done  Done        Done  UAT             ...
wk322
158         Ongoing  Stan   Developing Developing Developing  Developing  Developing ...
162         Ongoing  Stan   Done       Done  UAT done    Done  UAT done        ...
wk323
201         Ongoing  WY     Unneeded   Done  Done        Done  UAT             ...
212         Ongoing  SH     Done       Done  Done        Done  Done            ...
```

### 週次標記

題號之間穿插 `wk321`、`wk322`... 這種 separator row,代表「該題在這一週的會議被討論」。週次是手動填寫的,對應 ISO 週次(每年從 wk1 開始)。

`wk321` 只是範例資料,實際週次會跟著 ISO 標準走。

### Cell 內容變體

實際 Excel 中的 cell 不只是純狀態文字,有時會附加日期備註,例如:
- `UAT done\n2/20 Check in`(表示 UAT 完成,預計 2/20 上線)
- `UAT done\n2/10 Check in`

這是因為 Excel 儲存格能填寫的方式有限,使用者只能把多種資訊塞進同一格。在新系統中,這會被拆解成兩個獨立欄位:`state`(狀態) 和 `check_in_date`(預計上線日)。

### 合併儲存格

Excel 中有少數合併儲存格的情況,**只發生在同一列**(例如某一題目的 A14、N2、N3 都是同樣狀態 `UAT done`,Excel 上會合併顯示)。匯入時需要用 `openpyxl` 讀取 `ws.merged_cells.ranges`,把合併範圍內所有 cell 都填回左上角的值。

新系統**不會做相鄰同狀態的視覺合併**,每個 cell 獨立顯示,避免互動複雜化。

### 紅線(Red Line)

Excel 中有一條手動劃的「紅線」,線之上的題目代表「已經拖很久了,負責人應該關注」。紅線之上的 `UAT` 或 `TBD` 狀態 cell 在 Excel 中會被標紅字提醒。新系統會把這個概念數位化:super user 設定一條 ISO 週次的紅線,系統自動把紅線之上的 UAT/TBD cell 改成紅色狀態色塊。

### 版本管理

目前使用者完全靠**檔名分版本**(例如 `gitea_table_v1.xlsx`、`gitea_table_v2.xlsx`)做版本控管,效用很有限,也很難回溯特定 cell 在某時間點的值。每次狀態變更會用黃色醒目底色標示,提醒讀者「這版改了什麼」。新系統會用 timeline 與 per-user 「上次查看時間」徹底解決這個問題。

### Closed 分頁

目前 Excel 已有獨立分頁存放已關單(所有 node 都 `Done` 或 `Unneeded`)的題目。新系統會比照辦理。

## 痛點清單(來自使用者的原話)

1. 「由我一人來記錄或是維護已經有點吃力」
2. 「也有很多已經在 table 上面很久的題目懸而未決」
3. 「我目前有想要把這個 excel 表格系統化」
4. 「目前的版本紀錄只有靠 excel 分檔名來做版本控管,基本上作用很有限」
5. 「目前紅線的時間線比較隨興沒有特別規範」
6. 各 node 負責人無法自主更新狀態,所有更新都要透過 Meeting Owner

這些就是新系統要解決的核心問題,**不要在實作中失焦**。
