#!/bin/bash
# 色彩測驗完整流程測試
# 測試開始、暫停、恢復、完成等各種情境

set -e

API="${API_BASE_URL:-http://localhost:8913/api/jti}"

echo "=========================================="
echo "色彩測驗完整流程測試"
echo "API: $API"
echo "=========================================="

# 建立 Session
echo -e "\n=== 建立 Session ==="
response=$(curl -s -X POST "$API/session/new" \
  -H "Content-Type: application/json" \
  -d '{"language":"zh"}')
SID=$(echo "$response" | jq -r '.session_id')
echo "✓ Session ID: $SID"

# 測試 1: 透過對話開始測驗
echo -e "\n=== 測試 1: 透過對話開始測驗 ==="
curl -s -X POST "$API/chat" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"message\":\"開始測驗\",\"language\":\"zh\"}" \
  -o /tmp/r1.json
echo "回應:"
cat /tmp/r1.json | jq -r '.message' | head -8
echo ""

# 測試 2: 明確回答選項
echo -e "\n=== 測試 2: 明確回答 A ==="
curl -s -X POST "$API/chat" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"message\":\"A\",\"language\":\"zh\"}" \
  -o /tmp/r2.json
cat /tmp/r2.json | jq -r '.message' | head -3
echo ""

# 測試 3: 帶解釋的回答（不應被誤判為中斷）
echo -e "\n=== 測試 3: 帶解釋回答（不應被誤判為中斷）==="
curl -s -X POST "$API/chat" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"message\":\"我不想太華麗，所以選B\",\"language\":\"zh\"}" \
  -o /tmp/r3.json
cat /tmp/r3.json | jq -r '.message' | head -3
echo ""

# 測試 4: 數字回答
echo -e "\n=== 測試 4: 數字回答 (1) ==="
curl -s -X POST "$API/chat" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"message\":\"1\",\"language\":\"zh\"}" \
  -o /tmp/r4.json
cat /tmp/r4.json | jq -r '.message' | head -3
echo ""

# 測試 5: 中斷測驗
echo -e "\n=== 測試 5: 透過對話中斷測驗 ==="
curl -s -X POST "$API/chat" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"message\":\"中斷\",\"language\":\"zh\"}" \
  -o /tmp/r5.json
cat /tmp/r5.json | jq -r '.message'
step=$(cat /tmp/r5.json | jq -r '.session.step')
paused=$(cat /tmp/r5.json | jq -r '.session.metadata.paused_quiz')
answers=$(cat /tmp/r5.json | jq -r '.session.answers | length')
echo "✓ Step: $step (應為 WELCOME)"
echo "✓ Paused: $paused (應為 true)"
echo "✓ 已回答: $answers 題"
echo ""

# 測試 6: 一般問答
echo -e "\n=== 測試 6: 一般問答（確認已離開測驗）==="
curl -s -X POST "$API/chat" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"message\":\"Ploom X 的電池容量是多少？\",\"language\":\"zh\"}" \
  -o /tmp/r6.json
cat /tmp/r6.json | jq -r '.message' | head -2
echo ""

# 測試 7: 透過對話繼續測驗
echo -e "\n=== 測試 7: 透過對話繼續測驗 ==="
curl -s -X POST "$API/chat" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"message\":\"繼續測驗\",\"language\":\"zh\"}" \
  -o /tmp/r7.json
cat /tmp/r7.json | jq -r '.message' | head -6
step=$(cat /tmp/r7.json | jq -r '.session.step')
paused=$(cat /tmp/r7.json | jq -r '.session.metadata.paused_quiz')
echo "✓ Step: $step (應為 QUIZ)"
echo "✓ Paused: $paused (應為 false)"
echo ""

# 測試 8: 完成最後一題
echo -e "\n=== 測試 8: 完成最後一題 ==="
curl -s -X POST "$API/chat" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"message\":\"B\",\"language\":\"zh\"}" \
  -o /tmp/r8.json
cat /tmp/r8.json | jq -r '.message' | head -3
echo ""

# 測試 9: 邊界案例 - "pause" 不應被誤判為選項 A
echo -e "\n=== 測試 9: 邊界案例 - 'pause' 不應被誤判為選項 A ==="
response=$(curl -s -X POST "$API/session/new" -H "Content-Type: application/json" -d '{"language":"zh"}')
SID2=$(echo "$response" | jq -r '.session_id')
echo "新 Session ID: $SID2"

curl -s -X POST "$API/chat" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID2\",\"message\":\"開始測驗\",\"language\":\"zh\"}" > /tmp/r9a.json

curl -s -X POST "$API/chat" -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID2\",\"message\":\"pause\",\"language\":\"zh\"}" \
  -o /tmp/r9b.json

cat /tmp/r9b.json | jq -r '.message'
step=$(cat /tmp/r9b.json | jq -r '.session.step')
paused=$(cat /tmp/r9b.json | jq -r '.session.metadata.paused_quiz')
echo "✓ Step: $step (應為 WELCOME，表示暫停)"
echo "✓ Paused: $paused (應為 true)"
echo ""

echo "=========================================="
echo "✅ 測試完成"
echo "=========================================="
