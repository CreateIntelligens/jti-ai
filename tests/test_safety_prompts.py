"""Tests for the shared safety_prompts module."""

import unittest

from app.services.safety_prompts import (
    PRIORITY_ZERO_SCAN,
    SENSITIVE_HANDLING,
    wrap_with_safety,
)


class TestSafetyPrompts(unittest.TestCase):
    def test_priority_zero_both_languages_present(self):
        for lang in ("zh", "en"):
            self.assertIn(lang, PRIORITY_ZERO_SCAN)
            self.assertTrue(len(PRIORITY_ZERO_SCAN[lang]) > 0)

    def test_sensitive_handling_both_languages_present(self):
        for lang in ("zh", "en"):
            self.assertIn(lang, SENSITIVE_HANDLING)
            self.assertTrue(len(SENSITIVE_HANDLING[lang]) > 0)

    def test_priority_zero_contains_key_phrases(self):
        self.assertIn("自殺", PRIORITY_ZERO_SCAN["zh"])
        self.assertIn("suicide", PRIORITY_ZERO_SCAN["en"].lower())

    def test_sensitive_handling_contains_hotline_numbers(self):
        for lang in ("zh", "en"):
            text = SENSITIVE_HANDLING[lang]
            self.assertIn("1925", text)
            self.assertIn("1995", text)

    def test_wrap_with_safety_prepends_priority_zero(self):
        persona = "你是測試助理。"
        result = wrap_with_safety(persona, "zh")
        self.assertTrue(result.startswith("### 【最高優先級"))
        self.assertIn(persona, result)

    def test_wrap_with_safety_english(self):
        persona = "You are a test assistant."
        result = wrap_with_safety(persona, "en")
        self.assertTrue(result.startswith("### [PRIORITY 0"))
        self.assertIn(persona, result)

    def test_wrap_with_safety_unknown_lang_defaults_to_zh(self):
        persona = "テストです"
        result = wrap_with_safety(persona, "ja")
        # Should fall back to zh
        self.assertIn("最高優先級", result)


if __name__ == "__main__":
    unittest.main()
