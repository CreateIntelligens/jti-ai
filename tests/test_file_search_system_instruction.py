"""
測試 system_instruction 對 File Search 的影響
直接用 Gemini SDK 測試，不經過 backend
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import google.genai as genai
from google.genai import types

API_KEY = os.getenv("GEMINI_API_KEY")
STORE_ID = os.getenv("GEMINI_FILE_SEARCH_STORE_ID_ZH", os.getenv("GEMINI_FILE_SEARCH_STORE_ID"))
MODEL = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

client = genai.Client(api_key=API_KEY)
store_name = f"fileSearchStores/{STORE_ID}"
question = "Ploom X 機身有哪些顏色"

file_search_tools = [
    types.Tool(
        file_search=types.FileSearch(
            file_search_store_names=[store_name]
        )
    )
]

LONG_SYSTEM_PROMPT = """你是 Ploom X 加熱器的智慧客服人員。

## 你的人設

- 名字：小茵（參考黃路梓茵的風格）
- 個性：親切溫柔、帶點俏皮可愛
- 說話風格：溫暖、自然、像朋友聊天一樣
- 語氣範例：「欸對對對」「真的超讚的」「我跟你說」「你知道嗎」

## 你的角色

你可以：
1. 回答關於 Ploom X 加熱菸產品的問題（使用知識庫）
2. 與使用者親切閒聊
3. 引導使用者進行「生活品味色彩探索」測驗
4. 測驗完成後提供色系結果與推薦色

## 回應規則

- 語言：必須使用繁體中文，禁止英文或其他語言
- 長度：回應盡量簡潔，不超過 200 字
- 格式：不要使用表情符號 emoji、不要用特殊符號、不要用 markdown 格式
- 語氣：親切溫柔、俏皮可愛，像朋友聊天
- 如果不確定答案，可以說「這個我不太確定欸」

## 知識庫使用

產品相關問題請根據知識庫回答，不確定就說「這個我需要確認一下」。
Always use File Search before answering product questions.
Do not answer product questions from your own knowledge."""


def run_test(test_name, system_instruction_text=None, prepend_to_message=None):
    print(f"\n{'='*60}")
    print(f"測試: {test_name}")
    print(f"{'='*60}")

    si = None
    if system_instruction_text is not None:
        si = [types.Part.from_text(text=system_instruction_text)]

    config = types.GenerateContentConfig(
        tools=file_search_tools,
        system_instruction=si
    )

    chat_session = client.chats.create(
        model=MODEL,
        config=config,
        history=[]
    )

    msg = question
    if prepend_to_message:
        msg = f"{prepend_to_message}\n\n{question}"

    response = chat_session.send_message(msg, config=config)

    # 檢查 grounding
    grounding = False
    if response.candidates:
        cand = response.candidates[0]
        gm = getattr(cand, 'grounding_metadata', None)
        grounding = gm is not None

    # 取得回覆
    text = ""
    if response.candidates and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'text') and part.text:
                text += part.text

    print(f"grounding_metadata: {grounding}")
    print(f"回覆: {text[:150]}")

    # 檢查是否包含正確顏色
    correct = "極曜紅" in text and "銀" in text and "灰" in text
    print(f"正確答案: {'✅' if correct else '❌'}")
    return grounding, correct


if __name__ == "__main__":
    print(f"Store: {store_name}")
    print(f"Model: {MODEL}")

    # 測試 1: 無 system_instruction
    g1, c1 = run_test("1️⃣ 無 system_instruction", system_instruction_text=None)

    # 測試 2: 極短 system_instruction
    g2, c2 = run_test("2️⃣ system_instruction = 'You are helpful'", system_instruction_text="You are helpful")

    # 測試 3: 長 system_instruction（原始 JTI prompt）
    g3, c3 = run_test("3️⃣ 長 system_instruction（原始 JTI prompt）", system_instruction_text=LONG_SYSTEM_PROMPT)

    # 測試 4: 無 system_instruction，prompt 放在 user message
    g4, c4 = run_test("4️⃣ 無 system_instruction，prompt 放在 user message", system_instruction_text=None, prepend_to_message=LONG_SYSTEM_PROMPT)

    # 總結
    print(f"\n{'='*60}")
    print("總結")
    print(f"{'='*60}")
    print(f"1️⃣  無 system_instruction:          grounding={g1}, correct={c1}")
    print(f"2️⃣  短 system_instruction:          grounding={g2}, correct={c2}")
    print(f"3️⃣  長 system_instruction:          grounding={g3}, correct={c3}")
    print(f"4️⃣  prompt 放 user message:         grounding={g4}, correct={c4}")
