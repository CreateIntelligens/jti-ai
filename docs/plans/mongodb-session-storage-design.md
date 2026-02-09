# MongoDB Session Storage Design

## 概述

當前系統使用記憶體（in-memory dictionary）存儲 session，導致以下問題：
1. **數據持久化**: 服務重啟後 session 丟失
2. **可擴展性**: 無法在多進程/多服務器環境中共享 session
3. **歷史紀錄**: 無法查詢過去的對話和測驗記錄

本設計目標是遷移到 MongoDB，實現持久化、可查詢和可擴展的 session 儲存。

## 核心需求

### 1. Session 儲存
- 持久化 Quiz Session（色彩測驗會話）
- 分離存儲：JTI quiz mode vs 一般對話模式
- 支持 session 過期和清理

### 2. Conversation 日誌
- 在 MongoDB 中持久化對話紀錄，而非僅存檔案日誌
- 支持按 session_id 查詢完整對話歷史
- 記錄時間戳、用戶訊息、AI 回應、工具呼叫

### 3. 查詢能力
- 按 session_id 查詢
- 按模式（mode）查詢：`jti` vs `general`
- 按時間範圍查詢
- 按語言查詢

## MongoDB 集合設計

### Collection 1: `sessions`
存儲所有活躍和已完成的 session

```json
{
  "_id": ObjectId(),
  "session_id": "uuid-string",
  "mode": "jti|general",           // 區分測驗模式和一般對話
  "language": "zh|en",
  "created_at": ISODate(),
  "updated_at": ISODate(),
  "expires_at": ISODate(),          // TTL index 用於自動清理

  // Session 狀態
  "step": "initial|quiz|scoring|done",
  "current_q_index": Number,
  "answers": {                      // {"question_id": "option_id"}
    "q1": "a",
    "q2": "b"
  },
  "current_question": Object,
  "selected_questions": [Object],
  "chat_history": [
    {
      "role": "user|assistant",
      "content": "string"
    }
  ],

  // 色彩測驗結果
  "color_result_id": String,
  "color_scores": {                 // {"dimension": score}
    "metal": 2,
    "cool": 2,
    "warm": 1
  },
  "color_result": Object,

  // 中繼資料
  "metadata": {
    "ip_address": "string",         // 用於分析用途
    "user_agent": "string"
  }
}
```

### Collection 2: `conversations`
存儲完整的對話紀錄（包含工具呼叫、結果等）

```json
{
  "_id": ObjectId(),
  "session_id": "uuid-string",      // 外鍵參考 sessions.session_id
  "mode": "jti|general",
  "turn_number": Number,             // 對話輪次
  "timestamp": ISODate(),

  "user_message": String,
  "agent_response": String,

  "tool_calls": [
    {
      "tool_name": "string",
      "arguments": Object,
      "result": Object,
      "execution_time_ms": Number
    }
  ],

  // Session 快照（便於分析）
  "session_snapshot": {
    "step": String,
    "quiz_progress": String,        // "2/5 已完成"
    "color_scores": Object
  },

  "error": String  // 如果發生錯誤
}
```

### Collection 3: `quizzes` (可選 - 歷史測驗記錄)
若要單獨追蹤所有完成的測驗

```json
{
  "_id": ObjectId(),
  "session_id": "uuid-string",
  "language": "zh|en",
  "started_at": ISODate(),
  "completed_at": ISODate(),
  "duration_seconds": Number,

  "questions": [
    {
      "question_id": String,
      "selected_option": String,
      "is_correct": Boolean
    }
  ],

  "color_result": {
    "color_id": String,
    "color_scores": Object,
    "color_result": Object
  },

  "metadata": {
    "version": String               // 題庫版本
  }
}
```

## 索引策略

```javascript
// sessions collection
db.sessions.createIndex({ "session_id": 1 }, { unique: true })
db.sessions.createIndex({ "expires_at": 1 }, { expireAfterSeconds: 0 })  // TTL 索引
db.sessions.createIndex({ "mode": 1, "created_at": -1 })
db.sessions.createIndex({ "language": 1 })

// conversations collection
db.conversations.createIndex({ "session_id": 1, "turn_number": 1 })
db.conversations.createIndex({ "mode": 1, "timestamp": -1 })
db.conversations.createIndex({ "timestamp": 1 })

// quizzes collection
db.quizzes.createIndex({ "session_id": 1 })
db.quizzes.createIndex({ "completed_at": -1 })
db.quizzes.createIndex({ "language": 1, "completed_at": -1 })
```

