# Gitea Tracker — Project Handoff Package

> **目的**: 這份文件包是「Gitea Meeting Tracker」系統的完整需求與設計交接包。任何 AI 工具或開發者都可以根據這份文件接手這個專案,並繼續實作或修改。

## 這是什麼專案?

一個內部 Web 工具,用來取代目前用 Excel 維護的 Gitea meeting control table。團隊每週開 Gitea meeting 追蹤約 300 個題目在 9 個 node 上的開發、測試、上線狀態。原本由一位 Meeting Owner 一人維護 Excel,系統化後讓各 node 負責人能自主更新狀態,並提供歷史追蹤、權限控制、會議紀錄、儀表板等 Excel 難以做到的功能。

## 為什麼需要這份交接包?

原始討論是中文進行的,經過多輪需求釐清最終確定了完整規格、資料表設計、UI 草圖、分階段實作計畫,並完成了 Phase 0(專案骨架)。為了讓另一個 AI 工具或開發者能無痛接手,把所有討論結果、決策理由、現有產出整理在一起。

## 文件導覽

依**閱讀順序**排列。第一次接手請從上往下讀。

| 檔案 | 內容 | 用途 |
|---|---|---|
| `README.md` | 本檔,總覽 | 從這裡開始 |
| `01_context.md` | 業務背景、現有流程、現有 Excel 結構 | 理解 domain |
| `02_requirements.md` | 完整功能需求 | 開發時的主要參考 |
| `03_database_schema.md` | SQLite schema + 設計理由 | 資料層實作 |
| `04_ui_wireframe.html` | 視覺化 UI 草圖(瀏覽器打開) | 前端實作參考 |
| `05_ui_wireframe_description.md` | UI 草圖的純文字描述 | 給沒有視覺能力的 AI |
| `06_phase_plan.md` | Phase 0~7 詳細實作計畫 | 工作分配與里程碑 |
| `07_design_decisions_qa.md` | 釐清過程中的關鍵決策 Q&A | 理解「為什麼這樣設計」 |
| `08_glossary.md` | 領域術語對照表 | 避免誤解 |
| `reference/` | 補充資料(原始流程描述、Excel 結構) | 背景參考 |
| `phase0_starter_code/` | 已完成的 Phase 0 程式碼 | 開發起點 |

## 目前進度

| Phase | 內容 | 狀態 |
|---|---|---|
| 0 | 專案骨架、DB init、placeholder 首頁 | ✅ **已完成**(`phase0_starter_code/`) |
| 1 | 核心資料模型 + 主畫面唯讀版 + Excel 匯入 | 待開發 |
| 2 | Cell 編輯 + Timeline + 會議紀錄 | 待開發 |
| 3 | 帳號系統 + 權限 + Admin 後台 | 待開發 |
| 4 | 附件 + 版本差異 + 搜尋篩選 + 匯出 | 待開發 |
| 5 | Dashboard + Calendar + Closed 分頁 + 批次操作 | 待開發 |
| 6 | 精修 + 部署 + 正式切換 | 待開發 |
| 7 | 寄信提醒等後續迭代 | 待開發 |

## 技術棧(已決定,不可變更)

- **語言**: Python 3.12(專案主機有 3.9 / 3.12 / 3.14 可選,選 3.12 因為生態最穩)
- **後端框架**: Flask 3 + Jinja2(後端渲染)
- **前端互動**: HTMX + Alpine.js(無 build step,從 CDN 載入)
- **CSS 框架**: Tabler(從 CDN 載入)
- **資料庫**: SQLite(單檔,放在 `data/` 目錄)
- **附件儲存**: 檔案系統(`attachments/<year>/<month>/<uuid>.<ext>`)
- **部署環境**: RHEL 7/8 內網機器
- **部署方式**: 手動 `python main.py` + systemd,或透過 `.drone.yml` 自動化
- **郵件**: 透過內部 mail server(密碼 reset、未來提醒)

**為什麼這個技術棧?**

- 團隊熟 Python,Flask 學習曲線最低
- HTMX + Alpine.js 比 React/Vue 簡單得多,但能達成 SPA 等級的互動體驗
- 沒有 npm/webpack/build step,部署就是 `python main.py`
- SQLite 對 300 題 × 9 node × 三年歷史的資料量綽綽有餘,且團隊已有 SQLite 服務經驗
- 全部 server-side rendering 對 SEO / 資料權限控制都更安全(內網工具不需要 API-first)

## 給接手 AI 的工作建議

1. **先讀完 `01_context.md` 跟 `02_requirements.md`**,確保理解業務 domain
2. **看 `04_ui_wireframe.html`**(用瀏覽器),不能看圖的話讀 `05_ui_wireframe_description.md`
3. **看 `06_phase_plan.md`** 知道目前在哪、下一步要做什麼
4. **看 `07_design_decisions_qa.md`** 理解為什麼某些設計這樣選,避免重新討論已決定的事
5. **看 `phase0_starter_code/README.md`** 了解現有程式碼結構
6. 開始開發 Phase 1 之前,可以先把 `phase0_starter_code/` 跑起來確認環境

## 重要約束

- **不可破壞既有的命名慣例**:node 名稱例如 `N4/N5`、`A10`、`MtM` 是組織內既定詞彙,不要「改善」
- **不可強制狀態順序**:狀態間可任意切換(例如 `UAT done → UAT` 因需求變更而回退是合法的)
- **不可預設一切都是英文使用者**:介面文字要支援中文,因為這是台灣團隊
- **資料完整性優先**:寧可儲存多餘 cache 欄位也不要每次查詢都 join + group by(主畫面效能要求)
- **Audit trail 不可被覆蓋**:任何狀態變更、關單、權限變動都要留痕
- **Soft delete only**:刪除是標記,不是真的 DROP

## 對話來源

這個專案的需求是經過 9 輪以上的對話釐清而來,所有關鍵決策都記在 `07_design_decisions_qa.md`。如果你(接手的 AI)發現需求看似矛盾,**先去查 Q&A 文件**,通常會發現是某個 trade-off 的結果。

## 使用者背景

- 主要使用者是 Meeting Owner(目前是「WY」)
- 公司是 Cadence(EDA 軟體公司,從原始流程圖筆記本可見)
- 團隊在台灣新竹
- 目前所有題目維護由一人負擔,該使用者希望系統化以減輕負擔
- 已有近 3 年、約 300 題的歷史資料需要遷移
