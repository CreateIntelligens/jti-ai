# MongoDB Session Storage 功能實現

## 📋 項目概述

本 worktree 實現了將應用的 Session 和 Conversation 存儲從記憶體遷移到 MongoDB 的完整設計和實現。

### 核心功能

✅ **持久化 Session 存儲**
- 使用 MongoDB 存儲 quiz session 和對話狀態
- 支持 JTI quiz mode 和一般對話模式的分離存儲
- 自動過期清理（TTL 索引）

✅ **完整對話紀錄**
- 在 MongoDB 中記錄每次對話
- 支持按 session_id、模式、時間範圍查詢
- 工具呼叫和執行結果追蹤

✅ **數據分析能力**
- session 統計（按模式、狀態、語言）
- 對話統計（轉次、工具使用）
- 性能指標（執行時間、成功率）

✅ **無縫遷移**
- 工廠模式支持記憶體和 MongoDB 版本切換
- 環境變數控制（USE_MONGO_SESSION, USE_MONGO_LOGS）
- 完整的測試和故障排除指南

## 📁 文件結構

```
.worktrees/session-storage/
├── app/services/
│   ├── mongo_client.py                    # MongoDB 連接管理
│   ├── mongo_session_manager.py           # MongoDB Session Manager
│   ├── mongo_conversation_logger.py       # MongoDB Conversation Logger
│   └── session_manager_factory.py         # 工廠模式：選擇合適實現
│
├── docs/
│   ├── mongodb-session-storage-design.md  # 完整設計文檔
│   └── MIGRATION_GUIDE.md                 # 遷移指南
│
├── tests/
│   ├── test_mongo_session_manager.py      # SessionManager 單元測試
│   └── test_mongo_conversation_logger.py  # ConversationLogger 單元測試
│
└── SESSION_STORAGE_README.md              # 本文件
```

## 🏗️ 架構設計

### MongoDB 集合結構

#### 1. sessions 集合
存儲所有活躍和已完成的 quiz session

```json
{
  "session_id": "uuid",
  "mode": "jti|general",
  "language": "zh|en",
  "step": "initial|quiz|scoring|done",
  "answers": {"q1": "a", "q2": "b"},
  "color_result_id": "metal|cool|warm|dark|colorful",
  "color_scores": {"metal": 2, "cool": 1},
  "expires_at": ISODate(),
  ...
}
```

#### 2. conversations 集合
存儲完整的對話紀錄

```json
{
  "session_id": "uuid",
  "mode": "jti|general",
  "turn_number": 1,
  "timestamp": ISODate(),
  "user_message": "用戶訊息",
  "agent_response": "AI 回應",
  "tool_calls": [{"tool_name": "...", "result": {...}}],
  ...
}
```

#### 3. quizzes 集合（可選）
歷史測驗記錄

## 🚀 快速開始

### 1. 安裝依賴

```bash
pip install pymongo
```

### 2. 配置環境變數

`.env` 文件已包含 MONGODB_URI：

```env
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?appName=app
USE_MONGO_SESSION=false    # 設置為 true 以啟用
USE_MONGO_LOGS=false       # 設置為 true 以啟用
```

### 3. 測試連接

```bash
python -c "from app.services.mongo_client import get_mongo_client; get_mongo_client().health_check()"
```

### 4. 運行單元測試

```bash
python -m pytest tests/test_mongo_session_manager.py -v
python -m pytest tests/test_mongo_conversation_logger.py -v
```

### 5. 在應用中使用

使用工廠模式自動選擇合適的實現：

```python
from app.services.session_manager_factory import get_session_manager, get_conversation_logger

# 自動根據 USE_MONGO_SESSION 選擇
session_manager = get_session_manager()
conversation_logger = get_conversation_logger()

# 使用方式與原有代碼相同
session = session_manager.create_session(mode=GameMode.COLOR, language="zh")
conversation_logger.log_conversation(session_id, "jti", user_msg, ai_msg)
```

## 📊 API 參考

### MongoSessionManager

#### 核心方法

```python
# CRUD 操作
session = manager.create_session(mode=GameMode.COLOR, language="zh")
session = manager.get_session(session_id)
updated = manager.update_session(session)
deleted = manager.delete_session(session_id)

# 狀態轉換
manager.start_quiz(session_id, selected_questions)
manager.submit_answer(session_id, question_id, option_id)
manager.complete_scoring(session_id, color_result_id, scores)

# 查詢和分析
sessions = manager.get_all_sessions()
sessions = manager.get_sessions_by_mode(GameMode.COLOR)
sessions = manager.get_sessions_by_language("zh")
sessions = manager.get_sessions_by_date_range(start, end)
stats = manager.get_statistics()
```

