# Release 2026-04-29 — Excel 匯出大改版 + 匯入推年

> 這是版本獨立的升版指南。常態升版流程在 [`deploy/DEPLOY.md`](../DEPLOY.md) §9，
> 本檔只列**本次升版的額外注意事項**。
> 同日另一個 release：`2026-04-29-dashboard-trend-snapshot.md`，可一起升。

## 本次升版的核心改動

### 1. Excel 匯出全面改版（`/export`）

兩張 sheet：`Ongoing`（含 On Hold 混排）+ `Closed`，都用同一套樣式：

- **字體**：theme 改成 Latin=Calibri / East Asian=Microsoft JhengHei，自動依字元切換
- **狀態靠字體色區分（cell 不填色）**：Done 深綠 / UAT Done 藍 / UAT 橘 / TBD 紫 / Dev 灰 / Unneeded 淺灰斜體
- **紅線以上的 UAT/TBD 改紅色粗體**（覆蓋原狀態色），方便一眼掃出久卡老題
- 頂端 metadata 列（匯出時間/匯出者/紅線/範圍/題目數）+ 圖例
- `#` 欄是 Gitea 超連結（藍底線），點下去開原 issue
- State cell 三行內容：`狀態名 / YYYY-MM-DD / short_note`，沒有的行省略
- 多兩欄：`ICV` 與 `Group Label`
- 凍結窗格：第 1-3 列 + 前 3 欄
- 檔名帶 username：`gitea_tracker_YYYY-MM-DD_<username>.xlsx`，多人匯出不撞名
- Status 欄改友善英文 `Ongoing / On Hold / Closed`，pending close 加 `(待確認關單)` 後綴
- Owner 欄沿用現有 tracker 顯示來源（`requestor_name`，所見即所得）

### 2. Tracker 上「匯出 Excel」按鈕變 dropdown

兩個選項：
- **匯出全部**：所有 Ongoing / On Hold / Closed
- **匯出目前篩選結果**：套用畫面上 search/filter/進階條件後再匯（沒套條件時 disabled）

### 3. 匯入 Excel 的 check-in date 從 `MM-DD` 改成 `YYYY-MM-DD`

cell 寫 `2/20` 這類沒年份的 check-in，匯入時自動推年：
- MM-DD 在該題 ISO Monday 之後 → 同一年
- MM-DD 在該題 ISO Monday 之前 → 下一年（rolling 進新年）

例：題目 wk626（2026-06-22 那週），cell 寫 `2/20` → 存成 `2027-02-20`；寫 `8/15` → 存成 `2026-08-15`。
推錯了從 Side Panel 直接改成正確日期。

歷史 `MM-DD` 列不會自動回填，但 export 顯示時會即時推年成 YYYY-MM-DD。

### 4. 每次 `/export` 寫 `audit_log`

action = `export_excel`，details 含 `filtered`、`ongoing_n`、`closed_n`。PII 外流可追溯。

### 5. schema.sql 新增 `NAMING NOTE` 註解

`requestor_name` 欄位實際存 Owner（開發者），這次加註解避免後人誤解。
資料模型沒動。

---

## TL;DR 升版指令

```bash
cd ~/GiteaTracker
./deploy/migrate.sh                               # 一鍵 backup + stop + pull + migrate + start
```

**沒有 DB migration**、**沒有 `requirements.txt` 變動**，`migrate.sh` 跑完即可。

---

## 升版前自檢

```bash
venv/bin/pytest -q
# → 132 passed（舊 95 + 新 37 export/year-inference 測試）
```

---

## 本次需要特別注意的地方

### ① 使用者第一次匯出可能會驚訝「怎麼變這樣」

之前的匯出是大藍底白字 header + 純文字 body，這版整個重做。
**對策**：升版完知會使用者「Excel 匯出檔長得不一樣了」，讓他們不要以為是 bug 或檔案壞了。

### ② Closed 題目現在也會匯出來

之前 `/export` 只出 Ongoing + On Hold，這版多一張 `Closed` sheet。
若使用者主要是給自己人看不會差，給外部審計或客戶看的話注意是否要先 filter 掉。

