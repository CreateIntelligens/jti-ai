# MongoDB Session Storage 遷移指南

## 概述

本指南說明如何從記憶體 SessionManager 遷移到 MongoDB SessionManager。

## 前置條件

1. **MongoDB 實例**
   - 已有 MongoDB Atlas 帳戶（見 .env 中的 MONGODB_URI）
   - 或本機 MongoDB（預設 `mongodb://localhost:27017/jti_app`）

2. **Python 依賴**
   ```bash
   pip install pymongo
   ```

3. **環境變數配置**
   - `MONGODB_URI`: MongoDB 連接字符串（已在 .env 中）
   - `USE_MONGO_SESSION`: 啟用 MongoDB SessionManager（可選，預設 false）
   - `USE_MONGO_LOGS`: 啟用 MongoDB ConversationLogger（可選，預設 false）

## Phase 1: 並行存儲（推薦）

目標：測試 MongoDB 版本，同時保留記憶體版本作為備份

### 步驟 1: 更新 requirements.txt

```bash
echo "pymongo>=4.0" >> requirements.txt
pip install -r requirements.txt
```

### 步驟 2: 設定環境變數

編輯 `.env` 文件，添加：

```env
# MongoDB 已存在
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?appName=app

# 啟用 MongoDB（可選）
USE_MONGO_SESSION=false
USE_MONGO_LOGS=false
```

### 步驟 3: 更新 main.py（使用工廠模式）

```python
# 舊方式（記憶體）
from app.services.session_manager import session_manager
from app.services.conversation_logger import conversation_logger

# 新方式（使用工廠）
from app.services.session_manager_factory import get_session_manager, get_conversation_logger

session_manager = get_session_manager()
conversation_logger = get_conversation_logger()
```

### 步驟 4: 測試連接

```bash
python -c "from app.services.mongo_client import get_mongo_client; get_mongo_client().health_check()"
```

預期輸出：
```
Connected to MongoDB successfully!
```

### 步驟 5: 驗證集合和索引

```bash
mongo mongodb+srv://user:pass@cluster.mongodb.net/jti_app

# 在 MongoDB shell 中執行
db.sessions.getIndexes()
db.conversations.getIndexes()
db.quizzes.getIndexes()
```

## Phase 2: 逐步遷移

目標：切換部分用戶到 MongoDB，監控性能

### 步驟 1: 啟用 MongoDB SessionManager

編輯 `.env`：
```env
USE_MONGO_SESSION=true
USE_MONGO_LOGS=false  # 先只遷移 session，日誌保留檔案
```

### 步驟 2: 監控日誌

```bash
# 查看應用日誌
docker logs -f <container_id>

# 應該看到：
# [INFO] Using MongoDB SessionManager
```

### 步驟 3: 驗證功能

運行測試：
```bash
python -m pytest tests/test_mongo_session_manager.py -v
```

### 步驟 4: 進行負載測試

```bash
# 使用 locust 或 ab 進行壓力測試
ab -n 1000 -c 10 http://localhost:8913/api/jti/start_session
```

### 步驟 5: 監控 MongoDB 性能

```javascript
// MongoDB Atlas Dashboard 中查看
- Metrics → Operations
- Metrics → Read/Write Latency
- Alerts → 設置告警
```

### 步驟 6: 逐步啟用日誌遷移

一旦 session 穩定，啟用對話日誌：

```env
USE_MONGO_SESSION=true
USE_MONGO_LOGS=true
```

## Phase 3: 完全切換

目標：完全移除記憶體版本

### 步驟 1: 清理舊代碼

移除不再使用的文件（可選備份）：

```bash
# 保留記憶體版本作為備份
mv app/services/session_manager.py app/services/session_manager.memory.bak
mv app/services/conversation_logger.py app/services/conversation_logger.file.bak
```

### 步驟 2: 簡化工廠代碼

由於不再需要 fallback，可以直接返回 MongoDB 實現。

### 步驟 3: 更新文檔

- 更新 README.md：說明 MongoDB 是必需的
- 更新 deployment 指南

## 故障排除

### 連接失敗

