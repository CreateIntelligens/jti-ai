# 人格測驗重構摘要

## 狀態

此文件取代舊的色彩測驗實作計畫，反映目前 repo 已完成的實作狀態。

## 已完成項目

- 題庫已切換為 `12 題題庫 + 每次隨機抽 4 題`
- 結果已切換為 `4 種人格結果`
- `zh` / `en` 題庫與結果檔都已補齊
- default quiz bank 與 color results 支援啟動時 drift sync
- admin API 已拆到 `/api/jti-admin/*`
- 題目資料已移除 `category` 結構
- admin UI 已移除 category 篩選與編輯欄位
- questions CSV 匯入 / 匯出已移除 `category` 欄位

## 目前資料來源

- `data/quiz_bank_color_zh.json`
- `data/quiz_bank_color_en.json`
- `data/color_results.json`
- `data/color_results_en.json`

## 目前核心程式

- `app/tools/quiz.py`
- `app/tools/color_results.py`
- `app/services/jti/migrate_quiz_bank.py`
- `app/routers/jti/quiz_bank.py`
- `frontend/src/components/jti/JtiQuizTab.tsx`

## 舊設計已失效

以下假設已不再成立：

- `/api/mbti` 為主要 runtime route
- `frontend/src/pages/JtiTest.tsx` 為主要前端頁面
- 5 題固定流程
- 5 色系結果模型
- category-based 抽題規則

## 備註

若後續再調整題庫或結果內容，請直接以資料檔與 runtime 程式為準，不再回頭更新舊的 MBTI / 5 色系規劃稿。
