#!/bin/bash
# 測驗 API Endpoints 測試
# 測試 /quiz/start, /quiz/pause, /quiz/resume API

set -e

API="${API_BASE_URL:-http://localhost:8913/api/jti}"

echo "=========================================="
echo "測驗 API Endpoints 測試"
echo "API: $API"
echo "=========================================="

# 1. 建立 Session
echo -e "\n=== 1. 建立 Session ==="
response=$(curl -s -X POST "$API/session/new" \
  -H "Content-Type: application/json" \
  -d '{"language":"zh"}')
SID=$(echo "$response" | jq -r '.session_id')
echo "✓ Session ID: $SID"

# 2. 使用 API 開始測驗
echo -e "\n=== 2. POST /api/jti/quiz/start ==="
curl -s -X POST "$API/quiz/start" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\"}" | jq -r '.message' | head -8
echo ""

# 3. 回答第 1 題
echo -e "\n=== 3. 回答第 1 題 (A) ==="
curl -s -X POST "$API/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"message\":\"A\",\"language\":\"zh\"}" | jq -r '.message' | head -3
echo ""

# 4. 回答第 2 題
echo -e "\n=== 4. 回答第 2 題 (B) ==="
curl -s -X POST "$API/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"message\":\"B\",\"language\":\"zh\"}" | jq -r '.message' | head -3
echo ""

# 5. 使用 API 暫停測驗
echo -e "\n=== 5. POST /api/jti/quiz/pause ==="
response=$(curl -s -X POST "$API/quiz/pause" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\"}")
echo "$response" | jq -r '.message'
step=$(echo "$response" | jq -r '.session.step')
paused=$(echo "$response" | jq -r '.session.metadata.paused_quiz')
answers=$(echo "$response" | jq -r '.session.answers | length')
echo "✓ Step: $step (應為 WELCOME)"
echo "✓ Paused: $paused (應為 true)"
echo "✓ 已回答: $answers 題"
echo ""

# 6. 測試一般問答
echo -e "\n=== 6. 一般問答（確認已離開測驗）==="
curl -s -X POST "$API/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\",\"message\":\"你好\",\"language\":\"zh\"}" | jq -r '.message' | head -2
echo ""

# 7. 使用 API 恢復測驗
echo -e "\n=== 7. POST /api/jti/quiz/resume ==="
response=$(curl -s -X POST "$API/quiz/resume" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SID\"}")
echo "$response" | jq -r '.message' | head -6
step=$(echo "$response" | jq -r '.session.step')
paused=$(echo "$response" | jq -r '.session.metadata.paused_quiz')
current_q=$(echo "$response" | jq -r '.session.current_q_index')
echo "✓ Step: $step (應為 QUIZ)"
echo "✓ Paused: $paused (應為 false)"
echo "✓ 當前題號: $current_q"
echo ""

# 8. 完成剩餘題目
echo -e "\n=== 8. 完成剩餘題目 ==="
for i in {1..3}; do
  echo "回答題目 $i..."
  curl -s -X POST "$API/chat" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\":\"$SID\",\"message\":\"A\",\"language\":\"zh\"}" > /tmp/answer_$i.json
  step=$(cat /tmp/answer_$i.json | jq -r '.session.step')
  if [ "$step" == "DONE" ]; then
    echo "✓ 測驗完成！"
    cat /tmp/answer_$i.json | jq -r '.message' | head -5
    break
  fi
done
echo ""

echo "=========================================="
echo "✅ API Endpoints 測試完成"
echo "=========================================="
