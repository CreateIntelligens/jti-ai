#!/usr/bin/env python3
"""測試色彩測驗的各種情境"""

import asyncio
import json
import os
from typing import Optional

# 設定測試環境變數
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")


async def test_scenario(scenario_name: str, messages: list[tuple[str, str]]):
    """
    測試一個情境

    Args:
        scenario_name: 情境名稱
        messages: [(user_message, expected_pattern), ...]
    """
    from app.services.session.session_manager import SessionManager
    from app.routers.jti import _judge_user_choice, _format_options_text

    print(f"\n{'='*60}")
    print(f"測試情境: {scenario_name}")
    print(f"{'='*60}")

    session_manager = SessionManager()
    session = session_manager.create_session(language="zh", mode="jti")
    session_id = session.session_id

    # 載入第一題
    quiz_bank = json.load(open("data/quiz_bank_color_zh.json"))
    first_question = quiz_bank["questions"][0]

    test_results = []

    for i, (user_msg, expected_pattern) in enumerate(messages, 1):
        print(f"\n步驟 {i}: {user_msg}")

        # 測試意圖判斷
        choice = await _judge_user_choice(user_msg, first_question)

        print(f"  判斷結果: {choice}")
        print(f"  期望模式: {expected_pattern}")

        # 檢查是否符合期望
        if expected_pattern == "OPTION":
            success = choice in ["A", "B", "C", "D", "E"]
        elif expected_pattern == "PAUSE":
            success = choice == "PAUSE"
        elif expected_pattern == "NONE":
            success = choice is None
        else:
            success = choice == expected_pattern

        status = "✅ 通過" if success else "❌ 失敗"
        print(f"  {status}")

        test_results.append((user_msg, choice, expected_pattern, success))

    # 統計結果
    passed = sum(1 for _, _, _, s in test_results if s)
    total = len(test_results)
    print(f"\n結果: {passed}/{total} 通過")

    return test_results


async def main():
    """執行所有測試情境"""

    all_results = []

    # 情境 1: 明確選擇選項
    results = await test_scenario(
        "明確選擇選項",
        [
            ("A", "A"),
            ("我選 B", "B"),
            ("選擇第一個", "A"),
            ("第二個", "B"),
            ("1", "A"),
            ("2", "B"),
        ]
    )
    all_results.extend(results)

    # 情境 2: 帶有解釋的選擇
    results = await test_scenario(
        "帶有解釋的選擇",
        [
            ("我不想太華麗，所以選B", "B"),
            ("我覺得A比較適合我", "A"),
            ("因為我喜歡簡約風格，所以選第二個", "B"),
            ("我個性比較優雅，選A好了", "A"),
        ]
    )
    all_results.extend(results)

    # 情境 3: 暫停/中斷意圖
    results = await test_scenario(
        "暫停/中斷測驗",
        [
            ("中斷", "PAUSE"),
            ("暫停", "PAUSE"),
            ("我想停止測驗", "PAUSE"),
            ("不想做了", "PAUSE"),
            ("退出測驗", "PAUSE"),
        ]
    )
    all_results.extend(results)

    # 情境 4: 無法判斷的訊息
    results = await test_scenario(
        "無法判斷的訊息",
        [
            ("這個問題好難喔", "NONE"),
            ("我不知道要選哪個", "NONE"),
            ("你覺得哪個比較好？", "NONE"),
            ("可以解釋一下選項嗎？", "NONE"),
        ]
    )
    all_results.extend(results)

    # 情境 5: 邊界案例
    results = await test_scenario(
        "邊界案例",
        [
            ("pause", "PAUSE"),  # 英文暫停
            ("PAUSE", "PAUSE"),  # 大寫 PAUSE（不應被誤判為選項 A）
            ("A站", "NONE"),  # 包含 A 但不是選項
            ("prepare", "NONE"),  # 包含 A 但不是選項
            ("AAA", "A"),  # 連續 A
        ]
    )
    all_results.extend(results)

    # 情境 6: 繼續測驗
    print(f"\n{'='*60}")
    print(f"測試情境: 暫停後繼續")
    print(f"{'='*60}")

    from app.services.session.session_manager import SessionManager

    session_manager = SessionManager()
    session = session_manager.create_session(language="zh", mode="jti")

    # 開始測驗
    from app.tools.quiz import generate_random_quiz
    questions = generate_random_quiz(language="zh")
    session.selected_questions = questions
    session.current_q_index = 2  # 假設做到第 3 題
    session.answers = {"c1": "a", "c2": "b"}
    session = session_manager.update_session(session)

    # 暫停
    print("\n1. 暫停測驗")
    paused_session = session_manager.pause_quiz(session.session_id)
    print(f"   Step: {paused_session.step.value}")
    print(f"   paused_quiz: {paused_session.metadata.get('paused_quiz')}")
    print(f"   answers 保留: {len(paused_session.answers)} 題")
    print(f"   ✅ 通過" if paused_session.step.value == "WELCOME" else "❌ 失敗")

    # 繼續
    print("\n2. 繼續測驗")
    resumed_session = session_manager.resume_quiz(session.session_id)
    print(f"   Step: {resumed_session.step.value}")
    print(f"   paused_quiz: {resumed_session.metadata.get('paused_quiz')}")
    print(f"   current_q_index: {resumed_session.current_q_index}")
    print(f"   ✅ 通過" if resumed_session.step.value == "QUIZ" else "❌ 失敗")

    # 總結
    print(f"\n{'='*60}")
    print(f"總體測試結果")
    print(f"{'='*60}")

    passed = sum(1 for _, _, _, s in all_results if s)
    total = len(all_results)
    percentage = (passed / total * 100) if total > 0 else 0

    print(f"\n共測試 {total} 個案例")
    print(f"通過: {passed} ({percentage:.1f}%)")
    print(f"失敗: {total - passed}")

    if passed == total:
        print("\n🎉 所有測試通過！")
    else:
        print("\n⚠️ 有測試失敗，請檢查上方輸出")
        failed = [(msg, choice, expected) for msg, choice, expected, s in all_results if not s]
        print("\n失敗案例:")
        for msg, choice, expected in failed:
            print(f"  - 輸入: '{msg}' | 得到: {choice} | 期望: {expected}")


if __name__ == "__main__":
    asyncio.run(main())
