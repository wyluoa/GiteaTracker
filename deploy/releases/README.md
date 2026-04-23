# deploy/releases/

每次正式升版（含 migration、requirements 變動、或行為改變），在這裡放一份
獨立的升版指南：

```
deploy/releases/YYYY-MM-DD-<short-name>.md
```

這份檔案的職責是**只講本次升版的額外注意事項**，常態流程維持在
`deploy/DEPLOY.md`。

## 該寫什麼

- 本次包含的 commit 清單（`git log --oneline`）
- 是否需要特別的升版順序（e.g. 本次有 `pip install`）
- 使用者**升版後要做什麼**（硬重整？通知？）
- 行為改變清單（使用者會察覺的三件事）
- 升版後驗證步驟
- 這次特有的 rollback 注意
- 疑難排解（上線後最可能被問的問題）

## 不該寫什麼

- 重複 `DEPLOY.md` 已經寫過的常規流程
- 過於技術細節（進 commit message 就好）
- 推測性的未來規劃

## 範本

參考 `2026-04-24-csrf-tests-observability.md`。
