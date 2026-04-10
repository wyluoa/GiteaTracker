# 原始 Gitea Meeting 泳道流程圖描述

使用者在專案初期分享了一張手繪泳道圖(照片原始檔: `IMG_2158.jpeg`),畫在筆記本上,標示的是 Gitea meeting 的完整理想流程。

## 圖的整體結構

這是一張 5 列 × 4 欄的矩陣:
- **橫軸(4 個階段)**:Before Gitea meeting → Gitea Meeting → Script development + UAT → Close Gitea
- **縱軸(5 個角色)**:Gitea meeting owner / Coordinator in each section / Gitea requestor (first) / QA script owner / Gitea UAT owner (non-first requestor)

每個 cell 裡用圓角方框寫該角色在該階段要做的事,以箭頭連接步驟。

## 各角色詳細步驟

### Row 1: Gitea meeting owner

**Before Gitea meeting**:
- 方框 1: ① Collect Gitea topic, ② Inform participants

**Gitea Meeting**:
- 方框 2: Summary status

**Close Gitea**:
- 方框 3: All nodes have decision (Done / Unneeded), Inform 1st requestor to close

### Row 2: Coordinator in each section

**Before Gitea meeting**:
- 方框: ① Collect Gitea status, ② Assign UAT owner, ③ Invite UAT owner to meeting

**Gitea Meeting**:
- 方框: Update status of each Gitea item

### Row 3: Gitea requestor (first)

**Before Gitea meeting**:
- 方框: Fill first version spec

**Gitea Meeting**:
- 方框: Clarify & discuss issue / spec

**Script development + UAT**:
- 方框: UAT
  - ① build up good / bad case
  - ② Impact survey
- 決策菱形: Spec need to update?
- 方框: Done

### Row 4: QA script owner

**Gitea Meeting**:
- 方框: Check feasibility(箭頭連到右欄的 Script Development)

**Script development + UAT**:
- 方框: Script Development(跨越 row 3 和 row 5 的中間,服務雙方)

### Row 5: Gitea UAT owner (non-first requestor)

**Before Gitea meeting**:
- 方框: File spec (based on UAT result)
- (箭頭向上指回到自己的 Gitea Meeting 欄位,表示會議後會更新)

**Gitea Meeting**:
- 方框: Discuss spec

**Script development + UAT**:
- 方框: UAT
  - min. requirement = do impact survey
- 決策菱形: spec need to update?
- 方框: Done

**Close Gitea**:
- 所有 UAT 完成後 → 虛線箭頭指向 Close Gitea

## 流程解讀

1. **會議前(Before Gitea meeting)**
   - Meeting Owner 收集議題、通知與會者
   - 各 section 的 Coordinator 收集現況、指派 UAT owner、邀請與會
   - First requestor 準備初版 spec
   - 其他非第一 requestor 根據先前 UAT 結果提出更新 spec

2. **會議當下(Gitea Meeting)**
   - Meeting Owner 做 summary status 報告
   - 各 Coordinator 更新各 item 狀態
   - First requestor 釐清討論 issue 和 spec
   - QA script owner 檢查可行性
   - 其他 UAT owner 討論 spec

3. **開發 + 測試(Script development + UAT)**
   - QA script owner 進行 script development
   - First requestor 進行 UAT(建立 good/bad case + impact survey)
   - Non-first requestor 也做 UAT(最低要做 impact survey)
   - 雙方都有「spec 是否需要更新」的決策點,若需要就回到前面的階段,否則往前到 Done

4. **關單(Close Gitea)**
   - Meeting Owner 確認所有 node 都有決議(Done 或 Unneeded)
   - 通知第一位 requestor 執行 close

## 系統化設計對應

這張圖代表「理想流程」,但使用者明確表示「目前可能並沒有完全按照這張圖的流程進行」。新系統的目標不是強制執行這個流程,而是為這個流程提供追蹤、記錄、提醒的工具:

| 泳道圖中的概念 | 新系統對應 |
|---|---|
| 每個角色在每個階段的狀態 | `issue_node_states.state` |
| 狀態變更的歷史 | `timeline_entries` (type=state_change) |
| 會議中的討論 | `timeline_entries` (type=meeting_note) |
| 「Done / Unneeded」的決策 | state 值 `done` / `unneeded` |
| 「Spec need to update」決策點 | 使用者手動把 state 從 UAT done 改回 UAT |
| 「All nodes have decision」 | `issues.all_nodes_done` cache 欄位 + Ready to Close 標記 |
| 「Inform 1st requestor to close」 | Phase 7 寄信提醒功能 |
| Meeting Owner / Coordinator / Requestor / QA / UAT owner 等角色 | 透過 groups + user_groups + group_nodes 實作權限 |

## 圖片原檔

原始照片存在 `IMG_2158.jpeg`。如果你能處理圖片,可以直接查看;若不行,以上文字描述已經捕捉完整資訊。