## 數據流

### Session 生命週期

1. **建立** (app.routers.jti.start_session)
   - 在 MongoDB sessions 中插入新 document
   - 設置 expires_at = 現在 + 30 分鐘
   - 返回 session_id

2. **更新** (任何狀態改變)
   - 按 session_id 更新 document
   - 更新 updated_at 和 expires_at（延長過期時間）

3. **查詢** (get_session)
   - 按 session_id 查詢
   - 檢查是否已過期（updated_at + timeout）
   - 若已過期，刪除並返回 None

4. **清理** (定期任務或按需)
   - TTL 索引自動清理過期 session
   - 可選：定期查詢並刪除 expires_at < now 的記錄

### 對話紀錄流

1. **記錄** (每次用戶互動)
   - 在 conversations 中插入新 document
   - session_id, mode, turn_number 必填
   - 包含完整的對話內容和工具呼叫結果

2. **查詢** (查看歷史)
   - 按 session_id 查詢所有對話記錄
   - 按 turn_number 排序
   - 可選篩選：時間範圍、模式等

3. **分析** (可選 - 統計分析)
   - 按 mode 分組統計
   - 計算平均對話輪次、常用工具等

## Migration 策略

### Phase 1: 並行存儲
1. 保持原有的 SessionManager（記憶體版）
2. 創建 MongoSessionManager（MongoDB 版）
3. 在同一個 endpoint 中同時使用兩者，確保兼容性

### Phase 2: 逐步遷移
1. 所有新 session 優先使用 MongoDB
2. 舊記憶體 session 仍支持查詢（fallback）
3. 設置環境變數 `USE_MONGO_SESSION=true/false`

### Phase 3: 完全切換
1. 移除記憶體 SessionManager
2. 所有操作使用 MongoSessionManager
3. 關閉 fallback 邏輯

## 實現清單

- [ ] MongoSessionManager 類
  - [ ] create_session()
  - [ ] get_session()
  - [ ] update_session()
  - [ ] delete_session()
  - [ ] get_all_sessions()
  - [ ] clear_expired_sessions()
  - [ ] 所有狀態轉換方法 (start_quiz, submit_answer, complete_scoring 等)

- [ ] MongoConversationLogger 類
  - [ ] log_conversation()
  - [ ] get_session_logs()
  - [ ] list_sessions()
  - [ ] 新增查詢方法 (query_by_mode, query_by_date_range 等)

- [ ] 配置和初始化
  - [ ] MongoDB 連接字符串（使用 .env）
  - [ ] 集合和索引初始化
  - [ ] 連接池管理

- [ ] 單元測試
  - [ ] CRUD 操作測試
  - [ ] 過期清理測試
  - [ ] 並發操作測試

- [ ] 文檔
  - [ ] API 文檔（新查詢方法）
  - [ ] 遷移指南
  - [ ] 故障排除指南

## 技術棧

- **驅動程式**: `pymongo` 或 `motor`（非同步）
- **MongoDB**: 已有 MongoDB Atlas 實例（見 .env）
- **版本**: MongoDB 4.4+

## 優勢與考量

### 優勢
✅ 數據持久化 - session 和對話歷史不會丟失
✅ 可查詢 - 支持複雜的查詢和分析
✅ 可擴展 - 支持分散式部署
✅ 完整歷史 - 保存所有對話用於分析和調試

### 考量
⚠️ 網絡延遲 - MongoDB 查詢比記憶體慢
⚠️ 成本 - MongoDB Atlas 需要付費
⚠️ 數據安全 - 需要配置訪問控制

## 性能最佳化

1. **緩存**: 在應用層使用記憶體快取（LRU cache）
2. **批量操作**: 合併多個 update 操作
3. **異步記錄**: 使用非同步任務記錄對話（不阻塞主線程）
4. **索引優化**: 定期檢查和優化索引

## 監控和告警

- 監控 MongoDB 連接狀態
- 追蹤 session 創建/銷毀速率
- 監控對話記錄大小和增長速率
- 設置告警：連接失敗、查詢超時等
