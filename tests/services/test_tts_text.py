"""Tests for shared TTS text preparation helpers."""

import unittest

from app.services.hciot.tts import to_hciot_tts_text
from app.services.jti.tts import to_jti_tts_text


class TestTtsText(unittest.TestCase):
    def test_jti_tts_text_converts_digits_for_chinese(self):
        result = to_jti_tts_text("2024年有130人", "zh")
        self.assertIsNotNone(result)
        self.assertIn("二零二四年", result)
        self.assertIn("一百三十", result)

    def test_hciot_tts_text_preserves_digits_for_chinese(self):
        result = to_hciot_tts_text("2024年有130人", "zh")
        self.assertEqual(result, "2024年有130人")

    def test_jti_tts_text_reads_hotlines_digit_by_digit(self):
        result = to_jti_tts_text("請撥1922、1925、1995、110、113或119。", "zh")
        self.assertEqual(result, "请拨一九二二、一九二五、一九九五、一一零、一一三或一一九。")

    def test_hciot_tts_text_reads_hotlines_digit_by_digit(self):
        result = to_hciot_tts_text("請撥1922、1925、1995、110、113或119。", "zh")
        self.assertEqual(result, "请拨一九二二、一九二五、一九九五、一一零、一一三或一一九。")

    def test_non_chinese_tts_text_keeps_original(self):
        text = "There are 130 users in 2024."
        self.assertEqual(to_jti_tts_text(text, "en"), text)
        self.assertEqual(to_hciot_tts_text(text, "en"), text)


if __name__ == "__main__":
    unittest.main()
