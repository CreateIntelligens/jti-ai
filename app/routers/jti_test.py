"""
JTI 智慧助手測試介面
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/jti", tags=["JTI Test"])


@router.get("", response_class=HTMLResponse)
async def jti_test_page():
    """JTI 智慧助手測試頁面"""
    html_content = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JTI 智慧助手</title>
    <style>
        :root {
            --primary: #667eea;
            --primary-dark: #5568d3;
            --secondary: #764ba2;
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-tertiary: #334155;
            --text-primary: #f1f5f9;
            --text-secondary: #cbd5e1;
            --text-muted: #94a3b8;
            --border: #475569;
            --success: #10b981;
            --error: #ef4444;
            --warning: #f59e0b;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            padding: 1rem 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .header h1 {
            font-size: 1.25rem;
            font-weight: 600;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .status-indicator {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            background: var(--bg-tertiary);
            border-radius: 8px;
            font-size: 0.875rem;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
        }

        .container {
            flex: 1;
            display: flex;
            max-width: 900px;
            width: 100%;
            margin: 0 auto;
            flex-direction: column;
            overflow: hidden;
            min-height: 0;
        }

        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 2rem;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .message {
            display: flex;
            gap: 0.75rem;
            max-width: 85%;
            animation: fadeIn 0.3s ease-in;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message.user {
            align-self: flex-end;
            flex-direction: row-reverse;
        }

        .message-avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            font-size: 1.25rem;
        }

        .message.assistant .message-avatar {
            background: linear-gradient(135deg, var(--primary), var(--secondary));
        }

        .message.user .message-avatar {
            background: var(--bg-tertiary);
        }

        .message-content {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1rem 1.25rem;
            line-height: 1.6;
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .message.user .message-content {
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            border: none;
        }

        .message.system {
            align-self: center;
            max-width: 100%;
        }

        .message.system .message-content {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            color: var(--text-muted);
            text-align: center;
            font-size: 0.875rem;
            padding: 0.75rem 1rem;
        }

        .tool-indicator {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            padding: 0.25rem 0.75rem;
            background: rgba(102, 126, 234, 0.2);
            border: 1px solid var(--primary);
            border-radius: 20px;
            font-size: 0.75rem;
            color: var(--primary);
            margin-top: 0.75rem;
        }

        .input-area {
            background: var(--bg-secondary);
            border-top: 1px solid var(--border);
            padding: 1.5rem;
        }

        .input-wrapper {
            display: flex;
            gap: 0.75rem;
            max-width: 800px;
            margin: 0 auto;
        }

        input[type="text"] {
            flex: 1;
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 1rem 1.25rem;
            border-radius: 12px;
            font-size: 1rem;
            transition: all 0.2s;
        }

        input[type="text"]:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15);
        }

        input[type="text"]:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        button {
            padding: 1rem 2rem;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }

        button:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.35);
        }

        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }

        .spinner {
            display: inline-block;
            width: 18px;
            height: 18px;
            border: 2px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 0.8s ease-in-out infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .welcome {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 1.5rem;
            text-align: center;
            padding: 2rem;
        }

        .welcome-icon {
            font-size: 4rem;
        }

        .welcome h2 {
            font-size: 1.5rem;
            color: var(--text-primary);
        }

        .welcome p {
            color: var(--text-muted);
            max-width: 400px;
            line-height: 1.6;
        }

        .quick-actions {
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
            justify-content: center;
            margin-top: 1rem;
        }

        .quick-action {
            padding: 0.75rem 1.25rem;
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            border-radius: 20px;
            color: var(--text-secondary);
            font-size: 0.875rem;
            cursor: pointer;
            transition: all 0.2s;
        }

        .quick-action:hover {
            background: var(--primary);
            border-color: var(--primary);
            color: white;
        }

        .session-info {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.5rem;
            text-align: center;
        }

        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg-primary); }
        ::-webkit-scrollbar-thumb { background: var(--bg-tertiary); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--border); }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 JTI 智慧助手</h1>
        <div class="header-right">
            <div class="status-indicator">
                <span class="status-dot"></span>
                <span id="statusText">準備中...</span>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="messages" id="messages">
            <div class="welcome" id="welcome">
                <div class="welcome-icon">🤖</div>
                <h2>嗨！我是 JTI 智慧助手</h2>
                <p>我可以和你聊天、幫你做 MBTI 測驗，並根據你的性格類型推薦適合的商品。</p>
                <div class="quick-actions">
                    <div class="quick-action" onclick="sendQuickMessage('我想做 MBTI 測驗')">🎮 開始 MBTI 測驗</div>
                    <div class="quick-action" onclick="sendQuickMessage('你好，你是誰？')">👋 打個招呼</div>
                    <div class="quick-action" onclick="sendQuickMessage('有什麼商品推薦？')">🛍️ 看看商品</div>
                </div>
            </div>
        </div>

        <div class="input-area">
            <div class="input-wrapper">
                <input
                    type="text"
                    id="userInput"
                    placeholder="輸入訊息... (試試「我想做測驗」)"
                    disabled
                >
                <button id="sendBtn" disabled>發送</button>
            </div>
            <div class="session-info" id="sessionInfo"></div>
        </div>
    </div>

    <script>
        let sessionId = null;
        const apiBase = '/api/mbti';

        const messagesEl = document.getElementById('messages');
        const welcomeEl = document.getElementById('welcome');
        const userInput = document.getElementById('userInput');
        const sendBtn = document.getElementById('sendBtn');
        const statusText = document.getElementById('statusText');
        const sessionInfo = document.getElementById('sessionInfo');

        // 初始化：建立 session
        async function init() {
            try {
                const response = await fetch(apiBase + '/session/new', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode: 'MBTI' })
                });

                const data = await response.json();
                sessionId = data.session_id;

                statusText.textContent = '已連線';
                sessionInfo.textContent = 'Session: ' + sessionId.substring(0, 8) + '...';
                userInput.disabled = false;
                sendBtn.disabled = false;
                userInput.focus();

            } catch (error) {
                statusText.textContent = '連線失敗';
                console.error('Failed to create session:', error);
            }
        }

        function addMessage(text, type = 'assistant', toolCalls = null) {
            // 移除歡迎畫面
            if (welcomeEl) {
                welcomeEl.remove();
            }

            const msg = document.createElement('div');
            msg.className = 'message ' + type;

            const avatar = document.createElement('div');
            avatar.className = 'message-avatar';
            avatar.textContent = type === 'user' ? '👤' : '🤖';

            const content = document.createElement('div');
            content.className = 'message-content';
            content.textContent = text;

            msg.appendChild(avatar);
            msg.appendChild(content);

            // 顯示 tool calls
            if (toolCalls && toolCalls.length > 0) {
                const toolDiv = document.createElement('div');
                toolDiv.className = 'tool-indicator';
                toolDiv.textContent = '🔧 ' + toolCalls.map(t => t.tool).join(' → ');
                content.appendChild(toolDiv);
            }

            messagesEl.appendChild(msg);
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }

        async function sendMessage(message) {
            if (!message || !sessionId) return;

            addMessage(message, 'user');
            userInput.value = '';
            userInput.disabled = true;
            sendBtn.disabled = true;
            sendBtn.innerHTML = '<span class="spinner"></span>';

            try {
                const response = await fetch(apiBase + '/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: sessionId,
                        message: message
                    })
                });

                const data = await response.json();

                if (data.error && !data.message) {
                    addMessage('抱歉，發生錯誤：' + data.error, 'system');
                } else {
                    addMessage(data.message, 'assistant', data.tool_calls);
                }

                // 更新狀態
                if (data.session) {
                    const s = data.session;
                    let status = '對話中';
                    if (s.step === 'QUIZ') status = '測驗中 (' + Object.keys(s.answers || {}).length + '/5)';
                    else if (s.persona) status = 'MBTI: ' + s.persona;
                    statusText.textContent = status;
                }

            } catch (error) {
                addMessage('網路錯誤，請稍後再試', 'system');
                console.error('Chat error:', error);
            } finally {
                userInput.disabled = false;
                sendBtn.disabled = false;
                sendBtn.textContent = '發送';
                userInput.focus();
            }
        }

        function sendQuickMessage(msg) {
            userInput.value = msg;
            sendMessage(msg);
        }

        // Event listeners
        sendBtn.addEventListener('click', () => sendMessage(userInput.value.trim()));

        userInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage(userInput.value.trim());
            }
        });

        // 啟動
        init();
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)
