"""Tests for shared JTI response assembly helpers."""

import unittest

from app.services.jti.response_assembly import (
    build_jti_quiz_question_fields,
    build_jti_response_fields,
    extract_option_texts,
)
from app.services.tts_text import to_jti_tts_text


class TestJtiResponseAssembly(unittest.TestCase):
    def test_build_jti_response_fields_formats_message_for_tts(self):
        message = "請撥1922。"

        self.assertEqual(
            build_jti_response_fields(message, "zh"),
            {
                "message": message,
                "tts_text": to_jti_tts_text(message, "zh"),
            },
        )

    def test_build_jti_response_fields_uses_explicit_tts_source(self):
        fields = build_jti_response_fields(
            "畫面顯示文字",
            "zh",
            tts_source="請撥1925。",
        )

        self.assertEqual(fields["message"], "畫面顯示文字")
        self.assertEqual(fields["tts_text"], to_jti_tts_text("請撥1925。", "zh"))

    def test_build_jti_quiz_question_fields_include_options_only_in_message(self):
        question = {
            "text": "你喜歡哪種旅行？",
            "options": [
                {"text": "冒險"},
                {"text": "放鬆"},
            ],
        }

        fields = build_jti_quiz_question_fields(
            question,
            2,
            "zh",
            prefix="請從選項中選一個喜歡的答案喔！",
        )

        self.assertEqual(
            fields["message"],
            "請從選項中選一個喜歡的答案喔！\n\n第2題：你喜歡哪種旅行？\nA. 冒險\nB. 放鬆",
        )
        self.assertEqual(
            fields["tts_text"],
            to_jti_tts_text("請從選項中選一個喜歡的答案喔！ 第2題：你喜歡哪種旅行？", "zh"),
        )

    def test_extract_option_texts_returns_labeled_options(self):
        question = {
            "options": [
                {"text": "冒險"},
                {"text": "放鬆"},
            ],
        }

        self.assertEqual(extract_option_texts(question), ["A. 冒險", "B. 放鬆"])


if __name__ == "__main__":
    unittest.main()