### ③ 匯入推年只影響「之後新匯入的資料」

升版前 DB 已有的 `MM-DD` 列**保持原樣**，不會自動回填。
- 主因：歷史推測有風險，舊題的 issue_week 可能離現在很遠，推錯機率高
- 顯示層用同樣規則即時推年 → 看起來是 YYYY-MM-DD，但 DB 還是 MM-DD
- 想統一格式可手動到 Side Panel 編輯成 YYYY-MM-DD（會 round-trip 為 ISO）

### ④ 使用者不需硬重整

只動了路由 / 模板 / 後端 export 邏輯，沒碰 base.html / CSRF / cookie。
舊分頁繼續用沒問題（dropdown 看不到，按下去是舊單按鈕邏輯，重整後就正常）。

### ⑤ JIRA 欄沒做超連結

只有 `#` 欄做了 Gitea 超連結。要做 JIRA 超連結請先在 Admin → Settings 加上 JIRA base URL（目前還沒這個設定）。

---

## 升版後驗證清單

```bash
# 服務健康
curl -s http://127.0.0.1:5000/healthz

# logs 沒噴錯
tail -30 logs/app.log
tail logs/errors.jsonl 2>/dev/null || true

# Pytest 全綠
venv/bin/pytest -q
```

進 web 以 super user 登入，依序測：

- [ ] 開 `/tracker`，右上有「匯出 Excel ▾」dropdown
- [ ] 點「匯出全部」→ 下載 `gitea_tracker_<TODAY>_<your_username>.xlsx`
- [ ] 開檔，左下兩個 sheet：`Ongoing` 與 `Closed`
- [ ] Row 1 = metadata（匯出時間/匯出者/紅線/範圍/題目數）
- [ ] Row 2 = 圖例
- [ ] Row 3 = header（# / Status / Owner / 各 Node / JIRA / UAT Path / Topic / ICV / Group Label）
- [ ] 紅線以上的 UAT / TBD cell 是紅色粗體
- [ ] 紅線以下的 UAT 是橘色粗體
- [ ] 點 # 欄藍字超連結 → 跳到 Gitea Issue 頁
- [ ] 在 tracker 用「Owner」filter 篩一個人，回到 dropdown 點「匯出目前篩選結果」→ Excel 只有那個 Owner 的題
- [ ] Admin → Audit Log 篩 `action=export_excel`，看到剛剛的兩筆紀錄

---

## Rollback

本次升版**沒有 DB schema 變動**，rollback 只回 code 即可：

```bash
./deploy/stop.sh
git log --oneline -5
git checkout <升版前的 commit hash>
./deploy/start.sh
```

---

## 改動的檔案

| 檔案 | 改動 |
|---|---|
| `app/excel_export.py` | **新增** — 匯出邏輯（theme + 樣式 + workbook builder） |
| `app/excel.py` | `parse_cell()` 多 `issue_week_year/issue_week_number` kwargs；新增 `infer_check_in_year()` |
| `app/routes/main.py` | `/export` 全改寫；新增 `_apply_tracker_filters_from_args()` 給 filtered 模式共用；audit_log；username 進檔名 |
| `app/models/issue.py` | 新增 `get_all_closed()`（給 Closed sheet） |
| `app/templates/tracker.html` | 「匯出 Excel」改 dropdown |
| `app/schema.sql` | `requestor_name` 加 NAMING NOTE 註解 |
| `import_from_excel.py` | CLI `parse_cell` 改成 thin wrapper（與 web 共用 single source） |
| `tests/test_excel_export.py` | **新增** — 17 cases |
| `tests/test_year_inference.py` | **新增** — 12 cases |
| `docs/user_guide.html` | §4.10 匯出說明改寫；FAQ 新增推年 Q&A |
| `docs/developer_guide.html` | §7.5 / §7.6 新增匯出 + 推年技術細節 |
| `docs/handoff/07_design_decisions_qa.md` | 新增 5 條鎖死決策 |
