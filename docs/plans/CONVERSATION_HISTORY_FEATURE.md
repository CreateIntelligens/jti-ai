# 對話歷史查看功能

## 概述

用戶現在可以在 JTI 測驗頁面查看完整的對話歷史記錄，包括所有對話轉次、AI 回應、工具呼叫和 session 狀態。

## UI 組件

### 前端文件

**`frontend/src/components/ConversationHistoryModal.tsx`**
- 完整的對話歷史 Modal 組件
- 使用 Lucide React 圖標
- 響應式設計，支持搜索、篩選、導出功能

### 頁面集成

**`frontend/src/pages/JtiTest.tsx`**
- 添加了「History」按鈕到工具欄
- Modal 狀態管理
- 與現有 UI 風格一致

### 樣式

**`frontend/src/styles/JtiTest.css`**
- History 按鈕樣式（與 Restart、Language Toggle 一致）
- Hover 和 active 狀態
- 平滑過渡動畫

## 後端 API

### 新增端點

**`GET /api/jti/conversations`**

查詢參數：
- `session_id` (必需): Session ID
- `mode` (可選): 對話模式 (`jti` 或 `general`)

Response:
```json
{
  "session_id": "uuid",
  "mode": "jti",
  "conversations": [
    {
      "_id": "mongo_id",
      "session_id": "uuid",
      "mode": "jti",
      "timestamp": "2026-02-06T12:34:56.789Z",
      "user_message": "用戶訊息",
      "agent_response": "AI 回應",
      "tool_calls": [...],
      "session_snapshot": {...},
      "error": null
    }
  ],
  "total": 5
}
```

## 功能特性

### Modal 功能

✅ **對話展示**
- 按轉次號顯示（Turn 1, 2, 3...）
- 可展開/摺疊詳細內容
- 顯示時間戳

✅ **搜索和篩選**
- 即時搜索對話內容
- 支持搜索用戶訊息、AI 回應、工具名稱
- 篩選結果計數

✅ **詳細信息**
- 用戶訊息
- AI 回應（帶複製按鈕）
- 工具呼叫及執行時間
- Session 狀態快照（步驟、進度、分數）
- 錯誤信息（如果有）

✅ **數據導出**
- 導出為 JSON 格式
- 包含完整的對話記錄和 session ID
- 便於存檔和分析

## 使用流程

1. **打開 JTI 測驗頁面** → 進行對話和測驗
2. **點擊「History」按鈕** → 打開對話歷史 Modal
3. **查看或搜索** → 展開對話詳情或使用搜索功能
4. **導出（可選）** → 點擊 Export 按鈕下載 JSON

## 設計系統

### 顏色方案

- **背景**: `#0f172a` (Slate-900) → `#020208` (Slate-950)
- **邊框**: `#334155` (Slate-700)
- **主色**: `#0369a1` (Cyan-600)
- **強調**: `#06b6d4` (Cyan-400)
- **文本**: `#e2e8f0` (Slate-200)

### 字體

- **標題**: Poppins 600/700
- **正文**: Open Sans 400/500
- **代碼**: Monospace (工具呼叫展示)

### 動畫

- **過渡**: 200ms cubic-bezier
- **Hover 效果**: 1px 向上移動
- **加載動畫**: Spinner（標準 CSS）

## 國際化

Modal 自動使用應用的當前語言：

| 鍵 | 中文 | English |
|---|------|---------|
| `conversation_history` | 對話歷史 | Conversation History |
| `search_conversations` | 搜尋對話... | Search conversations... |
| `no_conversations` | 還沒有對話 | No conversations yet |
| `total_conversations` | 總對話數 | Total conversations |
| `close` | 關閉 | Close |
| `loading` | 載入中... | Loading conversations... |

## 技術實現細節

### 前端

```tsx
<ConversationHistoryModal
  isOpen={showHistoryModal}
  onClose={() => setShowHistoryModal(false)}
  sessionId={sessionId || ''}
  mode="jti"
/>
```

### 後端日誌記錄

所有 `conversation_logger.log_conversation()` 調用現在包括 `mode` 參數：

```python
conversation_logger.log_conversation(
    session_id=request.session_id,
    user_message=request.message,
    agent_response=response_message,
    tool_calls=tool_calls,
    session_state={...},
    mode="jti"  # 新增
)
```

## 性能考慮

- 對話記錄按需加載（不在初始化時加載）
- 搜索使用客戶端過濾（實時搜索）
- 導出為異步操作（不阻塞 UI）
- Modal 使用虛擬滾動可選（超過 100 條記錄時）

## 未來擴展

### 可能的增強功能

1. **時間線視圖** - 對話流程的視覺化表示
2. **統計信息** - 平均回應時間、工具使用統計
3. **對話重放** - 逐步重放對話過程
4. **共享功能** - 生成可共享的對話鏈接
5. **標記/筆記** - 用戶可在對話上添加批註
6. **性能優化** - 虛擬滾動、無限加載

## 故障排除

### Modal 不顯示對話

1. 檢查 `sessionId` 是否正確
2. 查看瀏覽器控制台是否有錯誤
3. 確保後端 `/api/jti/conversations` 端點可訪問
4. 驗證對話日誌是否已記錄（檢查 `logs/conversations/` 目錄）

### 搜索結果為空

- 搜索是實時的，檢查搜索詞是否正確
- 嘗試搜索對話中的部分詞彙

### 導出失敗

- 檢查瀏覽器的下載權限
- 確保有足夠的磁盤空間

## 相關文件

- `app/routers/jti.py` - 新增 `/api/jti/conversations` 端點
- `app/services/conversation_logger.py` - 更新以支持 `mode` 參數
- `frontend/src/types/index.ts` - 對話類型定義（如需要）

---

**建立日期**: 2026-02-06
**狀態**: ✅ 生產就緒
**設計系統**: Cyberpunk UI + Professional Palette
