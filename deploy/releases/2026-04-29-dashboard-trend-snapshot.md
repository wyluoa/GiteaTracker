# Release 2026-04-29 — Dashboard Trend 快照與單一資料源

> 這是版本獨立的升版指南。常態升版流程在 [`deploy/DEPLOY.md`](../DEPLOY.md) §9，
> 本檔只列**本次升版的額外注意事項**。

## 本次升版的核心改動

Dashboard 的兩張趨勢圖（**Topic Cumulative Trend** + **Closing Rate Trend**）
從這版起**單一資料源 = `weekly_trend_data`（Admin → Trend Data 手動輸入）**，
不再從現有 `issues` 即席運算。

為了讓 Meeting Owner 知道「這週要填什麼數字」，Dashboard 上方
Weekly summary 卡新增了一條 **「本週快照」**：顯示當下所有未刪除題目分到
UAT / TBD / Dev / Close 各幾題（每題只歸一類，priority Close > UAT > TBD > Dev）。
Super User 還會看到右側「填入 Trend Data」按鈕，點下去帶 query string
到 Admin → Trend Data，第一列被快照值 prefill。

同時調整了 UAT 類別的定義：**`uat_done` 不再算 UAT**，自然 fall-through 到 Dev。
理由：UAT 類別的語意是「還需要 user 去測試」，UAT done 已測完不該再被催。

---

## TL;DR 升版指令

```bash
cd ~/GiteaTracker
./deploy/migrate.sh                               # 一鍵 backup + stop + pull + migrate + start
```

本次**沒有 DB migration**、**沒有 `requirements.txt` 變動**，`migrate.sh`
跑完即可。

---

## 升版前自檢

```bash
# 跑測試：應該 86 passed（跟上版同數，本次沒新增測試）
venv/bin/pytest -q
```

---

## 本次需要特別注意的地方

### ① 沒填過任何一週的 `weekly_trend_data` → 兩張趨勢圖會消失

**原因**：以前沒填時會 fallback 到 `get_dashboard_trends()` 即席算，
本版這個 fallback 已移除。

**對策**：升版完成後立刻到 **Dashboard** → 找 Weekly summary 卡
→ 看「本週快照」→ 點「填入 Trend Data」→ 儲存第一筆。
之後每週固定流程是：開 Dashboard → 點按鈕 → 儲存。

如果你**已經有歷史 trend data**（升版前手動填過），圖表的歷史線會直接保留，
不會因為這次升版而消失。

### ② UAT 類別定義改變 — 歷史資料不會自動回填

2026-04-29 之前填的 `weekly_trend_data` 是按舊定義（UAT 含 `uat_done`）填的；
之後新填的是新定義。歷史圖整體趨勢仍然有效，但個別週的 UAT/Dev 比例可能在
這個轉折點有小幅跳動，這是預期行為。

要對齊定義，可以到 Admin → Trend Data 手動把對應週的 UAT 移到 Dev。
**沒做也沒事**——這只影響「同一張圖前後定義不一致」的潔癖問題。

### ③ Cell 上的 `uat_done` 顏色與行為**完全不變**

這次的 UAT 類別定義變動只影響 Dashboard 上的「本週快照」與
`weekly_trend_data` 圖。Tracker 主畫面的 cell 顏色、按鈕、Ready to Close
判斷、per-node UAT 統計等，**`uat_done` 仍是獨立的藍色狀態**，跟以前一樣。

### ④ 使用者不需硬重整

本次只動了 Dashboard 的 server-side render 與一個 admin 頁的 JS query
parsing；沒有 base.html / CSRF / session cookie 等需要硬重整的東西。
舊分頁繼續用沒問題（會看不到新的「本週快照」區塊，重新整理後就有）。

---

## 升版後驗證清單

```bash
# 服務健康
curl -s http://127.0.0.1:5000/healthz       # → {"status": "ok"}

# logs 沒噴錯
tail -30 logs/app.log
tail logs/errors.jsonl 2>/dev/null || true
```

進 web 以 super user 登入：

- [ ] Dashboard Weekly summary 卡有看到「本週快照（wkXXX，截至現在）」一行
- [ ] 快照數字（UAT/TBD/Dev/Close）總和 = 未刪除題目總數
- [ ] 點「填入 Trend Data」按鈕 → 跳到 Admin → Trend Data，第一列年/週/數字都已 prefill
- [ ] 確認後按「儲存全部」→ 回 Dashboard，cumulative 圖最右邊出現本週的新柱
- [ ] 沒登入或非 super user 進 Dashboard 時，看到快照但**沒有**「填入 Trend Data」按鈕

---

## Rollback

本次升版**沒有 DB schema 變動**，rollback 只回 code 即可：

```bash
./deploy/stop.sh
git log --oneline -5
git checkout <升版前的 commit hash>
./deploy/start.sh
```

不需要 restore DB。`weekly_trend_data` 是新版主資料源，舊版本沒在用，
保留也沒事。

---

## 疑難排解（本次特有）

### 「本週快照」跟我預期的數字對不上
快照分類是 priority-ordered，每題只歸一類：
1. **Close** = `status = 'closed'`
2. **UAT** = 任一 node 是 `uat`（**不含** `uat_done`）
3. **TBD** = 任一 node 是 `tbd`
4. **Dev** = 其餘（含 `uat_done`、空白、全 done/unneeded 但未關單、on_hold 沒 uat/tbd）

例：一題有 1 個 cell `uat` + 1 個 cell `tbd` → 算 UAT（priority 高的贏）。
詳細邏輯見 `app/models/issue.py::current_phase_snapshot`。

### Admin → Trend Data 第一列沒有被 prefill
檢查網址列是否含 `?prefill_year=...&prefill_week=...&uat=...` 等 query string；
如果 query string 在但仍沒 prefill，可能是 Alpine.js CDN 載入失敗 ——
查 DevTools Console 有沒有 error。手動填也可以，行為跟以前一樣。

### Cumulative 圖只有一根柱（剛填的本週）
正常 —— 圖完全來自 `weekly_trend_data`，你只填了一週就只有一根柱。
之後每週都填一筆就會慢慢長出來。

---

## 改動的檔案

| 檔案 | 改動 |
|---|---|
| `app/models/issue.py` | 移除 `get_dashboard_trends()`，新增 `current_phase_snapshot()` |
| `app/routes/main.py` | dashboard route 改傳 `current_snapshot` |
| `app/templates/dashboard.html` | Weekly summary 卡加「本週快照」+ 按鈕；cumulative chart 改讀 `manual_trend` |
| `app/templates/admin/trend_data.html` | Alpine init 接受 query string prefill |
| `docs/user_guide.html` | §9.2 / §9.4 改寫；新增 §9.2.1 |
| `docs/developer_guide.html` | §6.8 Trend Data 改寫 |
| `docs/handoff/07_design_decisions_qa.md` | 新增兩條 Q&A |