**錯誤**: `Failed to connect to MongoDB`

**解決**:
1. 檢查 MONGODB_URI 是否正確
2. 檢查網絡連接
3. 檢查防火牆白名單（MongoDB Atlas）
4. 測試連接字符串：
   ```bash
   mongosh "mongodb+srv://user:pass@cluster.mongodb.net/test"
   ```

### 索引衝突

**錯誤**: `Index with name 'session_id_1' already exists with a different name`

**解決**:
1. 刪除現有索引：
   ```javascript
   db.sessions.dropIndex("session_id_1")
   ```
2. 重新運行應用初始化

### 性能變慢

**症狀**: MongoDB 操作比記憶體慢

**解決**:
1. 檢查索引是否建立：
   ```javascript
   db.sessions.explain("executionStats").find({session_id: "test"})
   ```
2. 檢查網絡延遲
3. 考慮使用 Redis 緩存層
4. 啟用連接池優化

### 數據不一致

**症狀**: 舊記憶體 session 和新 MongoDB session 不同步

**解決**:
1. 實現 migration script 從記憶體轉移到 MongoDB
   ```python
   from app.services.session_manager import session_manager as memory_mgr
   from app.services.mongo_session_manager import mongo_session_manager

   for session in memory_mgr.get_all_sessions():
       mongo_session_manager.update_session(session)
   ```
2. 確認所有新 session 使用 MongoDB

## 回滾計畫

如果需要回滾到記憶體版本：

### 步驟 1: 更新環境變數

```env
USE_MONGO_SESSION=false
USE_MONGO_LOGS=false
```

### 步驟 2: 重啟應用

```bash
docker-compose restart backend
```

### 步驟 3: 驗證（可選）

```bash
python -c "from app.services.session_manager_factory import get_session_manager; print(get_session_manager())"
```

應該輸出：`<SessionManager object>` (記憶體版本)

## 性能基準

### 記憶體版本

- 建立 session: < 1ms
- 查詢 session: < 1ms
- 更新 session: < 1ms

### MongoDB 版本

- 建立 session: 10-50ms（取決於網絡）
- 查詢 session: 5-20ms
- 更新 session: 10-30ms

### 優化建議

1. **使用緩存層**
   - Redis LRU cache（活躍 session）
   - 減少 MongoDB 查詢

2. **批量操作**
   - 合併多個更新到一個請求

3. **異步記錄**
   - 使用後台任務記錄日誌（不阻塞主線程）

4. **連接池**
   ```python
   MongoClient(..., maxPoolSize=50, minPoolSize=10)
   ```

## 監控和告警

### 推薦監控指標

1. **連接狀態**
   - MongoDB health_check 成功率

2. **性能**
   - Session 操作延遲（p50, p95, p99）
   - 數據庫查詢時間

3. **容量**
   - 活躍 session 數量
   - MongoDB 存儲大小

4. **錯誤率**
   - 連接失敗
   - 操作超時

### 設置告警

```python
# 連接失敗超過 3 次
if failed_connections > 3:
    send_alert("MongoDB connection failures detected")

# 操作延遲過高
if operation_latency_p99 > 500ms:
    send_alert("High MongoDB latency")
```

## 常見問題

### Q: 能否同時使用記憶體和 MongoDB？

A: 可以。使用工廠模式，根據環境變數選擇。但建議不要混用，避免數據不一致。

### Q: 如何遷移現有 session 到 MongoDB？

A: 見「故障排除」中的「數據不一致」部分。

### Q: MongoDB Atlas 費用如何？

A: 共享集群免費，專用集群從 $57/月起。詳見 [MongoDB 定價](https://www.mongodb.com/pricing)。

### Q: 如何確保數據安全？

A:
- 啟用 IP whitelist（MongoDB Atlas）
- 使用強密碼
- 定期備份
- 啟用加密（傳輸中和靜止時）

## 支援和反饋

如遇問題，請檢查：
1. 日誌文件
2. MongoDB 連接字符串
3. 防火牆設置
4. 索引和統計信息

更多幫助見 `docs/mongodb-session-storage-design.md`。
