# 色彩測驗整合測試

此目錄包含色彩測驗功能的整合測試腳本。

## 測試腳本

### 1. `test_quiz_flow.sh`
**完整流程測試**，測試透過對話介面的測驗流程：

- ✅ 透過對話開始測驗
- ✅ 明確回答選項 (A/B)
- ✅ 帶解釋的回答（不應被誤判為中斷）
- ✅ 數字回答 (1/2)
- ✅ 透過對話中斷測驗
- ✅ 一般問答（確認已離開測驗）
- ✅ 透過對話繼續測驗
- ✅ 完成測驗
- ✅ 邊界案例：`pause` 不應被誤判為選項 A

**執行方式：**
```bash
cd tests/integration
chmod +x test_quiz_flow.sh
./test_quiz_flow.sh
```

### 2. `test_quiz_api.sh`
**API Endpoints 測試**，測試專用的測驗控制 API：

- ✅ `POST /api/jti/quiz/start` - 開始測驗
- ✅ `POST /api/jti/quiz/pause` - 暫停測驗
- ✅ `POST /api/jti/quiz/resume` - 恢復測驗
- ✅ 完整流程：開始 → 回答 → 暫停 → 一般問答 → 恢復 → 完成

**執行方式：**
```bash
cd tests/integration
chmod +x test_quiz_api.sh
./test_quiz_api.sh
```

## 環境變數

可以透過環境變數指定 API 位址（預設為 `http://10.9.0.32:8913/api/jti`）：

```bash
API_BASE_URL=http://localhost:8913/api/jti ./test_quiz_flow.sh
```

## 依賴

- `curl` - HTTP 請求工具
- `jq` - JSON 處理工具

## 測試涵蓋範圍

### 功能測試
- [x] 開始測驗（對話 & API）
- [x] 回答問題（A/B、數字、帶解釋）
- [x] 暫停測驗（對話 & API）
- [x] 恢復測驗（對話 & API）
- [x] 完成測驗並獲得結果

### 意圖判斷測試
- [x] 明確選項（A、B）
- [x] 數字選項（1、2）
- [x] 帶解釋的回答（如「我不想太華麗，所以選B」）
- [x] 中斷意圖（「中斷」、「pause」）
- [x] 無法判斷的訊息

### 邊界案例
- [x] "pause" 不應被誤判為選項 A
- [x] 測驗進度保留（暫停後恢復）
- [x] 測驗中可以切換到一般問答

## 測試結果範例

```
=== 測試 1: 透過對話開始測驗 ===
想來做個生活品味色彩探索測驗嗎？ 簡單五個測驗，尋找你的命定手機殼...
第1題：你最討厭的事情是？
A. 冷漠沒溫度
B. 虛偽不真誠

=== 測試 5: 透過對話中斷測驗 ===
好呀，那我先幫你暫停測驗，我們回到一般問答。之後想接著做，請輸入「繼續測驗」。
✓ Step: WELCOME (應為 WELCOME)
✓ Paused: true (應為 true)
✓ 已回答: 3 題

=== 測試 7: 透過對話繼續測驗 ===
好呀，我們接著做第4題。
第4題：選一種交通工具代表你？
✓ Step: QUIZ (應為 QUIZ)
✓ Paused: false (應為 false)

✅ 測試完成
```

## 相關檔案

- `app/routers/jti.py` - API 路由實作
- `app/services/session_manager.py` - Session 管理（記憶體版）
- `app/services/mongo_session_manager.py` - Session 管理（MongoDB 版）
- `app/tools/quiz.py` - 測驗邏輯
- `data/quiz_bank_color_zh.json` - 測驗題庫
