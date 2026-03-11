# 生活品味人格探索測驗 - 現行規格

## 狀態

此文件描述目前已上線的 quiz 規格。

Source of truth:
- `data/quiz_bank_color_zh.json`
- `data/quiz_bank_color_en.json`
- `data/quiz_results.json`
- `data/quiz_results_en.json`
- `app/tools/quiz.py`
- `app/tools/quiz_results.py`

## 測驗概述

- 測驗名稱：生活品味人格探索
- 支援語言：`zh`、`en`
- 題庫總數：每種語言 12 題
- 實際作答數：每次隨機抽 4 題
- 結果類型：4 種人格結果

## 抽題規則

- 依 `selection_rules.total` 從題庫隨機抽題
- 目前 `total = 4`
- 題目資料不再使用 `category`

## 計分規則

- 每題各選項會對單一人格維度加分
- 作答完成後加總各人格維度分數
- 最高分即為最終結果
- 平手時依 `tie_breaker_priority` 決定結果

## 結果 ID

- `analyst`
- `diplomat`
- `guardian`
- `explorer`

## 結果內容

每個結果包含：
- `title`
- `color_name`
- `recommended_colors`
- `description`

## 備註

- 舊版 5 種測驗結果與 category-based 選題規則已移除
- 若 MongoDB 中的 default quiz bank / quiz results 與 JSON seed 不一致，啟動時會自動同步
