# 原始 Excel 結構說明

此文件描述使用者目前用來維護 Gitea meeting 狀態的 Excel 檔案結構。原始檔在 `original_sample.xlsx`。

## 檔案基本資訊

- 檔名慣例(使用者現況): `gitea_table.xlsx`,版本控管靠檔名(例如 `gitea_table_v2.xlsx`、`gitea_table_20250415.xlsx`)
- 實際使用中的 workbook 有多個 sheet(至少一個 Ongoing + 一個 Closed)
- 範例檔 `original_sample.xlsx` 只包含一個簡化的工作表

## Sheet 結構

### Header(第一列)

```
(A1 空) | Status | Owner | A10 | A14 | N2 | A16 | N3 | N4/N5 | N6/N7 | 000 | MtM | JIRA | ICV | UAT path | Topic
```

注意事項:
- 第一欄 A1 沒有 header,但底下會放題號或週次 separator
- 範例檔**沒有** A12 欄位(A10 和 A14 中間),但**新系統需要**在此位置加入 A12

### 資料列模式

資料列分兩種:

**1. 週次 separator row**(例如 `wk321`):
- A 欄填 `wk321` / `wk322` / `wk323` 等
- 其他欄位全空
- 用途:告訴讀者下面的題目是在哪一週被討論

**2. 題目列**:
- A 欄填題號(例如 156、158、162)
- Status、Owner、各 node 狀態、JIRA、ICV、UAT path、Topic 依序填入
- 題號人工編制,可跳號

## Cell 值的類型

### 基本狀態文字

每個 node cell 填入以下其中之一:
- `Done` — 已完成
- `Developing` — 開發中
- `UAT` — 測試中
- `UAT done` — 測試完成(注意:跟 Done 不同!)
- `Unneeded` — 此 node 不需處理
- (空) — 尚未填寫

### 混合內容(帶日期備註)

有時候 cell 會帶額外資訊,用換行分隔:

```
UAT done
2/20 Check in
```

或

```
UAT done
2/10 Check in
```

這是因為 Excel 儲存格表達能力有限,使用者把「狀態 + 預計上線日」擠在同一格。

**匯入新系統時**必須:
1. 拆出第一行的狀態文字
2. 從第二行(如有)的「M/D Check in」格式解析出日期
3. 分別存入 `state` 和 `check_in_date` 欄位

### 合併儲存格

某些題目的相鄰 node 如果狀態都一樣(例如 A14、N2、N3 都是 `UAT done`),使用者會用 Excel 的合併儲存格功能把它們合起來顯示,視覺上更清爽。

**特性**:
- 只發生在**同一列**(橫向合併)
- 跨 node 欄位
- 頻率:偶爾發生,不是每題都有

**匯入處理**:
```python
import openpyxl
wb = openpyxl.load_workbook("gitea_table.xlsx")
ws = wb["工作表1"]

# 先展開合併儲存格
for merged_range in list(ws.merged_cells.ranges):
    top_left_cell = ws.cell(merged_range.min_row, merged_range.min_col)
    value = top_left_cell.value
    ws.unmerge_cells(str(merged_range))
    for row in range(merged_range.min_row, merged_range.max_row + 1):
        for col in range(merged_range.min_col, merged_range.max_col + 1):
            ws.cell(row, col).value = value

# 然後正常逐列讀取
for row in ws.iter_rows(values_only=True):
    ...
```

## 黃色醒目底(版本差異標示)

使用者在每個版本更新時,會把變動的 cell 用黃色背景標示,給其他讀者「這版改了什麼」的提示。新版本發布時再清除。

新系統不需要匯入這個黃底資訊(匯入時是 snapshot,不需要知道哪些 cell 是最近改的)。新系統用 per-user 「上次查看時間」自動計算版本差異。

## 紅字(紅線標示)

使用者在 Excel 中用紅字標示紅線以上的 UAT / TBD cell,提醒負責人關心。紅線本身的位置沒有明確記錄在 Excel 內,是使用者腦中的概念或在某欄手動註記。

新系統把紅線變成顯式的 `settings` 記錄。

## Sample Data

從原始 `original_sample.xlsx` 的節錄:

```
Row |  #     |  Status  | Owner |  A10         |  A14         |  N2          |  A16         |  N3          |  N4/N5       |  N6/N7       |  000         |  MtM         |  JIRA   |  ICV |  UAT path |  Topic
----|--------|----------|-------|--------------|--------------|--------------|--------------|--------------|--------------|--------------|--------------|--------------|---------|------|-----------|---------
 1  | (空)   |          |       | (headers)
 2  | wk321  |          |       |              |              |              |              |              |              |              |              |              |         |      |           |
 3  | 156    | Ongoing  | WY    | Done         | Done         | Done         | Done         | UAT          | UAT          | UAT          | UAT          | UAT          | N2-001  |      | path1     | request title
 4  | wk322  |          |       |              |              |              |              |              |              |              |              |              |         |      |           |
 5  | 158    | Ongoing  | Stan  | Developing   | Developing   | Developing   | Developing   | Developing   | Developing   | Developing   | Developing   | Developing   | N3-102  |      | path1     | request title1
 6  | 162    | Ongoing  | Stan  | Done         | Done         | UAT done\n2/20 Check in | Done | UAT done\n2/10 Check in | Done | Done | Done | UAT  |         |      | path3     | request title2
 7  | wk323  |          |       |              |              |              |              |              |              |              |              |              |         |      |           |
 8  | 201    | Ongoing  | WY    | Unneeded     | Done         | Done         | Done         | UAT          | Done         | Done         | Done         | Unneeded     |         |      | path4     | request title3
 9  | 212    | Ongoing  | SH    | Done         | Done         | Done         | Done         | Done         | Done         | Done         | Done         | UAT          |         |      | path5     | request title4
10  | wk324  |          |       |              |              |              |              |              |              |              |              |              |         |      |           |
11  | 301    | Ongoing  | IC    |              | Done         |              |              | Done         |              |              |              |              |         |      |           | title5
12  | 302    | Ongoing  | Stan  |              | Done         |              |              | Done         |              |              |              |              |         |      |           | title6
13  | wk325  |          |       |              |              |              |              |              |              |              |              |              |         |      |           |
14  | 305    | Ongoing  | Ivy   |              | Done         |              |              | Done         |              |              |              |              |         |      |           | title7
```

## 使用者提到的統計數字

- 題目總數:接近 300 題
- 歷史:運作約 3 年
- 主要維護者:1 人(Meeting Owner)
- Meeting 頻率:每週一次