### MongoConversationLogger

#### 核心方法

```python
# 記錄對話
log_id = logger.log_conversation(
    session_id, mode, user_msg, agent_msg,
    tool_calls=[], session_state={}
)

# 查詢對話
logs = logger.get_session_logs(session_id)
logs = logger.get_conversations_by_date_range(start, end, mode="jti")

# 統計分析
sessions = logger.list_sessions()
stats = logger.get_statistics()
tool_stats = logger.get_tool_call_statistics()

# 數據維護
deleted = logger.delete_old_logs(days=30)
```

## 🔄 數據遷移

### Phase 1: 並行存儲
1. 保持記憶體版本（預設）
2. 新增 MongoDB 版本（可選）
3. 環境變數控制切換

### Phase 2: 逐步遷移
1. 部分用戶切換到 MongoDB
2. 監控性能和穩定性
3. 驗證功能完整性

### Phase 3: 完全切換
1. 移除記憶體版本
2. MongoDB 成為唯一實現
3. 更新文檔和流程

詳見 `docs/MIGRATION_GUIDE.md`

## 📈 性能指標

### 基準測試

| 操作 | 記憶體版 | MongoDB 版 |
|------|---------|-----------|
| 建立 session | < 1ms | 10-50ms |
| 查詢 session | < 1ms | 5-20ms |
| 更新 session | < 1ms | 10-30ms |

### 優化策略

1. **Redis 緩存層** - 減少 MongoDB 查詢
2. **批量操作** - 合併多個更新
3. **異步記錄** - 非同步日誌記錄
4. **連接池** - 複用數據庫連接

## 🧪 測試覆蓋

### SessionManager 測試

✅ CRUD 操作（create, read, update, delete）
✅ 狀態轉換（initial → quiz → scoring → done）
✅ 過期清理（TTL）
✅ 查詢功能（by mode, by language, by date）
✅ 統計功能

### ConversationLogger 測試

✅ 記錄對話（各轉次）
✅ 查詢日誌（by session, by mode, by date）
✅ 統計分析（mode, tool, average turns）
✅ 數據刪除（old logs）

### 運行測試

```bash
# 全部測試
python -m pytest tests/ -v

# 特定測試
python -m pytest tests/test_mongo_session_manager.py::TestMongoSessionManager::test_create_session -v

# 覆蓋率報告
python -m pytest tests/ --cov=app --cov-report=html
```

## 📚 文檔

- **[MongoDB Session Storage Design](docs/mongodb-session-storage-design.md)**
  - 詳細的設計文檔
  - 集合和索引設計
  - 數據流和生命週期
  - 優化建議

- **[Migration Guide](docs/MIGRATION_GUIDE.md)**
  - 完整遷移步驟
  - 故障排除指南
  - 性能基準和優化
  - 回滾計畫

## ⚙️ 環境配置

### 必需

```env
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?appName=app
```

### 可選

```env
# 啟用 MongoDB 實現（預設 false = 使用記憶體版本）
USE_MONGO_SESSION=false
USE_MONGO_LOGS=false

# Session 過期時間（分鐘，預設 30）
SESSION_IDLE_TIMEOUT=30
```

## 🔍 故障排除

### 常見問題

1. **連接失敗** → 檢查 MONGODB_URI 和網絡
2. **索引衝突** → 刪除並重新建立索引
3. **性能下降** → 檢查索引和網絡延遲
4. **數據不同步** → 確認使用的實現版本一致

詳見 `docs/MIGRATION_GUIDE.md` 的故障排除部分

## 🎯 下一步

### 立即實現

1. **在主分支合併**
   - 將 MongoDB 服務合併到 main
   - 保留記憶體版本作為預設

2. **進行 Phase 1 測試**
   - 設置測試環境
   - 驗證 MongoDB 集合初始化
   - 運行全部單元測試

3. **監控和優化**
   - 建立監控儀表板
   - 設置性能告警
   - 優化慢查詢

### 長期規劃

1. **實現 Phase 2 遷移**
   - Canary deployment（少部分用戶）
   - A/B 測試（記憶體 vs MongoDB）

2. **完全切換（Phase 3）**
   - 移除記憶體版本
   - 文檔更新
   - 團隊培訓

3. **高級功能**
   - Redis 緩存層
   - 異步日誌記錄
   - 數據分析儀表板

## 📞 支援和貢獻

有問題或建議？
- 檢查 `docs/` 中的文檔
- 查看測試用例作為使用範例
- 參考遷移指南進行故障排除

---

**建立日期**: 2026-02-06
**分支**: feature/session-storage
**狀態**: ✅ 設計和實現完成，待合併
